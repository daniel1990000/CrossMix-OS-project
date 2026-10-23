"""Foreground SDL input mapping with release gates and bounded repeat.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import time
from typing import Any

import sdl2

from .model import Preferences


@dataclass(frozen=True)
class InputAction:
    action: str
    text: str = ""


class InputMapper:
    """Only maps this UI's input; it never grabs or remaps a device globally.

    Call ``block_held`` after changing pages, opening/closing a dialog or changing
    the Confirm preference. A held button cannot confirm the destination screen.
    An embedded PyUI view may use ``manage_controllers=False`` and feed its own
    logical actions directly to NavigationModel instead of opening devices twice.
    """

    INITIAL_REPEAT = 0.33
    REPEAT_INTERVAL = 0.095
    AXIS_PRESS = 18000
    AXIS_RELEASE = 10000
    DIRECTIONS = frozenset(("left", "right", "up", "down"))

    def __init__(self, manage_controllers: bool = True, sample_initial_state: bool = True):
        self._held: dict[tuple[Any, ...], tuple[str, float]] = {}
        self._repeat_due: dict[tuple[Any, ...], float] = {}
        self._axes: dict[tuple[int, int], int] = {}
        self._controllers: dict[int, Any] = {}
        self._gate = False
        self._text_mode = False
        self._manage_controllers = manage_controllers
        if manage_controllers:
            for index in range(max(0, sdl2.SDL_NumJoysticks())):
                self._open_controller(index)
        if sample_initial_state:
            if sdl2.SDL_WasInit(sdl2.SDL_INIT_VIDEO):
                sdl2.SDL_PumpEvents()
            count = ctypes.c_int()
            state = sdl2.SDL_GetKeyboardState(ctypes.byref(count))
            for scan in (sdl2.SDL_SCANCODE_RETURN, sdl2.SDL_SCANCODE_KP_ENTER,
                         sdl2.SDL_SCANCODE_ESCAPE, sdl2.SDL_SCANCODE_UP, sdl2.SDL_SCANCODE_DOWN,
                         sdl2.SDL_SCANCODE_LEFT, sdl2.SDL_SCANCODE_RIGHT, sdl2.SDL_SCANCODE_X, sdl2.SDL_SCANCODE_Y, sdl2.SDL_SCANCODE_TAB):
                if state and scan < count.value and state[scan]:
                    self._held[("keyboard", int(sdl2.SDL_GetKeyFromScancode(scan)))] = ("held_at_start", time.monotonic())
                    self._gate = True

    @property
    def controller_count(self) -> int:
        return len(self._controllers)

    def _open_controller(self, index: int) -> None:
        if not self._manage_controllers or not sdl2.SDL_IsGameController(index):
            return
        controller = sdl2.SDL_GameControllerOpen(index)
        if not controller:
            return
        joystick = sdl2.SDL_GameControllerGetJoystick(controller)
        identifier = int(sdl2.SDL_JoystickInstanceID(joystick))
        if identifier in self._controllers:
            sdl2.SDL_GameControllerClose(controller)
            return
        self._controllers[identifier] = controller
        # A pad connected with a face button already held must first go neutral.
        for button in range(sdl2.SDL_CONTROLLER_BUTTON_MAX):
            if sdl2.SDL_GameControllerGetButton(controller, button):
                self._held[("controller", identifier, button)] = ("held_at_connect", time.monotonic())
                self._gate = True
        for axis in (sdl2.SDL_CONTROLLER_AXIS_LEFTX, sdl2.SDL_CONTROLLER_AXIS_LEFTY):
            value = int(sdl2.SDL_GameControllerGetAxis(controller, axis))
            direction = -1 if value <= -self.AXIS_PRESS else 1 if value >= self.AXIS_PRESS else 0
            if direction:
                self._axes[(identifier, axis)] = direction
                self._held[("axis", identifier, axis, direction)] = ("held_at_connect", time.monotonic())
                self._gate = True

    def _remove_controller(self, identifier: int) -> None:
        controller = self._controllers.pop(identifier, None)
        if controller:
            sdl2.SDL_GameControllerClose(controller)
        for key in list(self._held):
            if len(key) >= 2 and key[1] == identifier and key[0] in ("controller", "axis"):
                self._release(key)
        self._axes = {key: value for key, value in self._axes.items() if key[0] != identifier}

    def block_held(self) -> None:
        self._gate = bool(self._held)

    def _release(self, key: tuple[Any, ...]) -> None:
        self._held.pop(key, None)
        self._repeat_due.pop(key, None)
        if not self._held:
            self._gate = False

    def _press(self, key: tuple[Any, ...], action: str | None, now: float) -> list[InputAction]:
        if action is None or key in self._held:
            return []
        self._held[key] = (action, now)
        if action in self.DIRECTIONS:
            self._repeat_due[key] = now + self.INITIAL_REPEAT
        return [] if self._gate else [InputAction(action)]

    def process(self, event: Any, preferences: Preferences | None = None,
                text_mode: bool = False, now: float | None = None) -> list[InputAction]:
        preferences = preferences or Preferences()
        now = time.monotonic() if now is None else now
        event_type = int(event.type)
        self._text_mode = text_mode
        if event_type == sdl2.SDL_QUIT:
            return [InputAction("quit")]
        if event_type == sdl2.SDL_CONTROLLERDEVICEADDED:
            self._open_controller(int(event.cdevice.which))
            return []
        if event_type == sdl2.SDL_CONTROLLERDEVICEREMOVED:
            self._remove_controller(int(event.cdevice.which))
            return []
        if event_type == sdl2.SDL_TEXTINPUT and text_mode and not self._gate:
            value = bytes(event.text.text).split(b"\0", 1)[0].decode("utf-8", "replace")
            return [InputAction("text", value)] if value else []
        if event_type in (sdl2.SDL_KEYDOWN, sdl2.SDL_KEYUP):
            symbol = int(event.key.keysym.sym)
            key = ("keyboard", symbol)
            if event_type == sdl2.SDL_KEYUP:
                self._release(key)
                return []
            if event.key.repeat:
                return []
            mapping = {sdl2.SDLK_UP: "up", sdl2.SDLK_DOWN: "down", sdl2.SDLK_LEFT: "left", sdl2.SDLK_RIGHT: "right",
                       sdl2.SDLK_RETURN: "submit_text" if text_mode else "confirm", sdl2.SDLK_KP_ENTER: "submit_text" if text_mode else "confirm",
                       sdl2.SDLK_ESCAPE: "back", sdl2.SDLK_BACKSPACE: "delete_text" if text_mode else "back",
                       sdl2.SDLK_DELETE: "delete_text" if text_mode else None,
                       sdl2.SDLK_F5: "refresh", sdl2.SDLK_TAB: None if text_mode else "menu"}
            if not text_mode:
                mapping.update({sdl2.SDLK_f: "search", sdl2.SDLK_SLASH: "search", sdl2.SDLK_x: "search", sdl2.SDLK_y: "favorite"})
            return self._press(key, mapping.get(symbol), now)
        if event_type in (sdl2.SDL_CONTROLLERBUTTONDOWN, sdl2.SDL_CONTROLLERBUTTONUP):
            identifier, button = int(event.cbutton.which), int(event.cbutton.button)
            key = ("controller", identifier, button)
            if event_type == sdl2.SDL_CONTROLLERBUTTONUP:
                self._release(key)
                return []
            confirm = sdl2.SDL_CONTROLLER_BUTTON_A if preferences.confirm == "south" else sdl2.SDL_CONTROLLER_BUTTON_B
            back = sdl2.SDL_CONTROLLER_BUTTON_B if preferences.confirm == "south" else sdl2.SDL_CONTROLLER_BUTTON_A
            mapping = {confirm: "confirm", back: "back", sdl2.SDL_CONTROLLER_BUTTON_START: None if text_mode else "menu", sdl2.SDL_CONTROLLER_BUTTON_X: "delete_text" if text_mode else "search",
                       sdl2.SDL_CONTROLLER_BUTTON_Y: "submit_text" if text_mode else "favorite",
                       sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT: "left", sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT: "right",
                       sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP: "up", sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN: "down"}
            return self._press(key, mapping.get(button), now)
        if event_type == sdl2.SDL_CONTROLLERAXISMOTION:
            identifier, axis, value = int(event.caxis.which), int(event.caxis.axis), int(event.caxis.value)
            if axis not in (sdl2.SDL_CONTROLLER_AXIS_LEFTX, sdl2.SDL_CONTROLLER_AXIS_LEFTY):
                return []
            old = self._axes.get((identifier, axis), 0)
            direction = -1 if value <= -self.AXIS_PRESS else 1 if value >= self.AXIS_PRESS else 0 if abs(value) < self.AXIS_RELEASE else old
            if direction == old:
                return []
            self._release(("axis", identifier, axis, old))
            self._axes[(identifier, axis)] = direction
            if not direction:
                return []
            action = ("left" if direction < 0 else "right") if axis == sdl2.SDL_CONTROLLER_AXIS_LEFTX else ("up" if direction < 0 else "down")
            return self._press(("axis", identifier, axis, direction), action, now)
        if event_type == sdl2.SDL_WINDOWEVENT and int(event.window.event) == sdl2.SDL_WINDOWEVENT_FOCUS_LOST:
            # All held inputs are forgotten on focus loss; return needs a new down.
            self._held.clear()
            self._repeat_due.clear()
            self._gate = False
        return []

    def tick(self, now: float | None = None) -> list[InputAction]:
        if self._gate:
            return []
        now = time.monotonic() if now is None else now
        eligible = [(pressed, key, action) for key, (action, pressed) in self._held.items()
                    if action in self.DIRECTIONS and now >= self._repeat_due.get(key, float("inf"))]
        if not eligible:
            return []
        _, key, action = max(eligible, key=lambda entry: entry[0])
        # Never replay a backlog of old repeats after a slow frame or suspend.
        self._repeat_due[key] = now + self.REPEAT_INTERVAL
        return [InputAction(action)]

    def close(self) -> None:
        for controller in self._controllers.values():
            sdl2.SDL_GameControllerClose(controller)
        self._controllers.clear()
        self._held.clear()
        self._repeat_due.clear()
