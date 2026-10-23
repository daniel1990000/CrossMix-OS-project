# SPDX-License-Identifier: MIT
"""Explicit synthetic fixtures exercise the real private runtime configuration."""
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from bridge.experimental import ExpectedFile, HostCandidate
from bridge.experimental_runtime import (HostFixtureReview, RecoveryRuntimeReview, RuntimeCandidate,
    RuntimeObservation, SourceUseEvidenceReview, configuration, prepare_fixture_session, prepare_private_session)
from bridge.process_source import ProcessSourceConfiguration, configured_runtime, process_start
from bridge.principal_integration import SOURCE_BLOBS, REQUIRED_PROJECT_MODULES
from psp_shell.health import _boot_id
from psp_shell.runtime import ContractError, POWER_OFF_ROUTE, SPRUCE_COMMIT


def fixture_file_bytes(root, overrides=None):
    """Expected synthetic bytes from test code, independently of observed files."""
    prefix = "App/PSPMode/integration/"
    names = set(SOURCE_BLOBS) | {prefix + name for name in REQUIRED_PROJECT_MODULES} | {"rootfs/python-fixture"}
    result = {name: ("synthetic-reviewed-fixture:" + name + "\n").encode() for name in names}
    result.update(overrides or {})
    return result


def prepare_fixture_tree(root, overrides=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name, raw in fixture_file_bytes(root, overrides).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o755 if name.endswith(".sh") else 0o644)


def make_fixture_configuration(root, *, principal_pid=None, principal_start=None, role_name="fixture",
                               overrides=None, clock=time.monotonic, view_seconds=120, return_seconds=5,
                               case_sha256="c" * 64):
    """Per-process test factory; does not enable the shipped fixed selector.

    Parent subprocess tests supply one independently known principal identity
    and the same expected test-program bytes in each role. Evidence directories
    are distinct per role/PID, while the principal alone reserves the case.
    """
    root = Path(root).absolute()
    principal_pid = os.getppid() if principal_pid is None else principal_pid
    principal_start = process_start(principal_pid) if principal_start is None else principal_start
    raw_expected = fixture_file_bytes(root, overrides)
    files = tuple(sorted((ExpectedFile(name, hashlib.sha256(raw).hexdigest()) for name, raw in raw_expected.items()),
                          key=lambda item: item.path))
    original = tuple(ExpectedFile(name, hashlib.sha256(raw_expected["App/PSPMode/integration/" + name]).hexdigest())
                     for name in REQUIRED_PROJECT_MODULES)
    build = HostCandidate("a" * 40, "b" * 64, "d" * 64, "e" * 64, "f" * 64, original)
    state = root.parent / "experimental-state"
    expected = RuntimeCandidate(build, files, ("rootfs/python-fixture",), str(root),
        str(root / "App/PSPMode/integration/app"), str(state), _boot_id(), principal_pid,
        principal_start, "1" * 64, "host-fixture-firmware", "host-fixture-filesystem", case_sha256)
    def hashes():
        return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in raw_expected}
    def observe():
        return RuntimeObservation(expected.boot_id, principal_pid, principal_start, expected.media_sha256,
            tuple(ExpectedFile(name, value) for name, value in sorted(hashes().items())),
            expected.firmware_version, expected.filesystem, live_device=False)
    evidence = root.parent / ("private-experimental-evidence-" + role_name + "-" + str(os.getpid()))
    evidence.mkdir(mode=0o700)
    session = prepare_fixture_session(expected, observe, evidence, review=HostFixtureReview("2" * 64),
                                      clock=clock, view_seconds=view_seconds, return_seconds=return_seconds)
    config = ProcessSourceConfiguration({"source_commit": SPRUCE_COMMIT,
        "source_use_verified": False, "runtime_verified": False, "hardware_qualified": False,
        "process_exit_qualified": False, "required_hashes": {item.path: item.sha256 for item in files}},
        lambda: {"hashes": hashes(), "live": False},
        lambda: {"enableButtonWatchers": False, "poweroffCmd": POWER_OFF_ROUTE},
        sd_root=root, state_dir=state, staged_command=root.parent / "staged-command.sh",
        private_runtime=root.parent / "experimental-private-runtime", execution_environment="host-fixture",
        experimental_session=session)
    config.assert_safe()
    return config


class ExperimentalRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="experimental-runtime-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "card"
        prepare_fixture_tree(self.root)
        self.config = make_fixture_configuration(self.root)
        self.addCleanup(self.config.experimental_session.close)

    def test_fixed_selectors_stay_unavailable_and_explicit_typed_fixture_config_validates(self):
        self.assertIsNone(configuration())
        self.assertIsNone(configured_runtime())
        self.config.assert_safe()
        self.assertTrue(all(self.config.profile[name] is False for name in
                            ("source_use_verified", "hardware_qualified", "runtime_verified", "process_exit_qualified")))
        with mock.patch("bridge.experimental_runtime.configuration", return_value=self.config):
            self.assertIs(configured_runtime(), self.config)

    def test_untyped_configuration_or_session_is_rejected(self):
        with mock.patch("bridge.experimental_runtime.configuration", return_value={"enabled": True}):
            with self.assertRaises(ContractError):
                configured_runtime()
        invalid = replace(self.config, experimental_session={"enabled": True})
        with self.assertRaises(ContractError):
            invalid.assert_safe()

    def test_missing_actual_prerequisite_reviews_cannot_create_a_private_device_session(self):
        session = self.config.experimental_session
        for source_review in (None, HostFixtureReview("1" * 64), SourceUseEvidenceReview("1" * 64, "2" * 64)):
            with self.assertRaises(ContractError):
                prepare_private_session(session.expected, session._observe, self.root.parent / "must-not-be-created",
                    source_use=source_review, recovery_runtime=RecoveryRuntimeReview("1" * 64, "2" * 64, "3" * 64, "4" * 64))
        self.assertFalse((self.root.parent / "must-not-be-created").exists())

    def test_device_factory_rejects_host_observations_even_with_explicit_review_objects(self):
        source = SourceUseEvidenceReview("1" * 64, "2" * 64, actual_delivery_reviewed=True)
        recovery = RecoveryRuntimeReview("1" * 64, "2" * 64, "3" * 64, "4" * 64, True, True, True)
        directory = self.root.parent / "rejected-device-evidence"
        directory.mkdir(mode=0o700)
        with self.assertRaises(ContractError):
            prepare_private_session(self.config.experimental_session.expected, self.config.experimental_session._observe,
                                    directory, source_use=source, recovery_runtime=recovery)

    def test_runtime_payload_or_media_change_blocks_instead_of_reusing_observed_hashes(self):
        path = self.root / "App/PyUI/launch.sh"
        path.write_bytes(b"changed")
        with self.assertRaises(ContractError):
            self.config.assert_safe()

    def test_complete_import_and_principal_inventory_is_required(self):
        expected = self.config.experimental_session.expected
        with self.assertRaises(ContractError):
            replace(expected, files=tuple(item for item in expected.files if item.path != "spruce/scripts/principal.sh"))
        with self.assertRaises(ContractError):
            replace(expected, imports=())

    def test_true_production_flags_are_not_an_experimental_shortcut(self):
        altered = replace(self.config, profile={**self.config.profile, "hardware_qualified": True})
        with self.assertRaises(ContractError):
            altered.assert_safe()

    def test_phase_cannot_be_claimed_without_the_authenticated_resident(self):
        session = self.config.experimental_session
        with self.assertRaises((ContractError, FileNotFoundError, KeyError)):
            session.check_view()
        self.assertNotEqual(session.phase, "released")

    def test_principal_deadline_uses_the_exact_authenticated_reservation(self):
        session = self.config.experimental_session
        start = time.monotonic()
        record = {"phase": "running", "started_monotonic": start,
                  "view_deadline": start + session.view_seconds,
                  "return_deadline": start + session.view_seconds + session.return_seconds}
        with mock.patch.object(session, "_record", return_value=record):
            policy = session.source_observation_policy()
            self.assertEqual(policy.deadline_monotonic, record["return_deadline"])
            self.assertTrue(policy.observation_active())
            record["phase"] = "released"
            self.assertFalse(policy.observation_active())

    def test_inconsistent_authenticated_deadline_is_rejected(self):
        session = self.config.experimental_session
        start = time.monotonic()
        record = {"phase": "running", "started_monotonic": start,
                  "view_deadline": start + session.view_seconds,
                  "return_deadline": float("inf")}
        with mock.patch.object(session, "_record", return_value=record), self.assertRaises(ContractError):
            session.source_observation_policy()
        self.assertEqual(session.phase, "blocked")

    def test_early_return_observation_uses_shortened_signed_deadline_without_releasing_owners(self):
        session = self.config.experimental_session
        start = time.monotonic()
        record = {"phase": "running", "started_monotonic": start,
                  "view_deadline": start + session.view_seconds,
                  "return_deadline": start + session.view_seconds + session.return_seconds}
        with mock.patch.object(session, "_record", return_value=record):
            policy = session.source_observation_policy()
            record.update(phase="return_requested", return_deadline=start + 1)
            self.assertTrue(policy.observation_active())
            with mock.patch.object(session, "_clock", return_value=start + 2), self.assertRaises(ContractError):
                policy.observation_active()
            self.assertNotEqual(session.phase, "released")

    def test_successful_timeout_evidence_callback_does_not_pretend_its_report_failed(self):
        session = self.config.experimental_session
        start = time.monotonic()
        record = {"phase": "running", "started_monotonic": start,
                  "view_deadline": start + session.view_seconds,
                  "return_deadline": start + session.view_seconds + session.return_seconds}
        with mock.patch.object(session, "_record", return_value=record):
            policy = session.source_observation_policy()
            self.assertIsNone(policy.on_blocked(None))
        self.assertEqual(session.phase, "blocked")


if __name__ == "__main__":
    unittest.main()
