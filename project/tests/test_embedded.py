"""Injected PyUI-context proof. No upstream code or device services execute."""
import builtins
from dataclasses import replace
from enum import Enum
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from bridge.pyui_entry import maybe_run_main_menu, stage_main_menu_hook
from psp_shell.embedded import EmbeddedContext, EmbeddedDependencies, EmbeddedRunner, logical_action, qualification
from psp_shell.health import FrontendHealth
from psp_shell.runtime import ContractError, LaunchState


class FakeDisplay:
    def __init__(self, events):
        self.events = events
        self.renderer = SimpleNamespace(renderer=object())
        self.window = SimpleNamespace(window=object())
        self.render_canvas = object()
    def present(self):
        self.events.append("present-existing-display")
    def init(self):
        raise AssertionError("second display init")
    def deinit_display(self):
        raise AssertionError("embedded runner must not globally deinitialize PyUI")


class FakeController:
    def __init__(self, events):
        self.events = events
    def still_held_down(self):
        return False
    def clear_input_queue(self):
        self.events.append("clear-existing-input")
    def clear_last_input(self):
        self.events.append("clear-last-input")
    def get_input(self, timeout):
        self.events.append("poll-existing-input")
        return False
    def last_input(self):
        return None
    def init(self):
        raise AssertionError("second input initialization")
    def close(self):
        raise AssertionError("unowned input closed")


class FakeBackend:
    def __init__(self, root, read_only, managers):
        self.device = managers.device
        self.events = managers.events
    def systems(self):
        return []
    def recent(self):
        return []
    def favorites(self):
        return []
    def tools(self):
        return []
    def games(self, *args, **kwargs):
        return {"items": [{"game_id": "fixture-game", "display_name": "Original fixture", "system_id": "PSP"}], "total": 1, "offset": 0}
    def resolve_game(self, game_id, preset_id, mode):
        return {"launchable": True, "action_id": "game:fixture", "game_id": game_id}
    def validate_action(self, action_id, mode):
        self.events.append("validate-existing-action")
        if action_id != "game:fixture":
            raise ContractError("UNKNOWN_ACTION", "not registered")
    def execute_action(self, action_id, mode, release_ui=True):
        if release_ui:
            raise AssertionError("provider cleanup would run a second time")
        self.events.append("execute-without-duplicate-release")
        self.device.run_game(SimpleNamespace(game_id="fixture-game"))


class EmbeddedTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.card = self.root / "card"
        self.card.mkdir()
        self.events = []
        self.exit_game = False
        def run_game(_):
            self.events.append("existing-device-run-game")
            if self.exit_game:
                raise SystemExit(0)
        self.device = SimpleNamespace(run_game=run_game)
        self.display = FakeDisplay(self.events)
        self.controller = FakeController(self.events)
        self.main_menu = SimpleNamespace(launch_selection=lambda value: self.events.append("existing-menu:" + value))
        self.context = EmbeddedContext(self.card, self.root / "state", self.device, self.display,
            self.controller, self.main_menu, {"live": False},
            {"execution_environment": "host-fixture", "id": "host-fixture-embedded"}, {},
            lambda: True, lambda: self.events.append("stop-project-work"), execution_environment="host-fixture",
            release_input=lambda: self.events.append("release-project-input"),
            restore_input=lambda: self.events.append("restore-project-input"))
        self.health = FrontendHealth(self.context.state_dir, boot_id="embedded-fixture")
        self.health.request("project", 0)
        outer = self
        class Renderer:
            def __init__(self, width, height, **kwargs):
                outer.assertEqual((width, height), (1280, 720))
                outer.assertFalse(kwargs["own_resources"])
                outer.assertIs(kwargs["external_renderer"], outer.display.renderer.renderer)
                outer.assertIs(kwargs["external_window"], outer.display.window.window)
                outer.assertIs(kwargs["external_target"], outer.display.render_canvas)
                outer.events.append("attach-existing-renderer")
                self.closed = False
            def render(self, snapshot, now):
                outer.events.append("render-project-frame")
            def close(self):
                outer.assertFalse(self.closed, "project renderer closed more than once")
                self.closed = True
                outer.events.append("close-project-renderer")
        self.renderer_factory = Renderer
        self.dependencies = EmbeddedDependencies(renderer_factory=Renderer, backend_factory=FakeBackend)

    def provider_patch(self):
        # Prove the production path binds from_pyui; it never constructs a
        # second set of favorites/recents/controller objects in the fixture.
        return patch("psp_shell.adapters.spruce.PyUIModelProvider.from_pyui",
                     return_value=SimpleNamespace(device=self.device, events=self.events))

    def test_first_frame_readiness_uses_existing_display_and_controller(self):
        runner = EmbeddedRunner(self.context, health=self.health, dependencies=self.dependencies)
        with self.provider_patch() as provider:
            result = runner.run(max_frames=1)
        self.assertEqual(result.reason, "frame_limit")
        self.assertEqual(result.evidence, "host-fixture")
        self.assertEqual(result.real_game_launches, 0)
        self.assertTrue(all(self.health.record()["readiness"].values()))
        self.assertEqual(self.events.count("present-existing-display"), 1)
        self.assertEqual(self.events.count("attach-existing-renderer"), 1)
        self.assertEqual(self.events.count("close-project-renderer"), 1)
        self.assertIs(provider.call_args.kwargs["device"], self.device)

    def test_control_adapter_is_passed_through_without_direct_writes(self):
        adapter = SimpleNamespace(capabilities=lambda: {"evidence": "fixture-read-only"})
        runner = EmbeddedRunner(replace(self.context, control_adapter=adapter),
                                health=self.health, dependencies=self.dependencies)
        with self.provider_patch():
            runner.run(max_frames=1)
        self.assertIs(runner.dispatcher.control_adapter, adapter)
        self.assertEqual(runner.dispatcher.dispatch("controls.capabilities", {}),
                         {"evidence": "fixture-read-only"})

    def test_failed_initial_input_poll_cannot_commit_readiness(self):
        self.controller.get_input = lambda **_: (_ for _ in ()).throw(RuntimeError("input fixture unavailable"))
        runner = EmbeddedRunner(self.context, health=self.health, dependencies=self.dependencies)
        with self.provider_patch(), self.assertRaises(RuntimeError):
            runner.run(max_frames=1, scripted_actions=("right",))
        self.assertFalse(runner.ready)
        self.assertFalse(any(self.health.record()["readiness"].values()))
        self.assertEqual(self.events.count("present-existing-display"), 1)

    def test_interrupted_start_delegates_classic_without_fake_readiness(self):
        self.health.begin()
        restart = FrontendHealth(self.context.state_dir, boot_id="embedded-fixture",
                                 process_alive=lambda *_: False)
        with self.provider_patch() as provider:
            self.assertFalse(maybe_run_main_menu(self.main_menu, context=self.context,
                                                health=restart, dependencies=self.dependencies))
            provider.assert_not_called()
        record = restart.record()
        self.assertEqual(record["stable"], "classic")
        self.assertIsNone(record["attempt"])
        self.assertTrue(record["fallback_used"])
        self.assertFalse(any(record["readiness"].values()))

    def test_game_handoff_order_and_existing_exit_are_preserved(self):
        self.exit_game = True
        runner = EmbeddedRunner(self.context, health=self.health, dependencies=self.dependencies)
        with self.provider_patch(), self.assertRaises(SystemExit):
            runner.run(max_frames=6, scripted_actions=("confirm", "confirm", "confirm"))
        self.assertEqual(runner.coordinator.state, LaunchState.DELEGATED)
        names = self.events
        self.assertLess(names.index("stop-project-work"), names.index("close-project-renderer"))
        self.assertLess(names.index("close-project-renderer"), names.index("release-project-input"))
        self.assertLess(names.index("release-project-input"), names.index("execute-without-duplicate-release"))
        self.assertLess(names.index("execute-without-duplicate-release"), names.index("existing-device-run-game"))
        self.assertEqual(names.count("close-project-renderer"), 1)
        self.assertEqual(names.count("existing-device-run-game"), 1)
        with self.assertRaises(ContractError):
            self.health.choose_interface()

    def test_partially_failed_input_release_restores_both_existing_owners(self):
        def release():
            self.events.append("partial-input-release")
            raise RuntimeError("injected partial release")
        context = replace(self.context, release_input=release,
            restore_background_tasks=lambda: self.events.append("restore-existing-background"))
        runner = EmbeddedRunner(context, health=self.health, dependencies=self.dependencies)
        with self.provider_patch(), self.assertRaises(ContractError) as caught:
            runner.run(max_frames=6, scripted_actions=("confirm", "confirm", "confirm"))
        self.assertEqual(caught.exception.code, "PREPARATION_FAILED")
        self.assertIn("restore-project-input", self.events)
        self.assertIn("restore-existing-background", self.events)
        self.assertNotIn("existing-device-run-game", self.events)
        self.assertEqual(runner.coordinator.state, LaunchState.IDLE)

    def test_partially_failed_background_stop_runs_paired_restore(self):
        def stop():
            self.events.append("partial-background-stop")
            raise RuntimeError("injected partial stop")
        context = replace(self.context, stop_background_tasks=stop,
            restore_background_tasks=lambda: self.events.append("restore-existing-background"))
        runner = EmbeddedRunner(context, health=self.health, dependencies=self.dependencies)
        with self.provider_patch(), self.assertRaises(ContractError) as caught:
            runner.run(max_frames=6, scripted_actions=("confirm", "confirm", "confirm"))
        self.assertEqual(caught.exception.code, "PREPARATION_FAILED")
        self.assertIn("restore-existing-background", self.events)
        self.assertNotIn("release-project-input", self.events)
        self.assertNotIn("existing-device-run-game", self.events)
        self.assertEqual(runner.coordinator.state, LaunchState.IDLE)

    def test_owner_replacement_during_background_stop_blocks_launch_and_fallback(self):
        valid = [True]
        def owners():
            if not valid[0]:
                raise ContractError("OWNER_CHANGED", "injected owner replacement")
        def stop():
            valid[0] = False
        context = replace(self.context, stop_background_tasks=stop, assert_owners=owners)
        runner = EmbeddedRunner(context, health=self.health, dependencies=self.dependencies)
        with self.provider_patch(), self.assertRaises(ContractError):
            runner.run(max_frames=6, scripted_actions=("confirm", "confirm", "confirm"))
        self.assertEqual(runner.coordinator.state, LaunchState.BLOCKED)
        self.assertFalse(runner.release_for_fallback())
        self.assertNotIn("existing-device-run-game", self.events)

    def test_owner_replacement_after_frame_blocks_classic_fallback(self):
        valid = [True]
        def owners():
            if not valid[0]:
                raise ContractError("OWNER_CHANGED", "injected owner replacement")
        context = replace(self.context, assert_owners=owners)
        runner = EmbeddedRunner(context, health=self.health, dependencies=self.dependencies)
        with self.provider_patch():
            runner.run(max_frames=1)
        valid[0] = False
        self.assertFalse(runner.release_for_fallback())

    def test_renderer_has_no_unconditional_pillow_dependency(self):
        imported = builtins.__import__
        def no_pillow(name, *args, **kwargs):
            if name == "PIL" or name.startswith("PIL."):
                raise AssertionError("embedded runner imported desktop Pillow backend")
            return imported(name, *args, **kwargs)
        with self.provider_patch(), patch("builtins.__import__", side_effect=no_pillow):
            result = EmbeddedRunner(self.context, health=self.health, dependencies=self.dependencies).run(max_frames=1)
        self.assertTrue(result.first_frame)

    def test_missing_optional_renderer_falls_back_without_destroying_existing_display(self):
        def missing(*args, **kwargs):
            raise ModuleNotFoundError("optional rasterizer is missing")
        dependencies = replace(self.dependencies, renderer_factory=missing)
        with self.provider_patch():
            handled = maybe_run_main_menu(self.main_menu, context=self.context, health=self.health,
                                         dependencies=dependencies, max_frames=1)
        self.assertFalse(handled)
        self.assertEqual(self.health.choose_interface(), "classic")
        self.assertIsNotNone(self.display.renderer)
        self.assertNotIn("existing-device-run-game", self.events)

    def test_force_classic_and_future_selector_do_not_import_optional_view(self):
        self.health.set_force_classic()
        with self.provider_patch() as provider:
            self.assertFalse(maybe_run_main_menu(self.main_menu, context=self.context, health=self.health,
                                                dependencies=self.dependencies))
            provider.assert_not_called()
        self.assertEqual(self.events, [])
        self.health.set_force_classic(False)
        value = self.health.record()
        value["schema"] = 2
        value.pop("checksum")
        canonical = lambda v: json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        value["checksum"] = hashlib.sha256(canonical(value)).hexdigest()
        self.health.primary.write_bytes(canonical(value))
        before = self.health.primary.read_bytes()
        self.assertFalse(maybe_run_main_menu(self.main_menu, context=self.context, health=self.health,
                                            dependencies=self.dependencies))
        self.assertEqual(self.health.primary.read_bytes(), before)
        self.assertEqual(self.events, [])

    def test_sameboot_foreground_uncertainty_blocks_classic_entry(self):
        self.health.begin_foreground("fixture-game")
        self.health.set_force_classic()
        with self.assertRaises(ContractError) as caught:
            maybe_run_main_menu(self.main_menu, context=self.context, health=self.health,
                                dependencies=self.dependencies)
        self.assertEqual(caught.exception.code, "FOREGROUND_UNCERTAIN")
        self.assertEqual(self.events, [])

    def test_unqualified_device_cannot_reuse_the_host_fixture_switch(self):
        device = replace(self.context, execution_environment="device",
                         profile={"source_use_verified": False, "hardware_qualified": False, "runtime_verified": False})
        with self.provider_patch() as provider:
            self.assertFalse(maybe_run_main_menu(self.main_menu, context=device, health=self.health,
                                                dependencies=self.dependencies))
            provider.assert_not_called()
        with self.assertRaises(ContractError):
            qualification(replace(self.context, sd_root="/mnt/SDCARD"))

    def test_advanced_settings_delegates_only_existing_menu_values(self):
        runner = EmbeddedRunner(self.context, health=self.health, dependencies=self.dependencies)
        with self.provider_patch():
            runner.run(max_frames=1)
            runner.open_advanced("settings")
            with self.assertRaises(ContractError):
                runner.open_advanced("poweroff")
            runner.release_for_fallback()
        self.assertIn("existing-menu:Setting", self.events)
        self.assertNotIn("existing-device-run-game", self.events)

    def test_failed_advanced_owner_restore_blocks_retry_and_classic_fallback(self):
        def restore():
            self.events.append("failed-owner-restore")
            raise RuntimeError("injected partial restore")
        context = replace(self.context, restore_background_tasks=restore)
        runner = EmbeddedRunner(context, health=self.health, dependencies=self.dependencies)
        with self.provider_patch():
            runner.run(max_frames=1)
            with self.assertRaises(RuntimeError):
                runner.open_advanced("settings")
            self.assertFalse(runner.release_for_fallback())
        self.assertEqual(self.events.count("failed-owner-restore"), 1)
        self.assertIsNone(runner.renderer)

    def test_advanced_menu_game_exit_also_preserves_foreground_uncertainty(self):
        def existing_menu(_):
            raise SystemExit(0)
        self.main_menu.launch_selection = existing_menu
        runner = EmbeddedRunner(self.context, health=self.health, dependencies=self.dependencies)
        with self.provider_patch():
            runner.run(max_frames=1)
            with self.assertRaises(SystemExit):
                runner.open_advanced("apps")
        self.assertFalse(runner.release_for_fallback())
        with self.assertRaises(ContractError) as caught:
            self.health.assert_no_foreground()
        self.assertEqual(caught.exception.code, "FOREGROUND_UNCERTAIN")

    def test_physical_confirm_respects_unique_existing_logical_swap(self):
        class Buttons(Enum):
            A = 1
            B = 2
            X = 3
            Y = 4
        device = SimpleNamespace(button_remapper=SimpleNamespace(get_mappping=lambda button:
            {Buttons.A: Buttons.B, Buttons.B: Buttons.A}.get(button, button)))
        prefs = SimpleNamespace(confirm="south")
        self.assertEqual(logical_action(Buttons.A, prefs, device), "confirm")
        self.assertEqual(logical_action(Buttons.B, prefs, device), "back")
        device.button_remapper.get_mappping = lambda button: Buttons.A if button in {Buttons.A, Buttons.B} else button
        with self.assertRaises(ContractError):
            logical_action(Buttons.A, prefs, device)

    def test_keyboard_shortcuts_respect_confirm_preferences_and_inverse_remaps(self):
        class Buttons(Enum):
            A = 1
            B = 2
            X = 3
            Y = 4
        for confirm in ("south", "east"):
            for swapped in (False, True):
                with self.subTest(confirm=confirm, swapped=swapped):
                    mapping = {Buttons.A: Buttons.B, Buttons.B: Buttons.A,
                               Buttons.X: Buttons.Y, Buttons.Y: Buttons.X} if swapped else {}
                    remap = lambda button: mapping.get(button, button)
                    device = SimpleNamespace(button_remapper=SimpleNamespace(get_mappping=remap))
                    preferences = SimpleNamespace(confirm=confirm)
                    self.assertEqual(logical_action(remap(Buttons.X), preferences, device, text_mode=True), "delete_text")
                    self.assertEqual(logical_action(remap(Buttons.Y), preferences, device, text_mode=True), "submit_text")
                    self.assertEqual(logical_action(remap(Buttons.X), preferences, device), "search")
                    self.assertEqual(logical_action(remap(Buttons.Y), preferences, device), "favorite")
                    physical = Buttons.B if confirm == "south" else Buttons.A
                    self.assertEqual(logical_action(remap(physical), preferences, device, text_mode=True), "confirm")
        device.button_remapper.get_mappping = lambda button: Buttons.X if button in {Buttons.X, Buttons.Y} else button
        with self.assertRaises(ContractError):
            logical_action(Buttons.X, preferences, device, text_mode=True)

    def test_existing_controller_deletes_and_submits_the_open_keyboard(self):
        class Buttons(Enum):
            A = 1
            B = 2
            X = 3
            Y = 4
        for confirm in ("south", "east"):
            for swapped in (False, True):
                with self.subTest(confirm=confirm, swapped=swapped):
                    mapping = {Buttons.A: Buttons.B, Buttons.B: Buttons.A,
                               Buttons.X: Buttons.Y, Buttons.Y: Buttons.X} if swapped else {}
                    remap = lambda button: mapping.get(button, button)
                    self.device.button_remapper = SimpleNamespace(get_mappping=remap)
                    physical_confirm = Buttons.B if confirm == "south" else Buttons.A
                    inputs = iter(remap(button) for button in
                                  (Buttons.X, physical_confirm, Buttons.X, physical_confirm, Buttons.Y))
                    current = [None]
                    def poll(timeout):
                        current[0] = next(inputs, None)
                        return current[0] is not None
                    self.controller.get_input = poll
                    self.controller.last_input = lambda: current[0]
                    context = replace(self.context, state_dir=self.root / ("keyboard-" + confirm + str(swapped)))
                    health = FrontendHealth(context.state_dir, boot_id="embedded-keyboard-fixture")
                    health.request("project", 0)
                    queries = []
                    class Backend(FakeBackend):
                        def games(self, *args, **kwargs):
                            queries.append(kwargs.get("search"))
                            return super().games(*args, **kwargs)
                    dependencies = replace(self.dependencies, backend_factory=Backend,
                        settings_factory=lambda path: SimpleNamespace(recover=lambda: None,
                            get=lambda: {"generation": 0, "preferences": {"confirm": confirm}}))
                    runner = EmbeddedRunner(context, health=health, dependencies=dependencies)
                    with self.provider_patch():
                        result = runner.run(max_frames=5)
                    self.assertIsNone(runner.model.snapshot().keyboard)
                    self.assertEqual(queries, ["A"])
                    self.assertEqual(result.real_game_launches, 0)

    def test_source_patch_stages_only_after_hash_and_source_use_gate(self):
        root = self.root / "original-fixture-source"
        source = root / "App/PyUI/main-ui/menus/main_menu.py"
        source.parent.mkdir(parents=True)
        raw = (b"class MainMenu:\n    def run_main_menu_selection(self):\n"
               b"        self.check_for_gameswitcher()\n        self.check_for_boxart_resizing()\n"
               b"        return 'original fixture'\n")
        source.write_bytes(raw)
        with self.assertRaises(ContractError) as caught:
            stage_main_menu_hook(root, self.root / "staged")
        self.assertEqual(caught.exception.code, "SOURCE_USE_UNVERIFIED")
        with self.assertRaises(ContractError):
            stage_main_menu_hook(root, self.root / "staged", source_use_verified=True)
        digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        # Synthetic source is original test code; no upstream derivative is
        # produced and this mock cannot enable a production staging override.
        with patch("bridge.pyui_entry.MAIN_MENU_BLOB", digest):
            record = stage_main_menu_hook(root, self.root / "staged", source_use_verified=True)
        self.assertEqual(source.read_bytes(), raw)
        self.assertFalse(record["hardware_execution_enabled"])
        staged = (self.root / "staged/0001-pyui-main-menu-psp-seam.patch").read_text()
        self.assertIn("except (ImportError, SyntaxError)", staged)
        self.assertIn("maybe_run_main_menu(self)", staged)
        self.assertLess(staged.index("self.check_for_gameswitcher()"),
                        staged.index("maybe_run_main_menu(self)"))
        self.assertLess(staged.index("self.check_for_boxart_resizing()"),
                        staged.index("maybe_run_main_menu(self)"))


if __name__ == "__main__":
    unittest.main()
