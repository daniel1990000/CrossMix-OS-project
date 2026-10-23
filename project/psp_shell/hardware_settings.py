"""Common controls bound to existing initialized spruce authorities.

No device, worker, input descriptor or command is created here. The source
bootstrap supplies the existing owner, its qualification check and shared
write window. Read-back observes configuration, never physical radio/audio or
power completion. SPDX-License-Identifier: MIT
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import copy
import threading
import time
from typing import Callable
import uuid


class HardwareSettingsError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class HardwareControl:
    id: str
    label: str
    group: str
    read: Callable
    lower: Callable | None = None
    raise_: Callable | None = None
    enable: Callable | None = None
    disable: Callable | None = None
    kind: str = "step"
    maximum: int | None = None
    asynchronous: bool = False


ROUTES = {
    "wifi": ("wifi", "Wi-Fi networks", "Choose and manage networks in the existing spruce settings"),
    "bluetooth": ("bluetooth", "Bluetooth devices", "Use spruce pairing and audio-device management"),
    "controllers": ("settings", "Controllers & calibration", "Use the existing controller, remapping and calibration screens"),
    "power": ("settings", "Power & sleep", "Use the existing save-aware power and sleep controls"),
    "usb": ("apps", "USB storage", "Use the existing staged clean-unmount USB app"),
    "advanced": ("settings", "All spruce settings", "Keep every installed system setting reachable"),
    "apps": ("apps", "All installed apps", "Open the existing spruce app browser"),
    "collections": ("collections", "Collections & artwork", "Use the existing collection and artwork tools"),
}


def unavailable_status():
    reason = "Device controls are unavailable here. Use spruce on your device."
    return {"schema": 1, "generation": 0, "authority_bound": False,
            "controls": [{"control_id": name, "label": label, "group": group,
                          "kind": kind, "value": None, "value_text": "Unavailable",
                          "writable": False, "reason": reason}
                         for name, label, group, kind in (
                             ("backlight", "Screen brightness", "display", "step"),
                             ("volume", "System volume", "sound", "step"),
                             ("wifi", "Wi-Fi", "network", "toggle"),
                             ("bluetooth", "Bluetooth", "network", "toggle"))],
            "routes": [{"route_id": name, "label": value[1], "description": value[2],
                        "available": False, "reason": reason} for name, value in ROUTES.items()],
            "physical_effect_verified": False}


class FixedHardwareSettings:
    """One reviewed source callback per operation, with stale-preview rejection.

    Values and callbacks are captured from an already initialized owner. A
    source-level shared write window must serialize the surrounding session.
    The local lock is only for this adapter's preview/request bookkeeping.
    """
    def __init__(self, controls, *, qualified, write_window=None, assert_owner=None, clock=time.monotonic):
        if not callable(qualified) or (write_window is not None and not callable(write_window)):
            raise ValueError("explicit qualification and write-window callbacks are required")
        self.controls = {control.id: control for control in controls}
        if set(self.controls) - {"backlight", "volume", "wifi", "bluetooth"}:
            raise ValueError("unknown hardware control")
        self.qualified, self.write_window = qualified, write_window
        self.assert_owner, self.clock = assert_owner, clock
        self.generation = 0
        self._previews, self._requests = OrderedDict(), OrderedDict()
        self._lock = threading.RLock()

    @classmethod
    def from_initialized_device(cls, device, *, qualified, write_window=None, current_device=None):
        def callback(name):
            value = getattr(device, name, None)
            return value if callable(value) else None
        controls = []
        for name, label, group, getter, lower, raise_, maximum in (
                ("backlight", "Screen brightness", "display", "lumination", "lower_lumination", "raise_lumination", 10),
                ("volume", "System volume", "sound", "get_display_volume", "volume_down", "volume_up", None)):
            read = callback(getter)
            if read:
                controls.append(HardwareControl(name, label, group, read, callback(lower), callback(raise_),
                                                maximum=maximum, asynchronous=name == "volume"))
        for name, label in (("wifi", "Wi-Fi"), ("bluetooth", "Bluetooth")):
            read, on, off = callback("is_" + name + "_enabled"), callback("enable_" + name), callback("disable_" + name)
            if read:
                def set_radio(enabled, on=on, off=off, name=name):
                    (on if enabled else off)()
                    if name == "wifi" and callback("note_wifi_change"):
                        callback("note_wifi_change")()
                controls.append(HardwareControl(name, label, "network", read,
                    enable=(lambda setter=set_radio: setter(True)) if on else None,
                    disable=(lambda setter=set_radio: setter(False)) if off else None,
                    kind="toggle", asynchronous=True))
        def owner():
            if current_device is not None and current_device() is not device:
                raise HardwareSettingsError("OWNER_CHANGED", "The existing device authority changed. Reopen this interface.")
        return cls(controls, qualified=qualified, write_window=write_window, assert_owner=owner)

    def _ready(self):
        if self.assert_owner:
            self.assert_owner()
        return self.qualified() is True and self.write_window is not None

    @staticmethod
    def _fields(params, allowed, required):
        if not isinstance(params, dict) or set(params) - set(allowed) or set(required) - set(params):
            raise HardwareSettingsError("INVALID_PARAMS", "This device action has unsupported fields.")

    @staticmethod
    def _value(control):
        value = control.read()
        if control.kind == "toggle":
            if type(value) is not bool:
                raise HardwareSettingsError("UNKNOWN_READING", "The device has no verified setting read-back.")
        elif type(value) is not int or not 0 <= value <= (control.maximum if control.maximum is not None else 100):
            raise HardwareSettingsError("UNKNOWN_READING", "The device has no verified setting read-back.")
        return value

    def status(self):
        with self._lock:
            ready = self._ready()
            result = unavailable_status()
            result.update(generation=self.generation, authority_bound=True)
            for row in result["controls"]:
                control = self.controls.get(row["control_id"])
                if control is None:
                    continue
                try:
                    value = self._value(control)
                except Exception:
                    row["reason"] = "The existing device authority did not supply a current reading."
                    continue
                callbacks = (control.enable, control.disable) if control.kind == "toggle" else (control.lower, control.raise_)
                row.update(value=value, value_text=("On" if value else "Off") if control.kind == "toggle"
                           else str(value) + (" / " + str(control.maximum) if control.maximum is not None else " · system level"),
                           writable=ready and all(callable(item) for item in callbacks),
                           asynchronous=control.asynchronous,
                           reason=("" if ready and all(callable(item) for item in callbacks)
                                   else "This control is not enabled for this device yet. Use the existing spruce settings."))
            for row in result["routes"]:
                row.update(available=ready, reason="" if ready else "Open this screen from classic spruce.")
            if not self._ready():
                for row in result["controls"]:
                    row.update(writable=False, reason="This control is not enabled for the current device session.")
                for row in result["routes"]:
                    row.update(available=False, reason="Open this screen from classic spruce.")
            return result

    def preview(self, params):
        self._fields(params, ("control_id", "operation", "expected_generation"),
                     ("control_id", "operation", "expected_generation"))
        with self._lock:
            if not self._ready():
                raise HardwareSettingsError("UNQUALIFIED_HARDWARE", "The existing device and shared write window must be qualified first.")
            if not isinstance(params["control_id"], str) or not isinstance(params["operation"], str):
                raise HardwareSettingsError("INVALID_PARAMS", "Device controls use fixed text identifiers.")
            control = self.controls.get(params["control_id"])
            if not control or params["operation"] not in (("toggle",) if control.kind == "toggle" else ("lower", "raise")):
                raise HardwareSettingsError("INVALID_PARAMS", "Choose a supported device control and operation.")
            if type(params["expected_generation"]) is not int or params["expected_generation"] != self.generation:
                raise HardwareSettingsError("STALE_HARDWARE_PREVIEW", "The device settings changed. Review them again.")
            before = self._value(control)
            if not self._ready():
                raise HardwareSettingsError("UNQUALIFIED_HARDWARE", "The device authority changed during observation.")
            operation = params["operation"]
            callback = (control.disable if before else control.enable) if operation == "toggle" else getattr(control, "raise_" if operation == "raise" else "lower")
            if not callable(callback):
                raise HardwareSettingsError("UNSUPPORTED_HARDWARE", "The existing device has no handler for that change.")
            if control.maximum is not None and ((operation == "lower" and before == 0) or (operation == "raise" and before == control.maximum)):
                raise HardwareSettingsError("SETTING_BOUNDARY", "This setting is already at its limit.")
            token = uuid.uuid4().hex
            self._previews[token] = {"control_id": control.id, "operation": operation, "before": before,
                                     "generation": self.generation, "expires": self.clock() + 60}
            while len(self._previews) > 32:
                self._previews.popitem(last=False)
            return {"preview_id": token, "generation": self.generation, "control_id": control.id,
                    "label": control.label, "before": before, "operation": operation,
                    "asynchronous": control.asynchronous,
                    "after": not before if operation == "toggle" else None,
                    "scope": "spruce applies this setting. Sound and wireless changes may take a moment to refresh."}

    def apply(self, params):
        self._fields(params, ("preview_id", "request_id", "expected_generation"),
                     ("preview_id", "request_id", "expected_generation"))
        request = params["request_id"]
        if not isinstance(request, str) or not 1 <= len(request) <= 128 or any(not (c.isascii() and (c.isalnum() or c in "_-")) for c in request):
            raise HardwareSettingsError("INVALID_PARAMS", "A bounded request identity is required.")
        if not isinstance(params["preview_id"], str) or len(params["preview_id"]) > 128:
            raise HardwareSettingsError("INVALID_PARAMS", "A bounded preview identity is required.")
        with self._lock:
            if request in self._requests:
                previous, result = self._requests[request]
                if previous != params:
                    raise HardwareSettingsError("REQUEST_CONFLICT", "That request identity belongs to another change.")
                if isinstance(result, Exception):
                    raise result
                return copy.deepcopy(result)
            if not self._ready():
                raise HardwareSettingsError("UNQUALIFIED_HARDWARE", "The existing device/write window is unavailable.")
            preview = self._previews.get(params["preview_id"])
            if (not preview or preview["expires"] < self.clock() or preview["generation"] != self.generation
                    or type(params["expected_generation"]) is not int or params["expected_generation"] != self.generation):
                raise HardwareSettingsError("STALE_HARDWARE_PREVIEW", "Review the current device setting again.")
            control = self.controls[preview["control_id"]]
            attempted = False
            try:
                with self.write_window():
                    if not self._ready():
                        raise HardwareSettingsError("UNQUALIFIED_HARDWARE", "The existing device/write window is unavailable.")
                    current = self._value(control)
                    if not self._ready() or current != preview["before"]:
                        raise HardwareSettingsError("HARDWARE_CONFLICT", "Another device setting owner changed this value. Review again.")
                    operation = preview["operation"]
                    callback = (control.disable if preview["before"] else control.enable) if operation == "toggle" else getattr(control, "raise_" if operation == "raise" else "lower")
                    self._previews.pop(params["preview_id"])
                    self.generation += 1
                    attempted = True
                    callback()
                    observed = self._value(control)
                    if not self._ready():
                        raise HardwareSettingsError("UNQUALIFIED_HARDWARE", "The device authority changed during application.")
                    result = {"generation": self.generation, "control_id": control.id, "value": observed,
                              "operation_accepted": True, "configuration_observed": observed != preview["before"],
                              "physical_effect_verified": False, "asynchronous": control.asynchronous}
            except Exception:
                if not attempted:
                    raise
                result = HardwareSettingsError("HARDWARE_OUTCOME_UNCERTAIN", "The existing handler did not confirm its result. Refresh before another change.")
            self._requests[request] = (dict(params), result)
            while len(self._requests) > 64:
                self._requests.popitem(last=False)
            if isinstance(result, Exception):
                raise result
            return copy.deepcopy(result)

    def route(self, params):
        self._fields(params, ("route_id",), ("route_id",))
        with self._lock:
            if not self._ready():
                raise HardwareSettingsError("UNQUALIFIED_HARDWARE", "This device route needs the qualified existing spruce session.")
            if not isinstance(params["route_id"], str) or len(params["route_id"]) > 64:
                raise HardwareSettingsError("INVALID_PARAMS", "Choose a fixed registered device route.")
            value = ROUTES.get(params["route_id"])
            if value is None:
                raise HardwareSettingsError("UNKNOWN_ROUTE", "This is not a registered spruce route.")
            return {"route": value[0], "label": value[1]}
