"""Original in-process frontend runner over already initialized PyUI objects.

There is no SDL initialization, event-device opening, process spawning or global
SDL shutdown here. The existing spruce device callback owns its normal final
display shutdown and principal.sh remains the external game owner.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Callable, Mapping

from .health import FrontendHealth
from .runtime import (ActionRegistry, ContractError, ExclusiveTransition, HandoffRejected,
                      LaunchCoordinator, LaunchHooks, LaunchState, PreflightReport,
                      original_tsp_preflight)


@dataclass
class EmbeddedContext:
    sd_root: str | Path
    state_dir: str | Path
    device: Any
    display: Any
    controller: Any
    main_menu: Any
    inventory: Mapping[str, Any]
    profile: Mapping[str, Any]
    preferences: Mapping[str, Any]
    quiescent: Callable[[], bool]
    stop_background_tasks: Callable[[], None]
    execution_environment: str = "device"
    release_input: Callable[[], None] | None = None
    restore_input: Callable[[], None] | None = None
    tool_list: Callable[[], Any] | None = None
    tool_actions: Mapping[str, Callable] | None = None
    mode_actions: Mapping[str, Mapping[str, Callable]] | None = None
    font_provider: Callable[[int], Any] | None = None
    report_error: Callable[[str], None] | None = None
    control_adapter: Any = None
    theme_manager: Any = None
    hardware_adapter: Any = None
    experience_manager: Any = None
    resume_evidence_provider: Callable | None = None
    game_options_handler: Callable | None = None
    # Trusted source bootstrap supplies live observations separately from its
    # independently qualified expected profile. Refresh before each handoff.
    inventory_provider: Callable[[], Mapping[str, Any]] | None = None
    preferences_provider: Callable[[], Mapping[str, Any]] | None = None
    model_provider_factory: Callable[..., Any] | None = None
    restore_background_tasks: Callable[[], None] | None = None
    assert_owners: Callable[[], None] | None = None


@dataclass
class EmbeddedDependencies:
    # Injection is an in-process host-test seam, never a metadata/plugin loader.
    renderer_factory: Callable[..., Any] | None = None
    provider_factory: Callable[..., Any] | None = None
    backend_factory: Callable[..., Any] | None = None
    settings_factory: Callable[..., Any] | None = None
    model_factory: Callable[..., Any] | None = None


@dataclass(frozen=True)
class EmbeddedResult:
    reason: str
    frames: int
    evidence: str
    first_frame: bool
    real_game_launches: int = 0


def qualification(context: EmbeddedContext) -> PreflightReport:
    if context.assert_owners is not None:
        context.assert_owners()
    if context.inventory_provider is not None:
        context.inventory = context.inventory_provider()
    if context.preferences_provider is not None:
        context.preferences = context.preferences_provider()
    if not isinstance(context.inventory, Mapping) or not isinstance(context.preferences, Mapping):
        raise ContractError("INVALID_EVIDENCE", "Live inventory and preferences must be mappings")
    if context.execution_environment == "host-fixture":
        root = Path(context.sd_root).resolve()
        if context.profile.get("execution_environment") != "host-fixture" or not str(context.profile.get("id", "")).startswith("host-fixture") or context.inventory.get("live") is not False or root == Path("/mnt/SDCARD") or Path("/mnt/SDCARD") in root.parents:
            raise ContractError("INVALID_FIXTURE", "Host fixtures cannot be used to bypass target qualification")
        return PreflightReport(warnings=("Synthetic injected context; no physical device or game launch is established.",))
    if context.execution_environment != "device":
        raise ContractError("INVALID_CONTEXT", "Unknown embedded execution environment")
    gates = ("source_use_verified", "hardware_qualified", "runtime_verified")
    if any(context.profile.get(name) is not True for name in gates):
        raise ContractError("TARGET_UNQUALIFIED", "Source-use, original-TSP hardware and runtime gates must be verified before enabling the embedded frontend")
    profile = dict(context.profile)
    profile.setdefault("source_commit", profile.get("base_commit"))
    versions = profile.get("firmware_versions", [])
    if "firmware_version" not in profile and versions == ["1.1.1"]:
        profile["firmware_version"] = "1.1.1"
    profile["physical_qualification"] = context.profile.get("hardware_qualified") is True
    result = original_tsp_preflight(context.inventory, context.preferences, profile)
    result.assert_safe()
    return result


def _logical_name(value: Any, device: Any) -> str:
    name = getattr(value, "name", str(value))
    # Controller already applies the user's base remapper. Recover face-button
    # position only for a unique inverse, so physical glyphs are not guessed.
    if name in {"A", "B", "X", "Y"}:
        remapper = getattr(device, "button_remapper", None)
        remap = getattr(remapper, "get_mappping", None)
        if callable(remap):
            try:
                candidates = [button for button in type(value) if remap(button) == value]
            except TypeError as exc:
                raise ContractError("UNVERIFIED_INPUT_MAPPING", "The existing logical face-button mapping cannot be inverted") from exc
            if len(candidates) != 1:
                raise ContractError("UNVERIFIED_INPUT_MAPPING", "The current face-button remap is ambiguous; use classic spruce to adjust it")
            name = candidates[0].name
    return name


def logical_action(value: Any, preferences: Any, device: Any) -> str | None:
    name = _logical_name(value, device)
    directions = {"DPAD_LEFT": "left", "DPAD_RIGHT": "right", "DPAD_UP": "up", "DPAD_DOWN": "down",
                  "LEFT_STICK_LEFT": "left", "LEFT_STICK_RIGHT": "right", "LEFT_STICK_UP": "up", "LEFT_STICK_DOWN": "down"}
    if name in directions:
        return directions[name]
    if name in {"A", "B"}:
        confirm = "B" if getattr(preferences, "confirm", "south") == "south" else "A"
        return "confirm" if name == confirm else "back"
    return {"Y": "favorite", "X": "search", "SELECT": "search"}.get(name)


def _existing_font_provider(display: Any) -> Callable[[int], Any]:
    fonts = tuple(value for value in getattr(display, "fonts", {}).values()
                  if getattr(value, "font", None) is not None)
    if not fonts:
        raise ContractError("FONT_UNAVAILABLE", "The existing PyUI fonts are not initialized")
    def font(pixel_size: int):
        chosen = min(fonts, key=lambda value: abs(float(getattr(value, "line_height", pixel_size)) - pixel_size))
        return chosen.font
    return font


class _LaunchBridge:
    def __init__(self, runner: "EmbeddedRunner") -> None:
        self.runner = runner
        self.registered: set[str] = set()

    def validate(self, action_id: str, mode: str) -> None:
        runner = self.runner
        qualification(runner.context).assert_safe()
        runner.backend.validate_action(action_id, mode)
        if action_id not in self.registered:
            def validate(intent):
                try:
                    runner.backend.validate_action(intent.action_id, intent.mode)
                except Exception as exc:
                    raise HandoffRejected(getattr(exc, "code", "ACTION_REJECTED"), "The existing spruce action changed before handoff") from exc
            runner.registry.register(action_id,
                lambda intent: runner.backend.execute_action(intent.action_id, intent.mode, release_ui=False),
                kind="tool" if action_id.startswith("tool:") else "game", allowed_modes=(mode,),
                backend_mode="fake" if runner.context.execution_environment == "host-fixture" else "spruce",
                validate=validate)
            self.registered.add(action_id)


class EmbeddedRunner:
    ADVANCED_ROUTES = {"settings": "Setting", "apps": "App", "collections": "Collection"}
    SOURCE_ROUTES = {"wifi", "bluetooth", "game-options"}

    def __init__(self, context: EmbeddedContext, *, health: FrontendHealth | None = None,
                 attempt_id: str | None = None, dependencies: EmbeddedDependencies | None = None):
        self.context = context
        self.health = health or FrontendHealth(context.state_dir)
        self.attempt_id = attempt_id
        self.dependencies = dependencies or EmbeddedDependencies()
        self.renderer = self.model = self.backend = self.dispatcher = self.settings = None
        self.registry = ActionRegistry()
        self.exclusive = ExclusiveTransition()
        self.coordinator = None
        self.frames = 0
        self.ready = False
        self._input_released = False
        self._background_stopped = False
        self._owner_restore_failed = False
        self._release_gate = True
        self._pending_advanced = None
        self._pending_game_options = None
        self._advanced_in_progress = False

    def _new_renderer(self):
        if self.context.assert_owners is not None:
            self.context.assert_owners()
        factory = self.dependencies.renderer_factory
        if factory is None:
            from .ui.renderer import Renderer
            from .ui.text import SDLTextRasterizer
            factory = Renderer
            text = SDLTextRasterizer(self.context.font_provider or _existing_font_provider(self.context.display))
        else:
            text = None
        display = self.context.display
        renderer = getattr(getattr(display, "renderer", None), "renderer", None)
        window = getattr(getattr(display, "window", None), "window", None)
        if renderer is None or window is None:
            raise ContractError("DISPLAY_UNAVAILABLE", "PyUI must initialize its existing renderer and window before the project view")
        return factory(1280, 720, external_renderer=renderer, external_window=window,
                       external_target=getattr(display, "render_canvas", None), own_resources=False,
                       text_backend=text, artwork_root=str(Path(self.context.sd_root).resolve()))

    def _snapshot(self):
        value = self.model.export_state()
        from .app import _save_navigation
        _save_navigation(self.context.state_dir, self.model)
        return value

    def _close_project_renderer(self):
        if self.renderer is not None:
            if self.context.assert_owners is not None:
                self.context.assert_owners()
            self.renderer.close()
            self.renderer = None

    def _release_input(self):
        if self.context.assert_owners is not None:
            self.context.assert_owners()
        self.context.controller.clear_input_queue()
        self.context.controller.clear_last_input()
        # A partially failing release still needs the paired restore callback.
        self._input_released = True
        if self.context.release_input:
            self.context.release_input()
        if self.context.assert_owners is not None:
            self.context.assert_owners()

    def _stop_background_tasks(self):
        self._background_stopped = True
        self.context.stop_background_tasks()
        if self.context.assert_owners is not None:
            self.context.assert_owners()

    def _restore_owners(self):
        try:
            if self.context.assert_owners is not None:
                self.context.assert_owners()
            if self._input_released:
                if self.context.restore_input:
                    self.context.restore_input()
                self._input_released = False
            if self._background_stopped:
                if self.context.restore_background_tasks:
                    self.context.restore_background_tasks()
                self._background_stopped = False
            if self.context.assert_owners is not None:
                self.context.assert_owners()
        except BaseException:
            # A second callback attempt is not independent proof that a
            # partially restored input/background owner is safe for fallback.
            self._owner_restore_failed = True
            raise

    def _restore(self, _snapshot):
        self._restore_owners()
        self.context.controller.clear_input_queue()
        self._release_gate = True
        if self.renderer is None:
            self.renderer = self._new_renderer()

    def setup(self):
        qualification(self.context).assert_safe()
        self.health.assert_no_foreground()
        if self.health.choose_interface() != "project":
            raise ContractError("CLASSIC_SELECTED", "The untouched classic frontend is selected before optional project imports")
        if not callable(getattr(self.context.controller, "get_input", None)) or not callable(getattr(self.context.display, "present", None)) or not self.context.quiescent():
            raise ContractError("BUSY_SESSION", "An initialized, idle existing PyUI session is required")
        # Only now import optional project UI dependencies, after recovery and
        # source/runtime qualification have selected this mode.
        from .app import Dispatcher, _restore_navigation
        from .adapters.spruce import PyUIModelProvider, SpruceBackend
        from .settings import SettingsStore
        from .ui.model import NavigationModel
        deps = self.dependencies
        provider = (deps.provider_factory or self.context.model_provider_factory or PyUIModelProvider.from_pyui)(
            self.context.sd_root, device=self.context.device, release_resources=self._close_project_renderer,
            quiescent=self.context.quiescent, tool_list=self.context.tool_list,
            tool_actions=self.context.tool_actions, mode_actions=self.context.mode_actions)
        self.backend = (deps.backend_factory or SpruceBackend)(self.context.sd_root, read_only=False, managers=provider)
        if self.context.resume_evidence_provider is not None:
            self.backend.set_verified_resume_evidence(self.context.resume_evidence_provider())
        self.settings = (deps.settings_factory or SettingsStore)(str(self.context.state_dir))
        self.settings.recover()
        self.model = (deps.model_factory or NavigationModel)(demo=False, restored_state=_restore_navigation(self.context.state_dir))
        self.coordinator = LaunchCoordinator(self.registry, LaunchHooks(self._snapshot,
            self._stop_background_tasks, self._close_project_renderer, self._release_input, self._restore),
            preflight=lambda: qualification(self.context), exclusive=self.exclusive, health=self.health)
        runner = self
        class EmbeddedDispatcher(Dispatcher):
            def _dispatch(self, method, params):
                if method == "spruce.advanced":
                    self._fields(params, ("route",), ("route",))
                    route = self._text(params, "route", limit=32)
                    if route not in set(runner.ADVANCED_ROUTES) | (runner.SOURCE_ROUTES - {"game-options"}):
                        raise ContractError("UNKNOWN_ROUTE", "This is not a registered classic spruce menu route")
                    runner._pending_advanced = route
                    return {"state": "releasing_ui"}
                if method == "tools.list":
                    result = super()._dispatch(method, params)
                    if callable(getattr(runner.context.main_menu, "launch_selection", None)):
                        result = list(result) + [{"id": "route:" + route, "tool_id": "route:" + route,
                            "label": label, "description": "Existing spruce interface", "available": True}
                            for route, label in (("settings", "All spruce system settings"), ("apps", "All installed spruce apps"), ("collections", "Spruce collections"))]
                    return result
                if method == "tool.launch" and isinstance(params.get("tool_id"), str) and params["tool_id"].startswith("route:"):
                    self._fields(params, ("tool_id",), ("tool_id",))
                    return self._dispatch("spruce.advanced", {"route": params["tool_id"][6:]})
                return super()._dispatch(method, params)
        self.dispatcher = EmbeddedDispatcher(self.backend, self.settings, self.context.state_dir,
                                             launch_bridge=_LaunchBridge(self),
                                             control_adapter=self.context.control_adapter,
                                             theme_manager=self.context.theme_manager,
                                             hardware_adapter=self.context.hardware_adapter,
                                             experience_manager=self.context.experience_manager,
                                             game_options_handler=self._schedule_game_options
                                             if self.context.game_options_handler is not None else None)
        self._commands(self.model.initial_commands())
        self.renderer = self._new_renderer()

    def _commands(self, commands):
        from .app import error_fields
        pending = list(commands)
        while pending:
            command = pending.pop(0)
            try:
                pending.extend(self.model.receive(command, self.dispatcher.dispatch(command.method, command.params)))
            except Exception as exc:
                self.model.error(command, *error_fields(exc))

    def _schedule_game_options(self, game_id):
        self.backend._game(game_id)
        if game_id not in getattr(self.backend.provider, "models", {}):
            raise ContractError("MODEL_UNAVAILABLE", "The existing selected game model is unavailable")
        self._pending_game_options = game_id
        self._pending_advanced = "game-options"
        return {"state": "releasing_ui"}

    def open_advanced(self, route: str):
        qualification(self.context).assert_safe()
        if route in self.ADVANCED_ROUTES and callable(getattr(self.context.main_menu, "launch_selection", None)):
            callback = lambda: self.context.main_menu.launch_selection(self.ADVANCED_ROUTES[route])
        elif route in {"wifi", "bluetooth"}:
            menu = getattr(getattr(self.context.main_menu, "settings_menu", None),
                           "wifi_menu" if route == "wifi" else "bt_menu", None)
            callback = getattr(menu, "show_wifi_menu" if route == "wifi" else "show_bluetooth_menu", None)
        elif route == "game-options" and callable(self.context.game_options_handler):
            model = getattr(self.backend.provider, "models", {}).get(self._pending_game_options)
            if model is None:
                raise ContractError("MODEL_UNAVAILABLE", "The existing game menu lost its selected source model")
            callback = lambda: self.context.game_options_handler(model)
        else:
            callback = None
        if not callable(callback):
            raise ContractError("UNKNOWN_ROUTE", "Existing spruce menu route is unavailable")
        if not self.context.quiescent():
            raise ContractError("BUSY_SESSION", "Finish the existing foreground operation before opening another menu")
        self._snapshot()
        self._stop_background_tasks()
        self._close_project_renderer()
        self.context.controller.clear_input_queue()
        self.context.controller.clear_last_input()
        self._release_input()
        # A fixed in-memory menu value, never a command string. The existing
        # menu may perform its normal game/app handoff and exit this process.
        token = self.health.begin_foreground("advanced:" + route)
        self._advanced_in_progress = True
        try:
            callback()
            if self.context.quiescent() is not True:
                raise ContractError("BUSY_SESSION", "The existing menu returned without a verified idle session")
        except Exception as exc:
            raise ContractError("HANDOFF_UNCERTAIN", "The existing advanced menu may have staged a foreground action; fallback is blocked") from exc
        self.health.clear_foreground(token, verified=True)
        self._advanced_in_progress = False
        self._pending_advanced = None
        self._pending_game_options = None
        self.model.exit_request = None
        self._restore(None)
        self._commands(self.model.initial_commands())

    def run(self, *, max_frames: int = 0, scripted_actions=()) -> EmbeddedResult:
        if type(max_frames) is not int or max_frames < 0 or max_frames > 100000:
            raise ContractError("INVALID_LIMIT", "Embedded frame limit is invalid")
        if self.attempt_id is None:
            if self.health.choose_interface() != "project":
                raise ContractError("CLASSIC_SELECTED", "The untouched classic frontend is selected before optional project imports")
            state = self.health.begin()
            if state["attempt"]["interface"] != "project":
                raise ContractError("CLASSIC_SELECTED", "The existing classic frontend is selected")
            self.attempt_id = state["attempt"]["id"]
        if self.model is None:
            self.setup()
        scripted = iter(scripted_actions)
        try:
            while max_frames == 0 or self.frames < max_frames:
                now = time.monotonic()
                self.renderer.render(self.model.snapshot(now), now)
                self.context.display.present()
                self.frames += 1
                # Readiness includes a successful service poll of the existing
                # input owner, even when host tests inject navigation actions.
                if self._release_gate and not self.context.controller.still_held_down():
                    self.context.controller.clear_input_queue()
                    self._release_gate = False
                has_input = self.context.controller.get_input(timeout=1 / 60)
                if not self.ready:
                    self.health.mark_ready(first_frame=True, input_ready=True, settings_ready=True, attempt_id=self.attempt_id)
                    self.ready = True
                action = next(scripted, None)
                if action is None and has_input and not self._release_gate:
                    action = logical_action(self.context.controller.last_input(), self.model.preferences, self.context.device)
                if action:
                    self._commands(self.model.handle(action))
                    if action not in {"left", "right", "up", "down"}:
                        self._release_gate = True
                if self._pending_advanced:
                    self.open_advanced(self._pending_advanced)
                if self.dispatcher.pending_launch:
                    intent = self.dispatcher.pending_launch
                    receipt = self.coordinator.launch(intent["action_id"], mode=intent["mode"])
                    return EmbeddedResult("delegated", self.frames, self.context.execution_environment, self.ready)
                if self.model.exit_request in {"classic", "quit"}:
                    state = self.health.record()
                    self.health.request("classic", state["generation"])
                    self._snapshot()
                    return EmbeddedResult("classic", self.frames, self.context.execution_environment, self.ready)
            self._snapshot()
            return EmbeddedResult("frame_limit", self.frames, self.context.execution_environment, self.ready)
        finally:
            self._close_project_renderer()

    def release_for_fallback(self) -> bool:
        if self._owner_restore_failed or self._advanced_in_progress or (self.coordinator and self.coordinator.state in {LaunchState.DELEGATED, LaunchState.DELEGATING, LaunchState.BLOCKED}):
            return False
        try:
            if self.context.assert_owners is not None:
                self.context.assert_owners()
            self._close_project_renderer()
            self._restore_owners()
            self.context.controller.clear_input_queue()
            if self.context.assert_owners is not None:
                self.context.assert_owners()
            return self.context.quiescent() is True
        except Exception:
            return False


def context_from_running_pyui(main_menu: Any, *, state_dir: str | Path,
                              inventory: Mapping[str, Any], profile: Mapping[str, Any],
                              preferences: Mapping[str, Any], quiescent: Callable[[], bool],
                              stop_background_tasks: Callable[[], None], **kwargs) -> EmbeddedContext:
    """Source bootstrap adapter; never calls Display.init or Controller.init.

    Lifecycle callbacks must be supplied by the qualified source integration;
    the pinned base exposes no generic safe stop-all-background-jobs method.
    """
    from devices.device import Device
    from display.display import Display
    from controller.controller import Controller
    return EmbeddedContext("/mnt/SDCARD", state_dir, Device.get_device(), Display, Controller,
                           main_menu, inventory, profile, preferences, quiescent,
                           stop_background_tasks, **kwargs)
