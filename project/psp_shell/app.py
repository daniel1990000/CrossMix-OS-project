"""Desktop proof and injected-backend runner for the Smart Pro experience.

The standalone CLI is a preview/read-only inventory UI. It never starts a game,
changes firmware, or exports storage. Target actions need an injected existing
spruce backend and a separately qualified runtime bridge.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import queue
import random
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from collections import deque

from . import __version__
from .demo import DemoBackend


class AppError(RuntimeError):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code, self.retryable = code, retryable


def error_fields(error):
    return (getattr(error, "code", "ACTION_FAILED"), str(error)[:2048])


def asset_root(explicit=None):
    choices = [Path(explicit)] if explicit else []
    choices.extend((Path(__file__).resolve().parent.parent / "assets",
                    Path(__file__).resolve().parent.parent.parent / "assets",
                    Path(sys.prefix) / "share" / "psp_shell" / "assets"))
    for path in choices:
        if (path / "fonts" / "NotoSans.ttf").is_file():
            return path
    raise AppError("ASSET_MISSING", "The original font assets are missing. Restore the verified preview package.")


def guard_snapshot_outputs(sd_root, paths):
    """An explicitly selected output must not defeat read-only card mode."""
    if not sd_root:
        return
    root = Path(sd_root).resolve()
    for path in paths:
        if path and Path(path).resolve().is_relative_to(root):
            raise AppError("READ_ONLY_SNAPSHOT", "Preview state, screenshots and reports must be stored outside the inspected card.")


class Dispatcher:
    """Fixed operation table. No shell endpoint or caller-supplied command."""
    def __init__(self, backend, settings, state_dir, *, launch_bridge=None, control_adapter=None,
                 theme_manager=None, hardware_adapter=None, experience_manager=None, game_options_handler=None):
        self.backend, self.settings = backend, settings
        self.state_dir = Path(state_dir)
        self.launch_bridge = launch_bridge
        self.control_adapter = control_adapter
        self.theme_manager = theme_manager
        self.hardware_adapter = hardware_adapter
        self.experience_manager = experience_manager
        # Trusted source callback schedules the existing foreground menu. It
        # must not be a raw popup callable executed on a data-worker thread.
        self.game_options_handler = game_options_handler
        self.pending_launch = None
        self.transitions = deque(maxlen=32)
        self.last_error_code = None

    @staticmethod
    def _fields(params, allowed, required=()):
        if not isinstance(params, dict) or set(params) - set(allowed) or set(required) - set(params):
            raise AppError("INVALID_PARAMS", "This action has invalid or unsupported fields.")

    @staticmethod
    def _text(params, name, default="", limit=1024):
        value = params.get(name, default)
        if not isinstance(value, str) or "\0" in value or len(value) > limit:
            raise AppError("INVALID_PARAMS", f"Invalid {name}.")
        return value

    def dispatch(self, method, params=None):
        params = dict(params or {})
        if self.pending_launch is not None and method not in ("system.snapshot", "system.capabilities"):
            raise AppError("BUSY_HANDOFF", "An accepted handoff is waiting for this interface to release its resources.")
        try:
            result = self._dispatch(method, params)
            self.transitions.append({"method": method, "outcome": "ok"})
            return result
        except Exception as error:
            self.last_error_code = getattr(error, "code", "ACTION_FAILED")
            self.transitions.append({"method": method, "outcome": self.last_error_code})
            raise

    def _dispatch(self, method, params):
        if method == "system.capabilities":
            self._fields(params, ())
            demo = bool(getattr(self.backend, "demo", False))
            return {"profile_id": "desktop-sample" if demo else "spruce-source-snapshot",
                    "physical_device_verified": False, "demo": demo,
                    "game_launch": self.launch_bridge is not None,
                    "game_options": callable(self.game_options_handler),
                    "power": {"supported": False, "reason": "Use the verified spruce device backend"},
                    "usb": {"supported": False, "reason": "Requires the qualified staged export/reboot route"},
                    "menu_controls": {"gameplay_is_separate": True, "live_emulator_changes": False}}
        if method == "system.snapshot":
            self._fields(params, ())
            return {"profile_id": "Desktop sample collection" if getattr(self.backend, "demo", False)
                    else "Read-only spruce snapshot", "firmware": None, "battery": None,
                    "temperature": None, "last_error_code": self.last_error_code,
                    "version": __version__, "hardware_readings": "unavailable"}
        if method == "hardware.status":
            self._fields(params, ())
            if self.hardware_adapter is not None:
                return self.hardware_adapter.status()
            from .hardware_settings import unavailable_status
            return unavailable_status()
        if method.startswith("hardware."):
            action = method.split(".", 1)[1]
            if action not in ("preview", "apply", "route"):
                raise AppError("UNKNOWN_METHOD", "This device setting action is not supported.")
            if self.hardware_adapter is None:
                raise AppError("UNQUALIFIED_HARDWARE", "This preview has no qualified existing device authority.")
            result = getattr(self.hardware_adapter, action)(params)
            if action == "route":
                return self._dispatch("spruce.advanced", {"route": result["route"]})
            return result
        if method == "experience.ppsspp.status":
            self._fields(params, ())
            if self.experience_manager is not None:
                return self.experience_manager.status()
            return {"schema": 1, "generation": 0, "profile_id": "ppsspp-native-unqualified",
                    "adoption_available": False, "gameplay_changed": False, "emulator_binary_changed": False,
                    "gate_reason": "UNQUALIFIED_PPSSPP_EXPERIENCE",
                    "reason": "PPSSPP menu matching is unavailable until this installed version is checked. Its current settings stay in place."}
        if method.startswith("experience.ppsspp."):
            action = method[len("experience.ppsspp."):]
            if action not in ("preview", "apply", "undo"):
                raise AppError("UNKNOWN_METHOD", "This PPSSPP settings action is not supported.")
            if self.experience_manager is None:
                raise AppError("UNQUALIFIED_PPSSPP_EXPERIENCE", "This preview has no qualified shared PPSSPP settings manager.")
            return getattr(self.experience_manager, action)(params)
        if method == "settings.get":
            self._fields(params, ())
            return self.settings.get()
        if method.startswith("settings."):
            action = method.split(".", 1)[1]
            if action not in ("preview", "apply", "undo"):
                raise AppError("UNKNOWN_METHOD", "This settings action is not supported.")
            return getattr(self.settings, action)(params)
        if method == "controls.capabilities":
            self._fields(params, ())
            if self.control_adapter is not None:
                return self.control_adapter.capabilities()
            reason = "Emulator menu changes need a qualified installed binary and a stopped-writer window."
            return {"schema": 1, "generation": 0, "profiles": [
                {"profile_id": profile, "label": label, "surface": surface,
                 "writable": False, "error": {"code": "UNQUALIFIED_CONTROLS", "message": reason}}
                for profile, label, surface in (
                    ("ppsspp-native-unqualified", "PPSSPP native menus", "native_menu"),
                    ("retroarch-standard-unqualified", "RetroArch standard menu", "standard_menu"),
                    ("spruce-igm-unqualified", "spruce in-game menu", "spruce_igm"))], "reason": reason}
        if method.startswith("controls."):
            action = method.split(".", 1)[1]
            if action not in ("preview", "apply", "undo"):
                raise AppError("UNKNOWN_METHOD", "This controls action is not supported.")
            if self.control_adapter is None:
                raise AppError("UNQUALIFIED_CONTROLS", "This preview has no qualified emulator configuration adapter.")
            return getattr(self.control_adapter, action)(params)
        if method == "appearance.ppsspp.status":
            self._fields(params, ())
            if self.theme_manager is not None:
                return {**self.theme_manager.status(), "preview_available": True}
            from .ppsspp import THEME_NAMES
            return {"generation": 0, "theme": None, "motion": None,
                    "available_themes": list(THEME_NAMES), "preview_available": False,
                    "adoption_available": False, "gate_reason": "UNQUALIFIED_THEME",
                    "reason": "PPSSPP appearance needs a verified installed version and a stopped emulator."}
        if method.startswith("appearance.ppsspp."):
            action = method[len("appearance.ppsspp."):]
            if action not in ("preview", "apply", "undo"):
                raise AppError("UNKNOWN_METHOD", "This appearance action is not supported.")
            if self.theme_manager is None:
                raise AppError("UNQUALIFIED_THEME", "PPSSPP appearance is unavailable until the installed emulator is verified.")
            return getattr(self.theme_manager, action)(params)
        if method == "library.systems":
            self._fields(params, ())
            return self.backend.systems()
        if method == "library.query":
            self._fields(params, ("system_id", "search", "offset", "limit"))
            system = self._text(params, "system_id", limit=128)
            search = self._text(params, "search", limit=128)
            offset, limit = params.get("offset", 0), params.get("limit", 40)
            if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 100:
                raise AppError("INVALID_PARAMS", "Page size must be 1–100 and offset must be nonnegative.")
            return self.backend.games(system or None, search=search, offset=offset, limit=limit)
        if method in ("library.recent", "library.favorites", "tools.list"):
            self._fields(params, ())
            return getattr(self.backend, {"library.recent": "recent", "library.favorites": "favorites", "tools.list": "tools"}[method])()
        if method == "library.random":
            self._fields(params, ())
            if hasattr(self.backend, "random"):
                return self.backend.random()
            data = self.backend.games(None, limit=100)
            if not data["items"]:
                raise AppError("EMPTY_LIBRARY", "There are no available games in this collection.")
            return random.choice(data["items"])
        if method == "library.favorite.set":
            self._fields(params, ("game_id", "enabled"), ("game_id", "enabled"))
            game_id = self._text(params, "game_id")
            if type(params["enabled"]) is not bool:
                raise AppError("INVALID_PARAMS", "Favorite state must be true or false.")
            if hasattr(self.backend, "preview_favorite"):
                preview = self.backend.preview_favorite(game_id, params["enabled"])
                result = self.backend.set_favorite(game_id, params["enabled"], preview=preview)
            else:
                result = self.backend.set_favorite(game_id, params["enabled"])
            return result if result is not None else {"game_id": game_id, "enabled": params["enabled"]}
        if method == "game.options":
            self._fields(params, ("game_id",), ("game_id",))
            game_id = self._text(params, "game_id")
            if not game_id or not callable(self.game_options_handler):
                raise AppError("UNSUPPORTED_GAME_OPTIONS", "Open this game's options from the existing spruce interface.")
            result = self.game_options_handler(game_id)
            if not isinstance(result, dict) or result.get("state") != "releasing_ui":
                raise AppError("UNVERIFIED_GAME_OPTIONS", "The existing game menu did not accept this handoff.")
            return result
        if method in ("game.launch", "tool.launch"):
            game = method == "game.launch"
            self._fields(params, ("game_id", "preset_id", "mode") if game else ("tool_id",),
                         ("game_id",) if game else ("tool_id",))
            identifier = self._text(params, "game_id" if game else "tool_id")
            mode = self._text(params, "mode", "normal", 16) if game else "normal"
            if mode not in ("normal", "fresh", "resume"):
                raise AppError("INVALID_PARAMS", "Unknown launch mode.")
            context = (self.backend.resolve_game(identifier, self._text(params, "preset_id") or None, mode)
                       if game else self.backend.resolve_tool(identifier))
            if not context.get("launchable") or self.launch_bridge is None:
                raise AppError(context.get("gate_reason", "UNVERIFIED_LAUNCH"),
                               "This standalone preview cannot launch that entry. Use the existing spruce interface until its runtime bridge is qualified.")
            action_id = context.get("action_id")
            if not isinstance(action_id, str) or not action_id:
                raise AppError("UNVERIFIED_ACTION", "The installed backend did not provide a registered action.")
            self.launch_bridge.validate(action_id, mode)
            self.pending_launch = {"action_id": action_id, "mode": mode}
            return {"state": "releasing_ui"}
        if method == "interface.switch":
            self._fields(params, ("interface",), ("interface",))
            if params["interface"] != "classic":
                raise AppError("UNSUPPORTED_INTERFACE", "Only the existing spruce interface is a valid handoff here.")
            return {"interface": "classic", "state": "releasing_ui"}
        if method == "support.export":
            self._fields(params, ())
            self.state_dir.mkdir(parents=True, exist_ok=True)
            report = {"schema": 1, "component": "smartpro-psp-experience", "version": __version__,
                      "evidence": "host", "physical_device_verified": False,
                      "last_error_code": self.last_error_code,
                      "operations": list(self.transitions),
                      "redaction": "No ROM titles/paths, network settings, credentials or command arguments collected"}
            target = self.state_dir / "support-report.json"
            temporary = target.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, target)
            return {"path": str(target)}
        raise AppError("UNKNOWN_METHOD", "This action is not supported by the installed interface.")


def _restore_navigation(state_dir):
    path = Path(state_dir) / "navigation.json"
    try:
        if path.stat().st_size > 32768:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("schema") == 1 else None
    except (OSError, ValueError):
        return None


def _save_navigation(state_dir, model):
    target = Path(state_dir) / "navigation.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(model.export_state(), ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def run_preview(args, backend=None):
    if args.headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import sdl2
    from .settings import SettingsStore
    from .ui.model import NavigationModel
    from .ui.renderer import Renderer
    from .ui.input import InputMapper

    scratch = None
    if args.state_dir:
        state_dir = Path(args.state_dir).resolve()
    elif args.headless or args.demo:
        scratch = tempfile.TemporaryDirectory(prefix="smartpro-preview-")
        state_dir = Path(scratch.name)
    else:
        state_dir = Path.home() / ".local" / "state" / "smartpro-preview"
    guard_snapshot_outputs(args.sd_root, (state_dir, args.screenshot, args.report))
    if backend is None:
        if args.demo:
            backend = DemoBackend()
        else:
            from .adapters.spruce import SpruceBackend
            backend = SpruceBackend(args.sd_root, read_only=True)
    settings = SettingsStore(str(state_dir))
    settings.recover()
    dispatcher = Dispatcher(backend, settings, state_dir)
    model = NavigationModel(demo=bool(getattr(backend, "demo", False)),
                            restored_state=_restore_navigation(state_dir))

    def receive(command, result=None, error=None):
        if error is not None:
            model.error(command, *error_fields(error))
            return []
        try:
            return model.receive(command, result)
        except Exception as exc:
            model.error(command, *error_fields(exc))
            return []

    def synchronous(commands):
        pending = list(commands)
        while pending:
            command = pending.pop(0)
            try:
                pending.extend(receive(command, dispatcher.dispatch(command.method, command.params)))
            except Exception as exc:
                receive(command, error=exc)

    synchronous(model.initial_commands())
    def select_category(index):
        for _ in range((index - model.category) % 4):
            synchronous(model.handle("right"))
    if args.screen == "continue":
        select_category(1)
    elif args.screen == "tools":
        select_category(2)
    elif args.screen in ("settings", "controls", "appearance", "experience", "display", "sound", "network", "controllers", "power"):
        select_category(3)
        if args.screen != "settings":
            target = args.screen if args.screen in ("controls", "appearance", "experience") else "hardware_" + args.screen
            for _ in range(len(model.snapshot().items)):
                if model.snapshot().selected_item.id == target:
                    break
                synchronous(model.handle("down"))
            else:
                raise AppError("SCREEN_UNAVAILABLE", "This preview screen is unavailable.")
            synchronous(model.handle("confirm"))
    elif args.screen == "search":
        for _ in range(2):
            synchronous(model.handle("down"))
        synchronous(model.handle("confirm"))
    elif args.screen == "error":
        model.error(None, "SAMPLE_FAILURE", "The launcher was unavailable. Your saves remain in place.")
    elif args.screen == "library":
        select_category(0)
        synchronous(model.handle("confirm"))
    for action in filter(None, (args.actions or "").split(",")):
        if action not in ("left", "right", "up", "down", "confirm", "back", "favorite", "search"):
            raise AppError("INVALID_ACTION", "The scripted preview contains an unknown navigation action.")
        synchronous(model.handle(action))

    font = asset_root(args.assets) / "fonts" / "NotoSans.ttf"
    renderer = Renderer(args.width, args.height, font_path=str(font), software=args.headless or args.software)
    mapper = InputMapper()
    event = sdl2.SDL_Event()
    ready = queue.Queue()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spruce-ui-data")
    frames, frame_times = 0, []
    text_input_active = False

    def sync_text_input():
        nonlocal text_input_active
        active = model.snapshot().keyboard is not None
        if active != text_input_active:
            text_input_active = active
            if active:
                sdl2.SDL_StartTextInput()
            else:
                sdl2.SDL_StopTextInput()

    def handle_action(action, text=""):
        before = model.snapshot()
        commands = model.handle(action, text)
        after = model.snapshot()
        signature = lambda state: (state.category, state.title, state.dialog is not None,
                                   state.keyboard is not None, state.preferences.confirm)
        if signature(before) != signature(after):
            mapper.block_held()
        sync_text_input()
        return commands

    def submit(commands):
        for command in commands:
            future = executor.submit(dispatcher.dispatch, command.method, command.params)
            future.add_done_callback(lambda f, command=command: ready.put((command, f)))

    try:
        while args.frames == 0 or frames < args.frames:
            start = time.monotonic()
            snapshot = model.snapshot(start)
            sync_text_input()
            while sdl2.SDL_PollEvent(ctypes.byref(event)):
                snapshot = model.snapshot(start)
                for action in mapper.process(event, snapshot.preferences, text_mode=snapshot.keyboard is not None):
                    submit(handle_action(action.action, action.text))
                    renderer.feedback(snapshot.preferences.sound)
            for action in mapper.tick(start):
                submit(handle_action(action.action, action.text))
            while True:
                try:
                    command, future = ready.get_nowait()
                except queue.Empty:
                    break
                try:
                    submit(receive(command, future.result()))
                except Exception as exc:
                    receive(command, error=exc)
                mapper.block_held()
            snapshot = model.snapshot(start)
            renderer.render(snapshot, start if not args.headless else args.frame_time)
            renderer.present()
            frames += 1
            frame_times.append(time.monotonic() - start)
            if model.exit_request:
                break
            if not args.headless:
                time.sleep(max(0, 1 / 60 - (time.monotonic() - start)))
        if args.screenshot:
            target = Path(args.screenshot)
            target.parent.mkdir(parents=True, exist_ok=True)
            renderer.save_screenshot(str(target))
        _save_navigation(state_dir, model)
        if args.report:
            times = sorted(frame_times)
            report = {"schema": 1, "evidence": "host-preview", "version": __version__,
                      "frames": frames, "width": args.width, "height": args.height,
                      "render_ms_p50": times[len(times)//2] * 1000 if times else None,
                      "render_ms_p95": times[min(len(times)-1, int(len(times)*.95))] * 1000 if times else None,
                      "device_performance_claim": False, "real_game_launches": 0}
            target = Path(args.report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
        if text_input_active:
            sdl2.SDL_StopTextInput()
        mapper.close()
        renderer.close()
        if scratch:
            scratch.cleanup()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Original Smart Pro interface preview; standalone mode never launches device commands")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--demo", action="store_true", help="Use an original synthetic sample collection")
    source.add_argument("--sd-root", help="Read a spruce card/source snapshot without modifying it")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--software", action="store_true")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--frames", type=int, default=0, help="Exit after N rendered frames; zero runs interactively")
    parser.add_argument("--frame-time", type=float, default=0.0, help="Fixed animation time for deterministic headless screenshots")
    parser.add_argument("--screen", choices=("home", "library", "continue", "tools", "settings", "controls", "appearance", "experience", "display", "sound", "network", "controllers", "power", "search", "error"), default="home")
    parser.add_argument("--actions", help="Comma-separated navigation actions for a recorded preview")
    parser.add_argument("--screenshot")
    parser.add_argument("--report")
    parser.add_argument("--state-dir")
    parser.add_argument("--assets")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    if not args.demo and not args.sd_root:
        args.demo = True
    if not 640 <= args.width <= 2560 or not 360 <= args.height <= 1440 or not 0 <= args.frames <= 100000:
        parser.error("Preview dimensions or frame limit exceed supported bounds")
    if args.headless and args.frames == 0:
        args.frames = 1
    try:
        return run_preview(args)
    except Exception as error:
        code, message = error_fields(error)
        print(f"{code}: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
