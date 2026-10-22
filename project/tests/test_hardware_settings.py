# SPDX-License-Identifier: MIT
"""Existing-authority hardware actions; all positive qualification is synthetic."""
import ast
from contextlib import contextmanager, nullcontext
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from psp_shell.app import AppError, Dispatcher
from psp_shell.demo import DemoBackend
from psp_shell.hardware_settings import (FixedHardwareSettings, HardwareControl,
                                         HardwareSettingsError, unavailable_status)
from psp_shell.settings import SettingsStore
from psp_shell.ui.model import NavigationModel


class HardwareSettingsTests(unittest.TestCase):
    def setUp(self):
        self.values = {"backlight": 5, "volume": 40, "wifi": False, "bluetooth": False}
        self.calls = []
        self.qualified = True
        self.owner = object()
        self.current = self.owner
        def step(name, delta):
            self.calls.append((name, delta))
            self.values[name] += delta
        self.device = SimpleNamespace(
            lumination=lambda: self.values["backlight"], lower_lumination=lambda: step("backlight", -1),
            raise_lumination=lambda: step("backlight", 1), get_display_volume=lambda: self.values["volume"],
            volume_down=lambda: step("volume", -5), volume_up=lambda: step("volume", 5),
            is_wifi_enabled=lambda: self.values["wifi"],
            enable_wifi=lambda: self.values.__setitem__("wifi", True),
            disable_wifi=lambda: self.values.__setitem__("wifi", False),
            note_wifi_change=lambda: self.calls.append(("wifi", "invalidate")),
            is_bluetooth_enabled=lambda: self.values["bluetooth"],
            enable_bluetooth=lambda: self.values.__setitem__("bluetooth", True),
            disable_bluetooth=lambda: self.values.__setitem__("bluetooth", False))
        self.current = self.device
        self.adapter = FixedHardwareSettings.from_initialized_device(self.device,
            qualified=lambda: self.qualified, write_window=nullcontext, current_device=lambda: self.current)

    def preview(self, control="backlight", operation="raise"):
        return self.adapter.preview({"control_id": control, "operation": operation,
                                     "expected_generation": self.adapter.generation})

    def apply(self, preview, request="fixture-request"):
        return self.adapter.apply({"preview_id": preview["preview_id"], "request_id": request,
                                   "expected_generation": preview["generation"]})

    def test_default_and_unqualified_readings_do_not_invent_values_or_changes(self):
        status = unavailable_status()
        self.assertTrue(all(row["value"] is None and not row["writable"] for row in status["controls"]))
        self.qualified = False
        status = self.adapter.status()
        self.assertTrue(all(not row["writable"] for row in status["controls"]))
        self.assertEqual(self.calls, [])
        with self.assertRaises(HardwareSettingsError):
            self.preview()
        with self.assertRaises(HardwareSettingsError):
            self.adapter.route({"route_id": "power"})

    def test_missing_shared_window_and_unknown_reading_refuse_writes(self):
        adapter = FixedHardwareSettings.from_initialized_device(self.device, qualified=lambda: True)
        self.assertFalse(adapter.status()["controls"][0]["writable"])
        with self.assertRaises(HardwareSettingsError):
            adapter.preview({"control_id": "backlight", "operation": "raise", "expected_generation": 0})
        self.values["backlight"] = True
        self.assertIsNone(self.adapter.status()["controls"][0]["value"])
        with self.assertRaises(HardwareSettingsError):
            self.preview()

    def test_review_apply_and_retry_use_exact_existing_handler_once(self):
        preview = self.preview()
        self.assertEqual(self.calls, [])
        result = self.apply(preview)
        self.assertEqual(result["value"], 6)
        self.assertTrue(result["configuration_observed"])
        self.assertFalse(result["physical_effect_verified"])
        self.assertEqual(self.apply(preview), result)
        self.assertEqual(self.calls, [("backlight", 1)])
        with self.assertRaises(HardwareSettingsError) as caught:
            self.adapter.apply({"preview_id": "other", "request_id": "fixture-request", "expected_generation": 0})
        self.assertEqual(caught.exception.code, "REQUEST_CONFLICT")

    def test_changed_owner_and_external_edit_block_before_action(self):
        preview = self.preview()
        self.values["backlight"] = 8
        with self.assertRaises(HardwareSettingsError) as caught:
            self.apply(preview)
        self.assertEqual(caught.exception.code, "HARDWARE_CONFLICT")
        self.assertEqual(self.calls, [])
        self.current = object()
        with self.assertRaises(HardwareSettingsError) as caught:
            self.adapter.status()
        self.assertEqual(caught.exception.code, "OWNER_CHANGED")

    def test_lost_qualification_and_expired_preview_do_not_write(self):
        preview = self.preview()
        self.qualified = False
        with self.assertRaises(HardwareSettingsError):
            self.apply(preview)
        self.qualified = True
        self.adapter.clock = lambda: 1e20
        with self.assertRaises(HardwareSettingsError) as caught:
            self.apply(preview)
        self.assertEqual(caught.exception.code, "STALE_HARDWARE_PREVIEW")
        self.assertEqual(self.calls, [])

    def test_observer_cannot_replace_the_owner_between_preflight_and_write(self):
        replace = False
        def read():
            if replace:
                self.current = object()
            return self.values["backlight"]
        self.adapter.controls["backlight"] = HardwareControl("backlight", "Brightness", "display", read,
            lambda: self.calls.append("lower"), lambda: self.calls.append("raise"), maximum=10)
        preview = self.preview()
        replace = True
        with self.assertRaises(HardwareSettingsError) as caught:
            self.apply(preview)
        self.assertEqual(caught.exception.code, "OWNER_CHANGED")
        self.assertEqual(self.calls, [])

    def test_async_radio_and_volume_acknowledgement_never_claim_physical_completion(self):
        for control, operation in (("wifi", "toggle"), ("bluetooth", "toggle"), ("volume", "raise")):
            result = self.apply(self.preview(control, operation), "fixture-" + control)
            self.assertTrue(result["asynchronous"])
            self.assertFalse(result["physical_effect_verified"])
        self.assertIn(("wifi", "invalidate"), self.calls)
        self.assertEqual(self.values["volume"], 45)

    def test_queued_handler_without_immediate_readback_is_not_reported_saved(self):
        adapter = FixedHardwareSettings([HardwareControl("volume", "Volume", "sound", lambda: 40,
            lambda: self.calls.append("lower"), lambda: self.calls.append("raise"), asynchronous=True)],
            qualified=lambda: True, write_window=nullcontext)
        preview = adapter.preview({"control_id": "volume", "operation": "raise", "expected_generation": 0})
        result = adapter.apply({"preview_id": preview["preview_id"], "request_id": "queued", "expected_generation": 0})
        self.assertTrue(result["operation_accepted"])
        self.assertFalse(result["configuration_observed"])
        self.assertFalse(result["physical_effect_verified"])

    def test_partial_handler_failure_and_window_close_failure_are_not_retried(self):
        def failed():
            self.calls.append("attempt")
            raise OSError("synthetic failure after existing event")
        @contextmanager
        def failed_close():
            yield
            raise OSError("synthetic release failure")
        for callback, window in ((failed, nullcontext), (lambda: self.calls.append("attempt"), failed_close)):
            self.calls.clear()
            adapter = FixedHardwareSettings([HardwareControl("volume", "Volume", "sound", lambda: 40,
                lambda: None, callback)], qualified=lambda: True, write_window=window)
            preview = adapter.preview({"control_id": "volume", "operation": "raise", "expected_generation": 0})
            params = {"preview_id": preview["preview_id"], "request_id": "uncertain", "expected_generation": 0}
            for _ in range(2):
                with self.assertRaises(HardwareSettingsError) as caught:
                    adapter.apply(params)
                self.assertEqual(caught.exception.code, "HARDWARE_OUTCOME_UNCERTAIN")
            self.assertEqual(self.calls, ["attempt"])

    def test_backlight_limits_and_hostile_fields_are_rejected(self):
        self.values["backlight"] = 10
        with self.assertRaises(HardwareSettingsError) as caught:
            self.preview()
        self.assertEqual(caught.exception.code, "SETTING_BOUNDARY")
        for params in ({"control_id": [], "operation": "raise", "expected_generation": 0},
                       {"control_id": "backlight", "operation": "raise", "expected_generation": 0, "shell": "poweroff"}):
            with self.assertRaises(HardwareSettingsError):
                self.adapter.preview(params)
        with self.assertRaises(HardwareSettingsError):
            self.adapter.route({"route_id": "../../App/USB/launch.sh"})
        self.assertEqual(self.calls, [])

    def test_source_routes_remain_typed_and_do_not_execute_device_commands(self):
        self.assertEqual(self.adapter.route({"route_id": "wifi"})["route"], "wifi")
        self.assertEqual(self.adapter.route({"route_id": "bluetooth"})["route"], "bluetooth")
        self.assertEqual(self.adapter.route({"route_id": "usb"})["route"], "apps")
        self.assertEqual(self.adapter.route({"route_id": "controllers"})["route"], "settings")
        self.assertEqual(self.calls, [])


class CommonSettingsFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dispatcher = Dispatcher(DemoBackend(), SettingsStore(self.root / "settings"), self.root / "support")
        self.model = NavigationModel()
        for command in self.model.initial_commands():
            self.model.receive(command, self.dispatcher.dispatch(command.method, dict(command.params)))
        self.model.category = 3

    def select(self, identifier):
        for _ in range(len(self.model.snapshot().items)):
            if self.model.snapshot().selected_item.id == identifier:
                return
            self.model.handle("down")
        self.fail("missing setting " + identifier)

    def test_all_common_groups_are_reachable_and_return_to_the_parent_focus(self):
        for group in ("display", "sound", "network", "controllers", "power"):
            self.select("hardware_" + group)
            command = self.model.handle("confirm")[0]
            self.model.receive(command, self.dispatcher.dispatch(command.method, dict(command.params)))
            self.assertIn(group.title().split()[0], self.model.snapshot().breadcrumb)
            self.assertTrue(self.model.snapshot().items)
            self.model.handle("back")
            self.assertEqual(self.model.snapshot().selected_item.id, "hardware_" + group)

    def test_unqualified_common_setting_offers_classic_without_an_apply_request(self):
        self.select("hardware_network")
        command = self.model.handle("confirm")[0]
        self.model.receive(command, self.dispatcher.dispatch(command.method))
        self.assertEqual(self.model.handle("confirm"), [])
        self.assertEqual(self.model.snapshot().dialog.selected, 1)
        self.assertIn("unavailable", self.model.snapshot().dialog.title.lower())

    def test_dispatcher_never_executes_route_in_standalone_or_after_accepted_launch(self):
        for method in ("hardware.preview", "hardware.apply", "hardware.route", "experience.ppsspp.apply"):
            with self.assertRaises(AppError):
                self.dispatcher.dispatch(method, {})
        self.dispatcher.pending_launch = {"action_id": "trusted", "mode": "normal"}
        with self.assertRaises(AppError) as caught:
            self.dispatcher.dispatch("hardware.status")
        self.assertEqual(caught.exception.code, "BUSY_HANDOFF")

    def test_combined_matching_uses_current_frontend_choices_and_warns_per_game_overrides(self):
        self.select("experience")
        command = self.model.handle("confirm")[0]
        self.model.receive(command, {"profile_id": "qualified-fixture", "generation": 4, "adoption_available": True})
        preview = self.model.handle("confirm")[0]
        self.assertEqual(preview.method, "experience.ppsspp.preview")
        self.assertEqual(preview.params["confirm"], self.model.preferences.confirm)
        self.assertEqual(preview.params["expected_generation"], 4)
        self.model.receive(preview, {"preview_id": "fixture", "adoption_available": True,
            "diff": [{"key": "NativeMenuConfirm", "before": "east", "after": "south"}],
            "per_game_overrides": [{"path": "fixture", "overrides": ["NativeMenuConfirm"]}]})
        self.assertEqual(self.model.snapshot().dialog.selected, 1)
        self.assertIn("take precedence", self.model.snapshot().dialog.message)
        self.model.handle("up")
        apply = self.model.handle("confirm")[0]
        self.assertEqual(apply.method, "experience.ppsspp.apply")
        follow = self.model.receive(apply, {"transaction_id": "joined", "generation": 5})
        self.assertEqual(follow[0].method, "experience.ppsspp.status")

    def test_game_options_require_a_trusted_scheduler_and_preserve_frontend_lifecycle(self):
        self.assertFalse(self.dispatcher.dispatch("system.capabilities")["game_options"])
        with self.assertRaises(AppError):
            self.dispatcher.dispatch("game.options", {"game_id": "fixture"})
        calls = []
        self.dispatcher.game_options_handler = lambda identifier: calls.append(identifier) or {"state": "releasing_ui"}
        capability = next(command for command in self.model.initial_commands() if command.context == "capabilities")
        self.model.receive(capability, self.dispatcher.dispatch("system.capabilities"))
        self.model.category = 0
        self.model.set_category_items(0, [{"id": "fixture", "display_name": "Fixture", "available": True}])
        self.model.handle("confirm")
        self.assertIn("Game options", [choice.title for choice in self.model.snapshot().dialog.choices])
        self.model.handle("down")
        command = self.model.handle("confirm")[0]
        self.assertEqual(command.method, "game.options")
        self.assertEqual(command.params, {"game_id": "fixture"})
        self.model.receive(command, self.dispatcher.dispatch(command.method, dict(command.params)))
        self.assertEqual(calls, ["fixture"])
        self.assertIsNone(self.model.exit_request)


class ExistingSourceHardwareAcceptance(unittest.TestCase):
    def test_actual_pinned_backlight_callbacks_are_the_only_write_authority(self):
        root = Path(os.environ.get("SPRUCE_SOURCE_ROOT", "/workspace/spruce-base"))
        path = root / "App/PyUI/main-ui/devices/device_common.py"
        if not path.is_file():
            self.skipTest("Set SPRUCE_SOURCE_ROOT to the untouched pinned spruce source")
        raw = path.read_bytes()
        expected = "2a557b1637370ae8da2d78551ffd7a96e9c118d6"
        self.assertEqual(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(), expected)
        tree = ast.parse(raw)
        owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DeviceCommon")
        functions = [node for node in owner.body if isinstance(node, ast.FunctionDef)
                     and node.name in {"lumination", "raise_lumination", "lower_lumination"}]
        namespace = {}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
        calls = []
        config = SimpleNamespace(backlight=5, reload_config=lambda: calls.append("reload"),
                                 save_config=lambda: calls.append("save"))
        config.set_backlight = lambda value: setattr(config, "backlight", value)
        device = SimpleNamespace(system_config=config, _set_lumination_to_config=lambda: calls.append("existing-device-write"))
        for name in ("lumination", "raise_lumination", "lower_lumination"):
            setattr(device, name, namespace[name].__get__(device))
        adapter = FixedHardwareSettings.from_initialized_device(device, qualified=lambda: True, write_window=nullcontext)
        preview = adapter.preview({"control_id": "backlight", "operation": "raise", "expected_generation": 0})
        self.assertEqual(calls, [])
        result = adapter.apply({"preview_id": preview["preview_id"], "request_id": "source-fixture", "expected_generation": 0})
        self.assertEqual(calls, ["reload", "save", "existing-device-write"])
        self.assertEqual(result["value"], 6)
        self.assertFalse(result["physical_effect_verified"])


if __name__ == "__main__":
    unittest.main()
