"""Recovery fault fixtures; no firmware/boot/USB scripts are executed."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from bridge.frontend import load_frontend
from psp_shell.health import FrontendHealth
from psp_shell.runtime import ActionRegistry, ContractError, HandoffRejected, LaunchCoordinator, LaunchHooks


def write_checked(path, value):
    # Independent fixture encoder checks the public on-disk contract.
    value = dict(value)
    value.pop("checksum", None)
    canonical = lambda record: json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    value["checksum"] = hashlib.sha256(canonical(value)).hexdigest()
    Path(path).write_bytes(canonical(value))


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.health = FrontendHealth(self.temporary.name, boot_id="fixture-boot")

    def project_attempt(self):
        self.health.request("project", self.health.record()["generation"])
        return self.health.begin()

    def ready(self, health=None):
        return (health or self.health).mark_ready(first_frame=True, input_ready=True, settings_ready=True)

    def test_pending_becomes_stable_only_with_three_readiness_checks(self):
        record = self.project_attempt()
        self.assertEqual(record["stable"], "classic")
        self.assertEqual(record["pending"], "project")
        with self.assertRaises(ContractError) as caught:
            self.health.mark_ready(first_frame=True, input_ready=False, settings_ready=True)
        self.assertEqual(caught.exception.code, "NOT_READY")
        record = self.ready()
        self.assertEqual(record["stable"], "project")
        self.assertIsNone(record["pending"])
        self.assertTrue(all(record["readiness"].values()))

    def test_stale_generation_and_attempt_cannot_commit(self):
        self.health.request("project", 0)
        before = self.health.primary.read_bytes()
        with self.assertRaises(ContractError) as caught:
            self.health.request("classic", 0)
        self.assertEqual(caught.exception.code, "STALE_GENERATION")
        self.assertEqual(self.health.primary.read_bytes(), before)
        self.health.begin()
        with self.assertRaises(ContractError):
            self.health.mark_ready(first_frame=True, input_ready=True, settings_ready=True, attempt_id="wrong")

    def test_interrupted_project_start_uses_only_one_classic_fallback(self):
        self.project_attempt()
        restart = FrontendHealth(self.temporary.name, boot_id="fixture-boot", process_alive=lambda *_: False)
        record = restart.begin("project")
        self.assertEqual(record["attempt"]["interface"], "classic")
        self.assertEqual(record["failures"], 1)
        self.assertTrue(record["fallback_used"])
        restart.note_failure()
        with self.assertRaises(ContractError) as caught:
            restart.choose_interface()
        self.assertEqual(caught.exception.code, "NO_SAFE_FRONTEND")

    def test_a_live_startup_is_not_misclassified_as_a_crash(self):
        self.project_attempt()
        second = FrontendHealth(self.temporary.name, boot_id="fixture-boot")
        with self.assertRaises(ContractError) as caught:
            second.begin()
        self.assertEqual(caught.exception.code, "STARTUP_BUSY")
        self.assertEqual(self.health.record()["failures"], 0)

    def test_ready_project_runtime_failure_selects_one_classic_fallback(self):
        self.project_attempt()
        ready = self.ready()
        record = self.health.note_runtime_failure(expected_generation=ready["generation"])
        self.assertEqual(record["stable"], "classic")
        self.assertIsNone(record["pending"])
        self.assertTrue(record["fallback_used"])
        self.assertEqual(record["failures"], 1)
        self.assertEqual(self.health.choose_interface(), "classic")

    def test_corrupt_primary_recovers_to_classic_without_reactivating_project_backup(self):
        self.project_attempt()
        self.ready()
        self.health.primary.write_bytes(b"broken interrupted write")
        self.assertEqual(self.health.choose_interface(), "classic")
        self.assertTrue(self.health.record()["fallback_used"])

    def test_valid_checksum_does_not_make_bad_field_types_safe(self):
        record = self.health.record()
        record["stable"] = ["project"]
        write_checked(self.health.primary, record)
        self.assertEqual(self.health.choose_interface(), "classic")

    def test_future_schema_is_refused_without_overwrite(self):
        record = self.health.record()
        record["schema"] = 2
        write_checked(self.health.primary, record)
        before = self.health.primary.read_bytes()
        with self.assertRaises(ContractError) as caught:
            self.health.request("project", 0)
        self.assertEqual(caught.exception.code, "FUTURE_SCHEMA")
        self.assertEqual(self.health.primary.read_bytes(), before)

    def test_sameboot_foreground_blocks_even_force_classic(self):
        token = self.health.begin_foreground("fake-game")
        self.health.set_force_classic()
        with self.assertRaises(ContractError) as caught:
            self.health.choose_interface()
        self.assertEqual(caught.exception.code, "FOREGROUND_UNCERTAIN")
        with self.assertRaises(ContractError):
            self.health.clear_foreground(token)
        with self.assertRaises(ContractError):
            self.health.clear_foreground("stale", verified=True)
        self.health.clear_foreground(token, verified=True)
        self.assertEqual(self.health.choose_interface(), "classic")

    def test_another_boot_cannot_retain_the_same_game_process(self):
        self.health.begin_foreground("fake-game")
        rebooted = FrontendHealth(self.temporary.name, boot_id="new-fixture-boot")
        self.assertEqual(rebooted.choose_interface(), "classic")

    def test_corrupt_foreground_record_never_assumes_safe_ui_restore(self):
        self.health.begin_foreground("fake-game")
        self.health.foreground.write_text("damaged", encoding="ascii")
        with self.assertRaises(ContractError) as caught:
            self.health.choose_interface()
        self.assertEqual(caught.exception.code, "FOREGROUND_UNCERTAIN")

    def test_force_classic_selects_before_optional_factory_is_called(self):
        self.health.request("project", 0)
        self.health.set_force_classic()
        calls = []
        frontend = load_frontend(self.health,
                                 classic_factory=lambda: calls.append("classic"),
                                 project_factory=lambda: self.fail("optional project import executed"),
                                 release_failed_frontend=lambda: True)
        self.assertEqual(frontend.mode, "classic")
        self.assertEqual(calls, ["classic"])
        frontend.ready(first_frame=True, input_ready=True, settings_ready=True)

    def test_project_import_failure_can_fallback_after_verified_cleanup(self):
        self.health.request("project", 0)
        calls = []
        def missing_view():
            calls.append("import-project")
            raise ImportError("fixture")
        frontend = load_frontend(self.health,
                                 classic_factory=lambda: calls.append("classic"), project_factory=missing_view,
                                 release_failed_frontend=lambda: calls.append("release") or True)
        self.assertEqual(frontend.mode, "classic")
        self.assertEqual(calls, ["import-project", "release", "classic"])

    def test_uncertain_display_release_does_not_open_a_fallback(self):
        self.health.request("project", 0)
        def broken():
            raise RuntimeError("after possible SDL acquisition")
        with self.assertRaises(ContractError) as caught:
            load_frontend(self.health, classic_factory=lambda: self.fail("second UI opened"),
                          project_factory=broken, release_failed_frontend=lambda: False)
        self.assertEqual(caught.exception.code, "UI_RELEASE_UNCERTAIN")

    def test_launch_uncertainty_survives_a_new_frontend_instance(self):
        registry = ActionRegistry()
        def uncertain(_):
            raise RuntimeError("after handoff may have staged")
        registry.register("one", uncertain)
        hooks = LaunchHooks(lambda: {}, lambda: None, lambda: None, lambda: None,
                            lambda _: self.fail("must not restore over unknown game"))
        coordinator = LaunchCoordinator(registry, hooks, health=self.health)
        with self.assertRaises(ContractError):
            coordinator.launch("one")
        restarted = FrontendHealth(self.temporary.name, boot_id="fixture-boot")
        with self.assertRaises(ContractError) as caught:
            restarted.choose_interface()
        self.assertEqual(caught.exception.code, "FOREGROUND_UNCERTAIN")

    def test_known_backend_rejection_clears_ownership_before_restore(self):
        registry = ActionRegistry()
        def reject(_):
            raise HandoffRejected("STALE_GAME", "No command was staged")
        registry.register("one", reject)
        calls = []
        hooks = LaunchHooks(lambda: {}, lambda: None, lambda: None, lambda: None,
                            lambda _: calls.append(self.health.choose_interface()))
        coordinator = LaunchCoordinator(registry, hooks, health=self.health)
        with self.assertRaises(HandoffRejected):
            coordinator.launch("one")
        self.assertEqual(calls, ["classic"])


if __name__ == "__main__":
    unittest.main()
