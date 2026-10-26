# SPDX-License-Identifier: MIT
"""Actual EmbeddedRunner/model actions obey the injected private view policy."""
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from bridge.pyui_entry import bind_context_factory, maybe_run_main_menu
from psp_shell.embedded import EmbeddedDependencies, EmbeddedRunner
from psp_shell.health import FrontendHealth
from psp_shell.runtime import ContractError
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_embedded as embedded_fixtures
from test_experimental_runtime import make_fixture_configuration, prepare_fixture_tree


class ExperimentalEmbeddedTests(unittest.TestCase):
    def setUp(self):
        fixture = embedded_fixtures.EmbeddedTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        prepare_fixture_tree(fixture.card)
        self.config = make_fixture_configuration(fixture.card)
        self.session = self.config.experimental_session
        self.addCleanup(self.session.close)
        self.addCleanup(bind_context_factory, None)
        self.context = replace(fixture.context, state_dir=self.config.state_dir,
            profile=self.config.profile, inventory=self.config.inventory(), preferences=self.config.preferences(),
            experimental_session=self.session)
        self.health = FrontendHealth(self.config.state_dir)
        state = self.health.record()
        self.health.request("project", state["generation"])
        self.read_only = []
        def backend(root, read_only, managers):
            self.read_only.append(read_only)
            return embedded_fixtures.FakeBackend(root, read_only, managers)
        self.dependencies = EmbeddedDependencies(renderer_factory=fixture.renderer_factory,
            backend_factory=backend,
            settings_factory=lambda *_: self.fail("View-only entered SettingsStore recovery"))
        self.remote_phase, self.phases = "running", []
        def remote(config, phase):
            self.assertIs(config, self.config)
            self.phases.append(phase)
            if phase == "return":
                self.remote_phase = "released"
            elif phase == "return-start":
                self.remote_phase = "return_requested"
            return {"phase": self.remote_phase, "candidate_sha256": self.session.candidate_sha256,
                    "case_sha256": self.session.case_sha256}
        self.remote = mock.patch("bridge.resident.experimental_check", side_effect=remote)
        self.remote.start()
        self.addCleanup(self.remote.stop)
        self.provider = fixture.provider_patch()
        self.provider.start()
        self.addCleanup(self.provider.stop)

    def runner(self, context=None):
        return EmbeddedRunner(context or self.context, health=self.health, dependencies=self.dependencies)

    def test_real_runner_reuses_display_input_and_source_models_then_authenticates_release(self):
        runner = self.runner()
        result = runner.run(max_frames=3, scripted_actions=("confirm", "search", "back"))
        self.assertEqual(result.reason, "classic")
        self.assertEqual(result.real_game_launches, 0)
        self.assertEqual(self.session.phase, "released")
        self.assertEqual(self.phases[0], "startup")
        self.assertEqual(self.phases[-1], "return")
        self.assertLess(self.phases.index("return-start"), self.phases.index("return"))
        self.assertEqual(self.read_only, [True])
        self.assertEqual(self.fixture.events.count("attach-existing-renderer"), 1)
        self.assertEqual(self.fixture.events.count("close-project-renderer"), 1)
        self.assertEqual(self.fixture.events.count("poll-existing-input"), 3)
        self.assertFalse(any("existing-device-run-game" == value for value in self.fixture.events))

    def test_actual_confirm_path_cannot_resolve_or_launch_a_game(self):
        runner = self.runner()
        runner.setup()
        runner._commands(runner.model.handle("confirm"))
        runner._commands(runner.model.handle("confirm"))
        dialog = runner.model.snapshot().dialog
        self.assertIsNotNone(dialog)
        self.assertFalse(any(choice.method == "game.launch" for choice in dialog.choices))
        self.assertIn("Game launch is unavailable in this view", dialog.message)
        # The hidden action is presentation only; direct dispatch must still
        # enforce the independent experimental authority boundary.
        with self.assertRaises(ContractError):
            runner.dispatcher.dispatch("game.launch", {"game_id": "fixture-game"})
        self.assertEqual(self.session.phase, "blocked")
        self.assertFalse(runner.release_for_fallback())
        self.assertNotIn("validate-existing-action", self.fixture.events)
        self.assertNotIn("existing-device-run-game", self.fixture.events)
        self.assertNotIn("return", self.phases)
        runner._close_project_renderer()

    def test_actual_favorite_action_is_denied_before_a_backend_write(self):
        runner = self.runner()
        with self.assertRaises(ContractError):
            runner.run(max_frames=4, scripted_actions=("confirm", "favorite"))
        self.assertEqual(self.session.phase, "blocked")
        self.assertNotIn("return", self.phases)

    def test_direct_dispatch_rejects_all_mutator_families_before_adapter_calls(self):
        requests = (("settings.preview", {}), ("settings.apply", {}), ("settings.undo", {}),
            ("controls.preview", {}), ("appearance.ppsspp.apply", {}), ("experience.ppsspp.apply", {}),
            ("hardware.apply", {}), ("game.launch", {"game_id": "fixture-game"}),
            ("tool.launch", {"tool_id": "route:apps"}), ("game.options", {"game_id": "fixture-game"}),
            ("spruce.advanced", {"route": "settings"}), ("library.favorite.set", {}),
            ("library.systems", {"refresh": True}), ("support.export", {}))
        for index, (method, params) in enumerate(requests):
            with self.subTest(method=method):
                self.config = make_fixture_configuration(self.fixture.card, role_name="method-%d" % index)
                self.session = self.config.experimental_session
                self.addCleanup(self.session.close)
                self.context = replace(self.context, experimental_session=self.session)
                self.remote_phase = "running"
                runner = self.runner()
                runner.setup()
                with self.assertRaises(ContractError):
                    runner.dispatcher.dispatch(method, params)
                self.assertEqual(self.session.phase, "blocked")
                self.assertFalse(runner.release_for_fallback())
                runner._close_project_renderer()

    def test_existing_preferences_navigation_and_incomplete_transactions_are_untouched(self):
        state = Path(self.config.state_dir)
        state.mkdir(parents=True, exist_ok=True)
        paths = (state / "settings.json", state / "navigation.json", state / "settings-transactions.json")
        for path in paths:
            path.write_bytes(b"owner sentinel: do not recover or overwrite")
        before = {path: path.read_bytes() for path in paths}
        self.runner().run(max_frames=1)
        self.assertEqual({path: path.read_bytes() for path in paths}, before)

    def test_advanced_route_and_live_emulator_adapters_are_not_exposed(self):
        bomb = SimpleNamespace(status=lambda: self.fail("Live emulator adapter entered"),
                               capabilities=lambda: self.fail("Live control adapter entered"))
        context = replace(self.context, theme_manager=bomb, control_adapter=bomb,
                          hardware_adapter=bomb, experience_manager=bomb)
        runner = self.runner(context)
        runner.setup()
        self.assertIsNone(runner.dispatcher.launch_bridge)
        self.assertIsNone(runner.dispatcher.control_adapter)
        self.assertIsNone(runner.dispatcher.hardware_adapter)
        with self.assertRaises(ContractError):
            runner.open_advanced("apps")
        self.assertNotIn("existing-menu:App", self.fixture.events)
        runner._close_project_renderer()

    def test_deadline_between_real_callbacks_uses_positive_release_without_claiming_classic_frame(self):
        original = self.context.display.present
        def present():
            original()
            self.remote_phase = "return_requested"
        self.context.display.present = present
        result = self.runner().run(max_frames=4)
        self.assertEqual(result.reason, "classic")
        self.assertEqual(self.session.phase, "released")
        self.assertEqual(self.fixture.events.count("present-existing-display"), 1)
        self.assertNotIn("classic-frame", self.fixture.events)

    def test_failed_renderer_or_input_does_not_allow_exception_fallback(self):
        def fail(**_):
            raise RuntimeError("synthetic source input error")
        self.context.controller.get_input = fail
        with self.assertRaises(ContractError) as caught:
            maybe_run_main_menu(self.fixture.main_menu, context=self.context, health=self.health,
                                dependencies=self.dependencies, max_frames=1)
        self.assertEqual(caught.exception.code, "UI_RELEASE_UNCERTAIN")
        self.assertEqual(self.session.phase, "blocked")
        self.assertNotIn("return", self.phases)

    def test_replaced_initialized_controller_blocks_before_next_frame(self):
        original = self.context.display.present
        def replace_controller():
            original()
            self.context.controller = embedded_fixtures.FakeController(self.fixture.events)
        self.context.display.present = replace_controller
        runner = self.runner()
        with self.assertRaises(ContractError):
            runner.run(max_frames=2)
        self.assertEqual(self.session.phase, "blocked")
        self.assertFalse(runner.release_for_fallback())

    def test_uncertain_quiescence_and_staged_symlink_cannot_report_release(self):
        original = self.context.display.present
        def stage():
            original()
            self.config.staged_command.symlink_to("/missing-command-target")
        self.context.display.present = stage
        runner = self.runner()
        with self.assertRaises(ContractError):
            runner.run(max_frames=1)
        self.assertEqual(self.session.phase, "blocked")
        self.assertTrue(self.config.staged_command.is_symlink())
        self.assertNotIn("return", self.phases)

    def test_project_selector_cannot_admit_a_plain_unqualified_context(self):
        context = replace(self.context, experimental_session=None, execution_environment="device")
        self.assertFalse(maybe_run_main_menu(self.fixture.main_menu, context=context, health=self.health,
                                            dependencies=self.dependencies, max_frames=1))
        self.assertFalse(self.phases)
        self.assertNotIn("attach-existing-renderer", self.fixture.events)

    def test_dead_prior_boot_attempt_is_preserved_before_any_private_admission(self):
        old = FrontendHealth(self.config.state_dir, boot_id="prior-boot")
        state = old.record()
        old.request("project", state["generation"])
        old.begin()
        fresh = FrontendHealth(self.config.state_dir)
        before = fresh.record()
        with self.assertRaises(ContractError) as caught:
            maybe_run_main_menu(self.fixture.main_menu, context=self.context, health=fresh,
                                dependencies=self.dependencies, max_frames=1)
        self.assertEqual(caught.exception.code, "EXPERIMENTAL_RECOVERY_REQUIRED")
        self.assertEqual(fresh.record(), before)
        self.assertFalse(self.phases)
        self.assertNotIn("attach-existing-renderer", self.fixture.events)

    def test_existing_classic_fallback_is_not_reset_to_start_a_private_case(self):
        attempt = self.health.begin()
        self.health.note_failure(attempt_id=attempt["attempt"]["id"])
        before = self.health.record()
        self.assertTrue(before["fallback_used"])
        with self.assertRaises(ContractError) as caught:
            maybe_run_main_menu(self.fixture.main_menu, context=self.context, health=self.health,
                                dependencies=self.dependencies, max_frames=1)
        self.assertEqual(caught.exception.code, "EXPERIMENTAL_RECOVERY_REQUIRED")
        self.assertEqual(self.health.record(), before)
        self.assertFalse(self.phases)
        self.assertNotIn("attach-existing-renderer", self.fixture.events)

    def test_recovery_change_during_source_checks_is_not_erased_by_a_fresh_generation_read(self):
        original = self.context.quiescent
        changed = False
        def racing_recovery():
            nonlocal changed
            if not changed:
                changed = True
                other = FrontendHealth(self.config.state_dir, boot_id="earlier-failed-boot")
                other.begin()
            return original()
        self.context.quiescent = racing_recovery
        with self.assertRaises(ContractError) as caught:
            maybe_run_main_menu(self.fixture.main_menu, context=self.context, health=self.health,
                                dependencies=self.dependencies, max_frames=1)
        self.assertEqual(caught.exception.code, "STALE_GENERATION")
        self.assertEqual(self.health.record()["attempt"]["boot_id"], "earlier-failed-boot")
        self.assertNotIn("attach-existing-renderer", self.fixture.events)


if __name__ == "__main__":
    unittest.main()
