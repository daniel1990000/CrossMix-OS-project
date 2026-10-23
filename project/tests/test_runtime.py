"""Host fake-backend proofs. No spruce or hardware commands execute here."""
import dataclasses
import unittest

from psp_shell.runtime import (ActionRegistry, ContractError, ExclusiveTransition,
                               HandoffRejected, LaunchCoordinator, LaunchHooks,
                               LaunchState, POWER_OFF_ROUTE, PreflightReport,
                               SPRUCE_COMMIT, TransitionBackend, original_tsp_preflight)


class RuntimeTests(unittest.TestCase):
    def coordinator(self, fail=None, backend=None, backend_mode="fake", preflight=None):
        events = []
        snapshot = {"category": "Games", "focus": "psp:one"}

        def hook(name, result=None):
            def call(*args):
                events.append(name)
                if name == "restore":
                    self.assertIs(args[0], snapshot)
                if fail == name:
                    raise RuntimeError("injected failure")
                return result
            return call

        registry = ActionRegistry()
        callback = backend or hook("delegate")
        registry.register("game:one", callback, backend_mode=backend_mode)
        hooks = LaunchHooks(hook("snapshot", snapshot), hook("stop"), hook("renderer"),
                            hook("input"), hook("restore"))
        return LaunchCoordinator(registry, hooks, preflight=preflight), events

    def test_release_order_and_external_return_are_distinct(self):
        coordinator, events = self.coordinator()
        receipt = coordinator.launch("game:one", request_id="request-one")
        self.assertEqual(events, ["snapshot", "stop", "renderer", "input", "delegate"])
        self.assertEqual(receipt.state, "delegated")
        self.assertEqual(coordinator.state, LaunchState.DELEGATED)
        with self.assertRaises(ContractError) as caught:
            coordinator.launch("game:one", request_id="other")
        self.assertEqual(caught.exception.code, "BUSY_GAME")
        coordinator.return_from_backend("request-one")
        self.assertEqual(events[-1], "restore")
        self.assertEqual(coordinator.state, LaunchState.IDLE)

    def test_request_is_once_only_even_after_return(self):
        coordinator, events = self.coordinator()
        first = coordinator.launch("game:one", request_id="once")
        self.assertEqual(coordinator.launch("game:one", request_id="once"), first)
        coordinator.return_from_backend("once")
        self.assertEqual(coordinator.launch("game:one", request_id="once"), first)
        self.assertEqual(events.count("delegate"), 1)
        with self.assertRaises(ContractError) as caught:
            coordinator.launch("game:one", mode="fresh", request_id="once")
        self.assertEqual(caught.exception.code, "REQUEST_CONFLICT")

    def test_preparation_failures_restore_before_another_launch(self):
        for stage in ("stop", "renderer", "input"):
            with self.subTest(stage=stage):
                coordinator, events = self.coordinator(fail=stage)
                with self.assertRaises(ContractError):
                    coordinator.launch("game:one", request_id="failed")
                self.assertEqual(events[-1], "restore")
                self.assertNotIn("delegate", events)
                self.assertEqual(coordinator.state, LaunchState.IDLE)

    def test_unknown_ids_and_snapshot_command_data_never_execute(self):
        coordinator, events = self.coordinator()
        for action in ("snapshot-executable", "sh -c something", {"command": "/bin/false"}):
            with self.subTest(action=action):
                with self.assertRaises(ContractError):
                    coordinator.launch(action)
        self.assertEqual(events, [])

    def test_unsupported_resume_fails_before_release(self):
        coordinator, events = self.coordinator()
        with self.assertRaises(ContractError) as caught:
            coordinator.launch("game:one", mode="resume")
        self.assertEqual(caught.exception.code, "UNSUPPORTED_MODE")
        self.assertEqual(events, [])

    def test_known_backend_rejection_restores_once(self):
        called = []
        def reject(intent):
            called.append(intent.request_id)
            raise HandoffRejected("MISSING_GAME", "Game vanished before staging")
        coordinator, events = self.coordinator(backend=reject)
        for _ in range(2):
            with self.assertRaises(HandoffRejected):
                coordinator.launch("game:one", request_id="rejected")
        self.assertEqual(called, ["rejected"])
        self.assertEqual(events.count("restore"), 1)

    def test_unknown_backend_failure_blocks_overlay(self):
        def uncertain(_):
            raise RuntimeError("might have staged command")
        coordinator, events = self.coordinator(backend=uncertain)
        with self.assertRaises(ContractError) as caught:
            coordinator.launch("game:one", request_id="uncertain")
        self.assertEqual(caught.exception.code, "HANDOFF_UNCERTAIN")
        self.assertEqual(coordinator.state, LaunchState.BLOCKED)
        self.assertNotIn("restore", events)
        with self.assertRaises(ContractError):
            coordinator.launch("game:one")

    def test_actual_pyui_style_exit_is_propagated_without_restore(self):
        def exit_frontend(_):
            raise SystemExit(0)
        coordinator, events = self.coordinator(backend=exit_frontend)
        with self.assertRaises(SystemExit):
            coordinator.launch("game:one")
        self.assertEqual(coordinator.state, LaunchState.DELEGATED)
        self.assertNotIn("restore", events)

    def test_live_backend_requires_preflight_and_verified_return(self):
        coordinator, events = self.coordinator(backend_mode="spruce")
        with self.assertRaises(ContractError) as caught:
            coordinator.launch("game:one")
        self.assertEqual(caught.exception.code, "HARDWARE_UNQUALIFIED")
        self.assertEqual(events, [])
        # This explicitly injected host result is not a device qualification.
        coordinator, events = self.coordinator(backend_mode="spruce", preflight=lambda: PreflightReport())
        receipt = coordinator.launch("game:one")
        with self.assertRaises(ContractError) as caught:
            coordinator.return_from_backend(receipt.request_id)
        self.assertEqual(caught.exception.code, "RETURN_UNVERIFIED")
        self.assertNotIn("restore", events)
        coordinator.return_from_backend(receipt.request_id, verified=True)
        self.assertEqual(events[-1], "restore")

    def test_duplicate_registry_id_is_not_replaced(self):
        registry = ActionRegistry()
        registry.register("one", lambda _: None)
        with self.assertRaises(ContractError):
            registry.register("one", lambda _: None)

    def test_exclusive_transition_refuses_each_busy_activity(self):
        exclusive = ExclusiveTransition()
        called = []
        backend = TransitionBackend(lambda: called.append("usb"))
        for activity in ("game", "index", "write"):
            with self.subTest(activity=activity), exclusive.activity(activity):
                with self.assertRaises(ContractError) as caught:
                    exclusive.perform("usb", backend)
                self.assertEqual(caught.exception.code, "BUSY_ACTIVITY")
        self.assertEqual(called, [])
        result = exclusive.perform("usb", backend, request_id="usb-once")
        self.assertTrue(result.reboot_required)
        self.assertEqual(result.backend_mode, "fake")
        exclusive.perform("usb", backend, request_id="usb-once")
        self.assertEqual(called, ["usb"])

    def test_live_usb_is_qualified_and_stays_exclusive_until_reboot(self):
        exclusive = ExclusiveTransition()
        called = []
        backend = TransitionBackend(lambda: called.append("delegated"), backend_mode="spruce")
        with self.assertRaises(ContractError):
            exclusive.perform("usb", backend)
        self.assertEqual(called, [])
        exclusive.perform("usb", dataclasses.replace(backend, qualified=True))
        with self.assertRaises(ContractError):
            exclusive.acquire("write")
        self.assertEqual(exclusive.operation, "usb")

    def test_usb_cannot_claim_live_return_without_reboot(self):
        with self.assertRaises(ContractError):
            ExclusiveTransition().perform("usb", TransitionBackend(lambda: None, reboot_required=False))

    def test_failed_restore_blocks_further_activity(self):
        coordinator, _ = self.coordinator(fail="restore")
        receipt = coordinator.launch("game:one")
        with self.assertRaises(ContractError) as caught:
            coordinator.return_from_backend(receipt.request_id)
        self.assertEqual(caught.exception.code, "UI_RESTORE_FAILED")
        self.assertEqual(coordinator.state, LaunchState.BLOCKED)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.profile = {"source_commit": SPRUCE_COMMIT, "firmware_version": "1.1.1",
                        "required_hashes": {"/fixture/SDL": "a" * 64}, "physical_qualification": True}
        self.inventory = {"model": "TG5040", "platform": "SmartPro", "architecture": "aarch64",
                          "source_commit": SPRUCE_COMMIT, "firmware_version": "1.1.1",
                          "hashes": {"/fixture/SDL": "a" * 64}, "live": True}
        self.preferences = {"enableButtonWatchers": False, "poweroffCmd": POWER_OFF_ROUTE}

    def test_host_fixture_can_check_typed_evidence_without_running_it(self):
        self.assertTrue(original_tsp_preflight(self.inventory, self.preferences, self.profile).safe)

    def test_wrong_models_missing_power_preference_and_snapshot_are_refused(self):
        cases = [({"model": "TG5050"}, {}, "UNSUPPORTED_DEVICE"),
                 ({"platform": "Brick"}, {}, "UNSUPPORTED_DEVICE"),
                 ({"hashes": {"/fixture/SDL": "b" * 64}}, {}, "RUNTIME_HASH_MISMATCH"),
                 ({"live": False}, {}, "HARDWARE_UNQUALIFIED"),
                 ({}, {"enableButtonWatchers": True}, "UNSAFE_POWER_PREFERENCES"),
                 ({}, {"poweroffCmd": "poweroff"}, "UNSAFE_POWER_PREFERENCES")]
        for changed_inventory, changed_preferences, code in cases:
            with self.subTest(code=code):
                report = original_tsp_preflight(dict(self.inventory, **changed_inventory),
                                               dict(self.preferences, **changed_preferences), self.profile)
                self.assertIn(code, [item[0] for item in report.errors])
        preferences = dict(self.preferences)
        del preferences["enableButtonWatchers"]
        self.assertFalse(original_tsp_preflight(self.inventory, preferences, self.profile).safe)

    def test_profile_cannot_learn_expected_hashes_from_snapshot(self):
        self.profile["required_hashes"] = {}
        self.assertFalse(original_tsp_preflight(self.inventory, self.preferences, self.profile).safe)


if __name__ == "__main__":
    unittest.main()
