# SPDX-License-Identifier: MIT
"""Private state transport is data until independent typed authorities agree."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import hashlib
import os
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bridge.bootstrap import ForegroundIdentity, SpruceReturnEvidence
from psp_shell.runtime import SPRUCE_COMMIT
from psp_shell.state_evidence import (FORMAT, UPSTREAM, LaunchIdentity, PPSSPPResumeAdapter, PrivateStateSession,
    QualifiedStateProfile, StateCapabilityStore, StateEvidenceError, VerifiedLoadCompletion, VerifiedState, WriterStoppedEvidence, encode_packet)


class StateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="state-authority-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.card = self.root / "card"
        self.card.mkdir()
        self.game = self.card / "game ü.iso"
        self.engine = self.card / "engine"
        self.states = self.card / "states"
        self.states.mkdir()
        self.state = self.states / "engine-selected.ppst"
        self.game.write_bytes(b"game fixture")
        self.engine.write_bytes(b"engine fixture")
        self.state.write_bytes(b"state fixture")
        self.native_config = self.card / "ppsspp-native.ini"
        self.native_config.write_text("Native configuration fixture\n")
        self.profile = QualifiedStateProfile("fixture", "PPSSPP", "ppsspp-fixture", self.engine, self.sha(self.engine),
            self.card, (self.states,), ("engine", "spruce-copyback"), "1" * 64, architecture="x86_64",
            hardware_qualified=True, writer_inventory_qualified=True, state_save_load_qualified=True, native_state_launch_qualified=True,
            config_hashes=((str(self.native_config), self.sha(self.native_config)),))
        self.foreground = ForegroundIdentity("a" * 32, "b" * 32, "fixture-boot", 3)
        self.identity = LaunchIdentity(self.foreground, "game:fixture", self.game, self.sha(self.game))
        self.returned = SpruceReturnEvidence(self.foreground, SPRUCE_COMMIT, self.profile.principal_sha256, True, True, "owned-tree:fixture")
        self.current = True
        self.writers = WriterStoppedEvidence(self.foreground, self.profile.writer_ids, "writers:fixture", lambda: self.current)

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def session(self, **kwargs):
        value = PrivateStateSession.create(self.root, self.identity, self.profile, **kwargs)
        self.addCleanup(value.close)
        return value

    def result(self, session, *, changes=None):
        fields = list(session._fields[:6]) + ["load" if session._fields[10] == "resume" else "save", "1", "success", "Saved State",
            "ULUS12345", "1.00", "ULUS12345_1.00", str(self.game), self.sha(self.engine), self.sha(self.game), self.sha(self.state),
            str(self.engine.stat().st_size), str(self.game.stat().st_size), str(self.state.stat().st_size), str(self.state), "2", UPSTREAM,
            "trimui-slot-evidence-v1", "v1.20.3-fixture", "x86_64", FORMAT]
        for key, value in (changes or {}).items():
            fields[key] = value
        path = session.path / "result"
        path.write_bytes(encode_packet(b"TPSE1R\n", fields))
        path.chmod(0o600)
        return path

    def verified(self):
        session = self.session()
        self.result(session)
        return session.consume(self.returned, self.writers)

    def test_exact_private_result_and_separate_authorities_make_immutable_capability(self):
        session = self.session()
        self.result(session)
        value = session.consume(self.returned, self.writers)
        self.assertIs(type(value), VerifiedState)
        self.assertTrue(value.validate_game("game:fixture", "PPSSPP", self.game))
        with self.assertRaises(FrozenInstanceError):
            value.slot = 9
        self.assertFalse(hasattr(value, "clean_shutdown"))
        self.assertEqual(session.path.stat().st_mode & 0o777, 0o700)
        self.assertEqual((session.path / "request").stat().st_mode & 0o777, 0o600)

    def test_dict_and_wrong_or_incomplete_foreground_are_rejected(self):
        session = self.session()
        self.result(session)
        invalid = [vars(self.returned), replace(self.returned, foreground=replace(self.foreground, request_id="c" * 32)),
                   replace(self.returned, foreground_ended=False), replace(self.returned, principal_sha256="2" * 64)]
        for proof in invalid:
            with self.subTest(proof=proof), self.assertRaises(StateEvidenceError):
                session.consume(proof, self.writers)

    def test_writer_inventory_and_live_window_remain_separate_requirements(self):
        session = self.session()
        self.result(session)
        for writers in (vars(self.writers), replace(self.writers, writer_ids=("engine",)), replace(self.writers, assert_current=lambda: False)):
            with self.subTest(writers=writers), self.assertRaises(StateEvidenceError):
                session.consume(self.returned, writers)

    def test_profile_is_independent_and_unqualified_default_never_enables_resume(self):
        session = self.session()
        self.result(session)
        session.profile = replace(self.profile, hardware_qualified=False)
        with self.assertRaises(StateEvidenceError) as caught:
            session.consume(self.returned, self.writers)
        self.assertEqual(caught.exception.code, "STATE_PROFILE_UNQUALIFIED")

    def test_request_boot_generation_engine_game_slot_and_state_correlations(self):
        session = self.session()
        for changes in ({0: "f" * 32}, {1: "f" * 32}, {3: "different-boot"}, {4: "4"}, {6: "load"}, {7: "0"}, {8: "failure"},
                        {13: str(self.game) + ".other"}, {14: "f" * 64}, {15: "f" * 64}, {21: "100"}, {26: "another-format"}):
            self.result(session, changes=changes)
            with self.subTest(changes=changes), self.assertRaises(StateEvidenceError):
                session.consume(self.returned, self.writers)

    def test_content_change_and_result_symlink_or_public_permissions_rejected(self):
        session = self.session()
        result = self.result(session)
        result.chmod(0o644)
        with self.assertRaises(StateEvidenceError):
            session.consume(self.returned, self.writers)
        result.chmod(0o600)
        real = session.path / "other"
        result.rename(real)
        result.symlink_to(real)
        with self.assertRaises(OSError):
            session.consume(self.returned, self.writers)
        result.unlink()
        real.rename(result)
        self.state.write_bytes(b"different state")
        with self.assertRaises(StateEvidenceError):
            session.consume(self.returned, self.writers)

    def test_forged_card_result_cannot_create_a_session_or_capability(self):
        with self.assertRaises(StateEvidenceError):
            PrivateStateSession.create(self.card, self.identity, self.profile)
        with self.assertRaises(StateEvidenceError):
            VerifiedState(None, self.identity, self.profile, self.returned, self.writers, ())
        session = self.session()
        self.result(session)
        (session.path / "result").write_bytes(b'TPSE1R\n01:x,' + b"0:," * 26)
        with self.assertRaises(StateEvidenceError):
            session.consume(self.returned, self.writers)

    def test_capability_revalidates_changed_rom_engine_state_and_writer_window(self):
        value = self.verified()
        self.current = False
        with self.assertRaises(StateEvidenceError):
            value.validate_game("game:fixture", "PPSSPP", self.game)
        self.current = True
        self.game.write_bytes(b"changed game")
        with self.assertRaises(StateEvidenceError):
            value.validate_game("game:fixture", "PPSSPP", self.game)

    def test_resume_stages_only_the_existing_qualified_launcher_with_scoped_environment(self):
        value = self.verified()
        new_foreground = replace(self.foreground, request_id="d" * 32, token="e" * 32, generation=5)
        new_identity = replace(self.identity, foreground=new_foreground)
        calls = []
        adapter = PPSSPPResumeAdapter(self.profile, self.root, current_foreground=lambda model, record: new_identity,
            stage_existing_launch=lambda model, invocation: calls.append(invocation) or "staged")
        self.assertEqual(adapter(SimpleNamespace(rom_file_path=str(self.game)), value), "staged")
        invocation = calls[0]
        self.addCleanup(invocation.session.close)
        self.assertEqual(invocation.command_environment["TRIMUI_PROJECT_RESUME_STATE"], str(self.state))
        self.assertEqual(invocation.session.native_arguments[1], "--state=" + str(self.state))
        with self.assertRaises(StateEvidenceError):
            adapter(SimpleNamespace(rom_file_path=str(self.game)), {"state": "fake"})

    def test_load_acknowledgement_cannot_be_substituted_for_a_different_state(self):
        value = self.verified()
        session = self.session(mode="resume", resume=value)
        self.result(session)
        self.assertIs(type(session.consume(self.returned, self.writers)), VerifiedLoadCompletion)
        self.result(session, changes={16: "0" * 64})
        with self.assertRaises(StateEvidenceError):
            session.consume(self.returned, self.writers)

    def completed(self, session, *, operation="save", sequence="1"):
        result = self.result(session, changes={6: operation, 7: sequence})
        (session.path / (operation + "-completed")).write_bytes(result.read_bytes())
        (session.path / (operation + "-completed")).chmod(0o600)

    def failed_result(self, session, sequence, operation="save"):
        changes = {6: operation, 7: str(sequence), 8: "failure"}
        changes.update({index: "" for index in range(10, 27)})
        self.result(session, changes=changes)

    def test_same_session_failed_later_save_retains_only_genuine_completed_state(self):
        session = self.session()
        self.completed(session)
        self.failed_result(session, 2)
        values, error = session.consume_completed(self.returned, self.writers)
        self.assertEqual(error, "STATE_OPERATION_FAILED")
        self.assertEqual(len(values), 1)
        self.assertIs(type(values[0]), VerifiedState)
        self.assertEqual(values[0]._result[7], "1")
        self.state.write_bytes(b"unrecorded later state")
        values, error = session.consume_completed(self.returned, self.writers)
        self.assertEqual(values, ())

    def test_interrupted_future_or_other_request_completion_cannot_be_promoted(self):
        session = self.session()
        self.completed(session, sequence="2")
        (session.path / "result").unlink()
        with self.assertRaises(FileNotFoundError):
            session.consume_completed(self.returned, self.writers)
        self.failed_result(session, 1)
        values, _ = session.consume_completed(self.returned, self.writers)
        self.assertEqual(values, ())
        self.result(session, changes={1: "f" * 32})
        (session.path / "save-completed").write_bytes((session.path / "result").read_bytes())
        self.failed_result(session, 3)
        values, _ = session.consume_completed(self.returned, self.writers)
        self.assertEqual(values, ())

    def test_resumed_session_new_save_survives_failed_write_and_invalid_old_load_bytes(self):
        prior = self.verified()
        session = self.session(mode="resume", resume=prior)
        self.completed(session, operation="load")
        old_hash = self.sha(self.state)
        self.state.write_bytes(b"genuinely exported new checkpoint fixture")
        self.completed(session, sequence="2")
        self.failed_result(session, 3)
        values, error = session.consume_completed(self.returned, self.writers)
        self.assertEqual(error, "STATE_OPERATION_FAILED")
        self.assertEqual(len(values), 1)
        value = values[0]
        self.assertIs(type(value), VerifiedState)
        self.assertNotEqual(value.state_sha256, old_hash)
        self.assertEqual(value._result[6:9], ("save", "2", "success"))
        store = StateCapabilityStore(self.root / "capabilities", boot_id="fixture-boot")
        self.addCleanup(store.close)
        store.save(session, value)
        restored = store.load("game:fixture", self.profile, lambda foreground, profile: self.writers)
        self.assertEqual(restored.state_sha256, value.state_sha256)
        self.assertEqual(restored.recorded_at_utc, value.recorded_at_utc)

    def stored(self):
        session = self.session()
        self.result(session)
        value = session.consume(self.returned, self.writers)
        store = StateCapabilityStore(self.root / "capabilities", boot_id="fixture-boot")
        self.addCleanup(store.close)
        store.save(session, value)
        return store, value

    def test_authenticated_capability_survives_a_fresh_process_with_original_timestamp(self):
        store, value = self.stored()
        loaded = store.load("game:fixture", self.profile, lambda foreground, profile: self.writers)
        self.assertEqual(loaded.recorded_at_utc, value.recorded_at_utc)
        self.assertEqual(loaded.recorded_monotonic_ns, value.recorded_monotonic_ns)
        self.assertEqual(store.game_ids(), ("game:fixture",))
        code = '''import json,sys,hashlib
from pathlib import Path
from psp_shell.state_evidence import *
root=Path(sys.argv[1]);card=root/'card'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
profile=QualifiedStateProfile('fixture','PPSSPP','ppsspp-fixture',card/'engine',sha(card/'engine'),card,(card/'states',),('engine','spruce-copyback'),'1'*64,architecture='x86_64',hardware_qualified=True,writer_inventory_qualified=True,state_save_load_qualified=True,native_state_launch_qualified=True,config_hashes=((str(card/'ppsspp-native.ini'),sha(card/'ppsspp-native.ini')),))
store=StateCapabilityStore(root/'capabilities',boot_id='fixture-boot')
value=store.load('game:fixture',profile,lambda foreground,profile:WriterStoppedEvidence(foreground,profile.writer_ids,'fresh-writer-lease',lambda:True))
print(json.dumps([value.state_sha256,value.recorded_at_utc,value.recorded_monotonic_ns]))
store.close()
'''
        result = subprocess.run([sys.executable, "-c", code, str(self.root)], text=True, capture_output=True, timeout=15, check=True)
        self.assertEqual(json.loads(result.stdout), [value.state_sha256, value.recorded_at_utc, value.recorded_monotonic_ns])

    def test_delayed_consumption_records_verification_not_engine_save_time(self):
        session = self.session()
        result = self.result(session)
        # A completed native result can exist while play continues. Its old
        # file timestamp does not turn the later principal observation into a
        # save timestamp; no engine save time exists in this protocol.
        os.utime(result, (1700000000, 1700000000))
        observed = datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc)
        with patch("psp_shell.state_evidence.datetime") as clock:
            clock.now.return_value = observed
            value = session.consume(self.returned, self.writers)
        self.assertEqual(value.recorded_at_utc, observed.isoformat())
        self.assertFalse(hasattr(value, "saved_at_utc"))
        self.assertEqual(result.stat().st_mtime_ns, 1700000000000000000)
        store = StateCapabilityStore(self.root / "capabilities", boot_id="fixture-boot")
        self.addCleanup(store.close)
        store.save(session, value)
        with patch("psp_shell.state_evidence.datetime") as later_clock:
            later_clock.now.return_value = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
            restored = store.load("game:fixture", self.profile, lambda foreground, profile: self.writers)
        self.assertEqual(restored.recorded_at_utc, observed.isoformat())

    def test_concurrent_first_use_never_publishes_a_partial_signing_key(self):
        entered = threading.Event()
        release = threading.Event()
        second_started = threading.Event()
        from psp_shell.state_evidence import secrets
        random_bytes = secrets.token_bytes

        def delayed_random(count):
            if count == 32:
                entered.set()
                self.assertTrue(release.wait(3), "key writer was never released")
            return random_bytes(count)

        path = self.root / "concurrent-capabilities"
        def open_second():
            second_started.set()
            return StateCapabilityStore(path, boot_id="fixture-boot")

        with patch("psp_shell.state_evidence.secrets.token_bytes", side_effect=delayed_random), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(StateCapabilityStore, path, boot_id="fixture-boot")
            try:
                self.assertTrue(entered.wait(3))
                second = pool.submit(open_second)
                self.assertTrue(second_started.wait(3))
                with self.assertRaises(FutureTimeout):
                    second.result(timeout=0.05)
                self.assertFalse((path / "key").exists(), "unfinished key became visible")
            finally:
                release.set()
            one, two = first.result(timeout=3), second.result(timeout=3)
        self.addCleanup(one.close)
        self.addCleanup(two.close)
        self.assertEqual(one._key, two._key)
        self.assertEqual(len(one._key), 32)
        self.assertEqual((path / "key").stat().st_mode & 0o777, 0o600)

    def test_tampered_capability_cross_boot_and_changed_profile_inventory_are_rejected(self):
        store, value = self.stored()
        changed = replace(self.profile, writer_ids=self.profile.writer_ids + ("other-writer",))
        with self.assertRaises(StateEvidenceError):
            store.load("game:fixture", changed, lambda foreground, profile: replace(self.writers, writer_ids=profile.writer_ids))
        second_boot = StateCapabilityStore(store.path, boot_id="different-boot")
        self.addCleanup(second_boot.close)
        with self.assertRaises(StateEvidenceError):
            second_boot.load("game:fixture", self.profile, lambda foreground, profile: self.writers)
        record = store.path / store._name("game:fixture")
        raw = record.read_bytes()
        record.write_bytes(raw.replace(b"game:fixture", b"game:forgery"))
        with self.assertRaises(StateEvidenceError) as caught:
            store.load("game:fixture", self.profile, lambda foreground, profile: self.writers)
        self.assertEqual(caught.exception.code, "STATE_CAPABILITY_AUTHENTICATION")

    def test_replaced_native_config_or_executable_invalidates_capability(self):
        store, value = self.stored()
        original = self.native_config.read_bytes()
        self.native_config.write_text("replaced config")
        with self.assertRaises(StateEvidenceError):
            store.load("game:fixture", self.profile, lambda foreground, profile: self.writers)
        self.native_config.write_bytes(original)
        self.engine.write_bytes(b"replaced engine")
        with self.assertRaises(StateEvidenceError):
            store.load("game:fixture", self.profile, lambda foreground, profile: self.writers)

    def test_backend_typed_resume_delivers_capability_and_invalidates_stale_actions(self):
        from psp_shell.adapters.spruce import PyUIModelProvider, SpruceBackend, SpruceError
        game = self.card / "Roms/PSP/game.iso"
        game.parent.mkdir(parents=True)
        game.write_bytes(self.game.read_bytes())
        self.game = game
        emu = self.card / "Emu/PSP"
        emu.mkdir(parents=True)
        (emu / "config.json").write_text(json.dumps({"label": "PSP", "launch": "launch.sh", "extlist": "iso", "default_emulator": "PPSSPP"}))
        (emu / "launch.sh").write_text("#!/bin/sh\n")
        system = SimpleNamespace(system_name="PSP")
        model = SimpleNamespace(game_system=system, rom_file_path=str(game), display_name="Fixture PSP")
        calls = []
        provider = PyUIModelProvider(self.card, system_manager=SimpleNamespace(get_active_systems=lambda: [system]),
            game_list=lambda system_id: [model], device=SimpleNamespace(run_game=lambda item: calls.append("normal")),
            favorites_manager=SimpleNamespace(get_favorites=lambda: []), recents_manager=SimpleNamespace(get_recents=lambda: [model]),
            release_resources=lambda: None, quiescent=lambda: True,
            mode_actions={"PPSSPP": {"resume": lambda item, record: calls.append(record)}})
        backend = SpruceBackend(self.card, read_only=False, managers=provider)
        row = provider.game_records()[0]
        self.identity = replace(self.identity, game_id=row["id"], rom_path=game)
        value = self.verified()
        backend.set_verified_resume_evidence({row["id"]: value})
        status = backend.recent()[0]
        self.assertTrue(status["resume_available"])
        self.assertEqual(status["state_recorded_at"], value.recorded_at_utc)
        self.assertEqual(status["state_recorded_at_kind"], "verification")
        action = backend.resolve_game(row["id"], mode="resume")["action_id"]
        backend.execute_action(action, "resume", release_ui=False)
        self.assertIs(calls[0], value)
        action = backend.resolve_game(row["id"], mode="resume")["action_id"]
        self.state.write_bytes(b"changed after preview")
        with self.assertRaises(SpruceError):
            backend.execute_action(action, "resume", release_ui=False)
        with self.assertRaises(SpruceError):
            backend.set_verified_resume_evidence({row["id"]: {"state": "forged"}})


if __name__ == "__main__":
    unittest.main()
