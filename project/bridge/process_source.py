"""Bind real initialized PyUI authorities through its existing process exit.

Normal source workers and input descriptors remain owned by PyUI. Preparing a
handoff does not claim to stop them: principal's child-subreaper must observe
the complete source process subtree exit before running its staged command.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Callable, Mapping

from .bootstrap import ExistingPyUIModels, InitializedPyUIBinding, PRINCIPAL_PATH
from .lifecycle import _Task
from psp_shell.health import FrontendHealth, _atomic, _read
from psp_shell.runtime import ContractError, SPRUCE_COMMIT, original_tsp_preflight


@dataclass(frozen=True)
class ProcessSourceConfiguration:
    """Reviewed source references plus independent expected/live evidence.

    True profile flags in host fixtures exercise code; they establish no device
    qualification. The fixed shipped qualified_runtime module returns None.
    completion_observer receives a sealed principal completion in-process and
    must separately establish all state/config writer evidence it needs.
    """

    profile: Mapping[str, Any]
    inventory: Callable[[], Mapping[str, Any]]
    preferences: Callable[[], Mapping[str, Any]]
    state_dir: str | Path = "/mnt/SDCARD/App/PSPMode/state"
    sd_root: str | Path = "/mnt/SDCARD"
    staged_command: str | Path = "/tmp/cmd_to_run.sh"
    private_runtime: str | Path = "/tmp/trimui-project-principal"
    adapters: Callable[[Any, Any], Mapping[str, Any]] | None = None
    completion_observer: Callable[[Any], None] | None = None
    command_environment: Callable[[Any, Any], Mapping[str, str]] | None = None
    resume_evidence: Callable[[], Any] | None = None
    mode_actions: Callable[[Any], Mapping[str, Any]] | None = None
    execution_environment: str = "device"
    experimental_session: Any = None

    def __post_init__(self):
        if (not isinstance(self.profile, Mapping) or not callable(self.inventory) or
                not callable(self.preferences) or self.adapters is not None and not callable(self.adapters) or
                self.completion_observer is not None and not callable(self.completion_observer) or
                self.command_environment is not None and not callable(self.command_environment) or
                self.resume_evidence is not None and not callable(self.resume_evidence) or
                self.mode_actions is not None and not callable(self.mode_actions)):
            raise ContractError("INVALID_CONTEXT", "Process integration requires fixed reviewed configuration and live observations")
        object.__setattr__(self, "profile", copy.deepcopy(dict(self.profile)))
        for name in ("state_dir", "sd_root", "staged_command", "private_runtime"):
            object.__setattr__(self, name, Path(getattr(self, name)).absolute())

    def assert_safe(self):
        if self.experimental_session is not None:
            from .experimental_runtime import ExperimentalRuntimeSession
            if type(self.experimental_session) is not ExperimentalRuntimeSession:
                raise ContractError("INVALID_CONTEXT", "Private experiment requires the fixed reviewed in-memory session type")
            self.experimental_session.assert_configuration(self)
            return
        profile = self.profile
        if (not isinstance(profile.get("required_hashes"), Mapping) or
                any(profile.get(name) is not True for name in
                ("source_use_verified", "runtime_verified", "hardware_qualified", "process_exit_qualified")) or
                profile.get("source_commit") != SPRUCE_COMMIT or
                PRINCIPAL_PATH not in profile.get("required_hashes", {})):
            raise ContractError("TARGET_UNQUALIFIED", "The source process/principal integration has not been independently qualified")
        if self.execution_environment == "host-fixture":
            if (profile.get("execution_environment") != "host-fixture" or
                    not str(profile.get("id", "")).startswith("host-fixture") or
                    self.sd_root == Path("/mnt/SDCARD") or Path("/mnt/SDCARD") in self.sd_root.parents):
                raise ContractError("INVALID_FIXTURE", "Host process fixtures cannot target a device card")
        elif self.execution_environment != "device":
            raise ContractError("INVALID_CONTEXT", "Unknown source process environment")
        else:
            from .principal_integration import SOURCE_BLOBS, REQUIRED_PROJECT_MODULES
            installed_modules = Path(__file__).resolve().parent.parent
            try:
                relative_modules = installed_modules.relative_to(self.sd_root.resolve()).as_posix()
            except ValueError as exc:
                raise ContractError("TARGET_UNQUALIFIED", "Source helpers must come from the fixed reviewed installed original payload") from exc
            if profile.get("module_root") != str(installed_modules):
                raise ContractError("TARGET_UNQUALIFIED", "The independently qualified fixed module path does not match this source installation")
            if self.private_runtime != Path("/tmp/trimui-project-principal"):
                raise ContractError("TARGET_UNQUALIFIED", "Principal capabilities must stay in the fixed private volatile runtime directory")
            required = set(SOURCE_BLOBS) | {relative_modules + "/" + path.removeprefix("app/")
                                                   for path in REQUIRED_PROJECT_MODULES}
            if not required.issubset(profile.get("required_hashes", {})):
                raise ContractError("TARGET_UNQUALIFIED", "Independent expected source and original-payload hashes are incomplete")
        expected = dict(profile)
        expected["physical_qualification"] = profile.get("hardware_qualified") is True
        observed = self.inventory()
        result = original_tsp_preflight(observed, self.preferences(), expected)
        if self.execution_environment == "host-fixture":
            if observed.get("live") is not False:
                raise ContractError("INVALID_FIXTURE", "Synthetic source process fixtures must report non-live observations")
            for code, message in result.errors:
                if code != "HARDWARE_UNQUALIFIED":
                    raise ContractError(code, message)
        else:
            result.assert_safe()


def configured_runtime() -> ProcessSourceConfiguration | None:
    # A fixed reviewed import; no configuration file supplies a module name.
    from .qualified_runtime import configuration
    value = configuration()
    if value is None:
        from .experimental_runtime import configuration as private_configuration
        value = private_configuration()
    if value is not None and type(value) is not ProcessSourceConfiguration:
        raise ContractError("INVALID_CONTEXT", "The fixed runtime module did not supply a typed source configuration")
    return value


class ProcessExitSourceTasks:
    """Keep existing workers until the principal observes this process exit.

    The renderer/input preparation callbacks record transition intent. They do
    not claim that Python's blocking input threads stopped or closed their fds.
    A rejected, unstaged transition can restore its intent without restarting
    any task. Once the existing device stages/exits, no in-process UI restarts.
    """

    def __init__(self, device, manager_startup, config: ProcessSourceConfiguration):
        self.device, self.config = device, config
        self.owner_thread = threading.get_ident()
        self._lock = threading.RLock()
        self._phase = "new"
        self._input_prepared = False
        self._writing = False
        self._startup = _Task("PyUI-device-startup", device.perform_startup_tasks, daemon=False)
        self._managers = _Task("PyUI-manager-startup", manager_startup, daemon=False)
        self._audio = _Task("PyUI-AudioRoute", device.watch_audio_route, daemon=True)
        self.assert_owners: Callable[[], None] | None = None
        self.source_game: Mapping[str, str] | None = None
        self.state_intent: Mapping[str, Any] | None = None

    def start(self):
        with self._lock:
            if self._phase != "new":
                raise ContractError("LIFECYCLE_ALREADY_STARTED", "Existing PyUI startup may run only once")
            self._phase = "starting"
            try:
                for task in (self._startup, self._managers, self._audio):
                    task.thread.start()
            except BaseException:
                self._phase = "failed"
                raise
            self._phase = "running"
        return self

    def _ready(self):
        return (threading.get_ident() == self.owner_thread and
                all(task.finished.is_set() and not task.failed and not task.thread.is_alive()
                    for task in (self._startup, self._managers)) and not self._audio.failed)

    def quiescent(self):
        with self._lock:
            if self.assert_owners is not None:
                self.assert_owners()
            return (self._phase in {"running", "prepared"} and self._ready() and not self._writing and
                    not os.path.lexists(self.config.staged_command))

    def stop_background_tasks(self):
        with self._lock:
            if not self.quiescent() or self._phase != "running":
                raise ContractError("BUSY_SESSION", "Existing source startup or a writer/handoff is active")
            self._phase = "prepared"

    def release_input(self):
        with self._lock:
            if self._phase != "prepared" or not self.quiescent():
                raise ContractError("BUSY_SESSION", "Source input release belongs to its pending process-exit transition")
            self._input_prepared = True

    def restore_input(self):
        with self._lock:
            if os.path.lexists(self.config.staged_command):
                raise ContractError("HANDOFF_UNCERTAIN", "A staged command blocks in-process input restoration")
            self._input_prepared = False

    def restore_background_tasks(self):
        with self._lock:
            if self._phase not in {"running", "prepared"} or os.path.lexists(self.config.staged_command):
                raise ContractError("HANDOFF_UNCERTAIN", "Source workers remain owned until process exit")
            self._phase = "running"
            self.source_game, self.state_intent = None, None

    @contextmanager
    def write_window(self):
        with self._lock:
            if self.config.experimental_session is not None:
                self.config.experimental_session.block("action_denied")
            if self._phase != "running" or not self.quiescent():
                raise ContractError("BUSY_SESSION", "Source settings writes and process handoffs share one owner window")
            self.config.assert_safe()
            self._writing = True
            try:
                yield
            finally:
                self._writing = False


def begin_process_source_tasks(device, manager_startup):
    global _source_tasks
    config = configured_runtime()
    if config is None:
        return None
    config.assert_safe()
    if _source_tasks is not None:
        raise ContractError("LIFECYCLE_ALREADY_STARTED", "The source process already owns its startup callbacks")
    _source_tasks = ProcessExitSourceTasks(device, manager_startup, config)
    return _source_tasks.start()


_source_tasks: ProcessExitSourceTasks | None = None
COMMAND_REQUEST = "principal-source-command.json"


def process_start(pid):
    try:
        with open("/proc/%d/stat" % pid, "rb") as source:
            raw = source.read(32769)
        fields = raw.rpartition(b")")[2].split()
        if len(raw) > 32768 or len(fields) <= 19 or fields[0] in {b"Z", b"X"}:
            return None
        return fields[19].decode("ascii")
    except (OSError, ValueError, UnicodeError):
        return None


@dataclass(frozen=True)
class SourceCommandRequest:
    foreground: Any
    command_sha256: str
    source_pid: int
    source_start: str
    source_game: Mapping[str, str] | None
    state_intent: Mapping[str, Any] | None

    @classmethod
    def read(cls, config):
        from .bootstrap import ForegroundIdentity
        value = _read(config.state_dir / COMMAND_REQUEST)
        if (set(value) != {"schema", "foreground", "command_sha256", "source_pid", "source_start", "source_game", "state_intent", "checksum"} or
                value["schema"] != 1 or type(value["schema"]) is not int or
                not isinstance(value["command_sha256"], str) or re.fullmatch("[0-9a-f]{64}", value["command_sha256"]) is None or
                type(value["source_pid"]) is not int or not 0 < value["source_pid"] < 2 ** 31 or
                not isinstance(value["source_start"], str) or not value["source_start"].isdigit() or len(value["source_start"]) > 32):
            raise ContractError("INVALID_SOURCE_REQUEST", "The source command correlation request is invalid")
        identity = value["foreground"]
        if (not isinstance(identity, dict) or set(identity) != {"token", "request_id", "boot_id", "generation"} or
                type(identity["generation"]) is not int or not 0 < identity["generation"] < 2 ** 53 or
                any(not isinstance(identity[k], str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,191}", identity[k]) is None
                    for k in ("token", "request_id", "boot_id"))):
            raise ContractError("INVALID_SOURCE_REQUEST", "The source command foreground identity is invalid")
        game = value["source_game"]
        if game is not None:
            if (not isinstance(game, dict) or set(game) != {"rom_relative", "system_id"} or
                    any(not isinstance(v, str) or not v or len(v) > 4096 or "\0" in v for v in game.values()) or
                    not game["rom_relative"].startswith("Roms/") or ".." in Path(game["rom_relative"]).parts or
                    "/" in game["system_id"] or "\\" in game["system_id"]):
                raise ContractError("INVALID_SOURCE_REQUEST", "The bounded source game context is invalid")
        intent = value["state_intent"]
        if intent is not None:
            if (not isinstance(intent, dict) or set(intent) != {"mode", "state_path", "state_sha256", "slot"} or
                    intent["mode"] != "resume" or type(intent["slot"]) is not int or not 0 <= intent["slot"] <= 99 or
                    not isinstance(intent["state_sha256"], str) or re.fullmatch("[0-9a-f]{64}", intent["state_sha256"]) is None or
                    not isinstance(intent["state_path"], str) or not intent["state_path"].startswith("/") or
                    len(intent["state_path"]) > 4096 or any(ord(c) < 32 for c in intent["state_path"])):
                raise ContractError("INVALID_SOURCE_REQUEST", "The bounded source Resume intent is invalid")
        return cls(ForegroundIdentity(**identity), value["command_sha256"], value["source_pid"], value["source_start"], game, intent)


def capture_state_resume_intent(state_path, state_sha256, slot):
    """Trusted typed Resume adapter records data before existing run_game.

    Principal independently checks this intent against its authenticated state
    capability store. This request cannot itself mint Resume eligibility.
    """
    tasks = _source_tasks
    if tasks is None or tasks._phase != "prepared" or not tasks._input_prepared:
        raise ContractError("HANDOFF_UNCERTAIN", "Resume intent needs the current prepared source process")
    if (not isinstance(state_path, str) or not state_path.startswith("/") or len(state_path) > 4096 or
            any(ord(c) < 32 for c in state_path) or not isinstance(state_sha256, str) or
            re.fullmatch("[0-9a-f]{64}", state_sha256) is None or type(slot) is not int or not 0 <= slot <= 99):
        raise ContractError("INVALID_SOURCE_REQUEST", "Resume intent requires the exact engine-generated state identity")
    tasks.state_intent = {"mode": "resume", "state_path": state_path, "state_sha256": state_sha256, "slot": slot}


def capture_existing_game(rom_info):
    """Called by the actual source run_game with its selected RomInfo."""
    tasks = _source_tasks
    if tasks is None:
        return
    from .bootstrap import ForegroundIdentity
    foreground = ForegroundIdentity.from_health(FrontendHealth(tasks.config.state_dir))
    if foreground is None:
        tasks.source_game = None
        return
    if tasks._phase != "prepared" or not tasks._input_prepared:
        raise ContractError("HANDOFF_UNCERTAIN", "The existing source game does not own a prepared project transition")
    root = tasks.config.sd_root.resolve(strict=True)
    path = Path(rom_info.rom_file_path).resolve(strict=True)
    relative = path.relative_to(root).as_posix()
    system = getattr(rom_info.game_system, "system_name", None)
    if not isinstance(system, str) or not system or "/" in system or "\\" in system or not relative.startswith("Roms/"):
        raise ContractError("INVALID_SOURCE_REQUEST", "The actual selected source game is outside its ROM identity")
    tasks.source_game = {"rom_relative": relative, "system_id": system}


def stage_existing_command(command):
    """Atomically preserve an actual existing-source command and its identity.

    The journal is a bounded correlation request, never a completion receipt or
    authority to load code. Its game path must be independently checked by any
    qualified state/config adapter. A missing journal leaves the handoff blocked.
    """
    config = configured_runtime()
    if config is not None and config.experimental_session is not None:
        config.experimental_session.block("action_denied")
    tasks = _source_tasks
    if tasks is None:
        return False
    from .bootstrap import ForegroundIdentity
    config, health = tasks.config, FrontendHealth(tasks.config.state_dir)
    expected = ForegroundIdentity.from_health(health)
    if expected is None:
        return False
    if (expected.boot_id != health.boot_id or tasks._phase != "prepared" or not tasks._input_prepared or
            not isinstance(command, str) or not command or "\0" in command):
        raise ContractError("HANDOFF_UNCERTAIN", "The source command lacks its current prepared process-exit transition")
    config.assert_safe()
    raw = command.encode("utf-8")
    if len(raw) > 1024 * 1024:
        raise ContractError("INVALID_SOURCE_REQUEST", "The existing source command exceeds its staging budget")
    journal = config.state_dir / COMMAND_REQUEST
    if os.path.lexists(config.staged_command) or os.path.lexists(journal):
        raise ContractError("HANDOFF_UNCERTAIN", "Existing command/request ownership must not be replaced")
    start = process_start(os.getpid())
    if start is None:
        raise ContractError("HANDOFF_UNCERTAIN", "The source process start identity is unavailable")
    fd, temporary = tempfile.mkstemp(prefix=".spruce-command-", dir=config.staged_command.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o700)
        os.link(temporary, config.staged_command)
        _atomic(journal, {"schema": 1, "foreground": asdict(expected),
            "command_sha256": hashlib.sha256(raw).hexdigest(), "source_pid": os.getpid(),
            "source_start": start, "source_game": tasks.source_game, "state_intent": tasks.state_intent})
        if ForegroundIdentity.from_health(health) != expected:
            raise ContractError("STALE_HANDOFF", "The foreground changed while staging the existing source command")
    finally:
        os.unlink(temporary)
    return True


def existing_models(device, builder) -> ExistingPyUIModels:
    """Wrap the source's normal initialized builder/managers; create none."""
    from menus.games.utils.favorites_manager import FavoritesManager
    from menus.games.utils.recents_manager import RecentsManager
    from menus.games.utils.rom_info import RomInfo
    from psp_shell.adapters.spruce import MAX_DEPTH, MAX_ENTRIES
    systems, roms = device.get_game_system_utils(), getattr(builder, "rom_utils", None)
    if (not callable(getattr(roms, "get_roms", None)) or
            not callable(getattr(builder, "resolve_display_name", None)) or
            not callable(getattr(builder, "get_image_path", None))):
        raise ContractError("MODELS_NOT_READY", "The existing source ROM builder has not initialized")

    def game_list(system_id):
        system = systems.get_game_system_by_name(system_id)
        if system is None:
            return
        pending, visited, count = [(None, 0)], set(), 0
        while pending:
            directory, depth = pending.pop()
            marker = os.path.realpath(directory) if directory else "<root>"
            if marker in visited or depth > MAX_DEPTH:
                continue
            visited.add(marker)
            files, folders = roms.get_roms(system, directory)
            for filename in files:
                count += 1
                if count > MAX_ENTRIES:
                    raise ContractError("MODEL_LIMIT", "The existing ROM manager exceeded its query budget")
                yield RomInfo(system, filename)
            pending.extend((folder, depth + 1) for folder in folders)
    return ExistingPyUIModels(systems, game_list, FavoritesManager, RecentsManager,
                              builder.resolve_display_name, builder.get_image_path)


def bind_initialized_source(main_menu, tasks: ProcessExitSourceTasks, builder):
    from devices.device import Device
    from display.display import Display
    from controller.controller import Controller
    config = configured_runtime()
    if (type(tasks) is not ProcessExitSourceTasks or config is not tasks.config or
            Device.get_device() is not tasks.device):
        raise ContractError("OWNER_CHANGED", "Bind only the current initialized source process session")
    config.assert_safe()
    health = FrontendHealth(config.state_dir)
    health.assert_no_foreground()
    popup = getattr(getattr(getattr(main_menu, "favorites_menu", None), "popup_menu", None), "run_game_select_popup_menu", None)
    binding = InitializedPyUIBinding(device=tasks.device, display=Display, controller=Controller,
        models=existing_models(tasks.device, builder), state_dir=config.state_dir, sd_root=config.sd_root,
        profile=config.profile, inventory=config.inventory, preferences=config.preferences,
        current_owners=lambda: (Device.get_device(), Display, Controller),
        quiescent=tasks.quiescent, stop_background_tasks=tasks.stop_background_tasks,
        restore_background_tasks=tasks.restore_background_tasks, release_input=tasks.release_input,
        restore_input=tasks.restore_input, execution_environment=config.execution_environment,
        resume_evidence_provider=config.resume_evidence,
        mode_actions=config.mode_actions(tasks.device) if config.mode_actions is not None else None,
        game_options_handler=popup if callable(popup) else None)
    tasks.assert_owners = binding._assert_owners
    adapters = config.adapters(tasks.device, tasks) if config.adapters is not None else {}
    if not isinstance(adapters, Mapping) or set(adapters) - {
            "control_adapter", "theme_manager", "hardware_adapter", "experience_manager",
            "performance_manager", "backup_adapter"}:
        raise ContractError("INVALID_CONTEXT", "Source adapters must use the fixed initialized adapter slots")
    binding.options.update(adapters)
    if config.experimental_session is not None:
        if adapters or config.resume_evidence is not None or config.mode_actions is not None:
            raise ContractError("EXPERIMENTAL_ACTION_DENIED", "View-only binding cannot install mutator or Resume adapters")
        binding.options.update(experimental_session=config.experimental_session,
                               game_options_handler=None, tool_actions={}, mode_actions={})
        from .pyui_entry import bind_experimental_context_factory
        bind_experimental_context_factory(binding, config.experimental_session, state_dir=config.state_dir)
        return binding
    if "hardware_adapter" not in adapters:
        from psp_shell.hardware_settings import FixedHardwareSettings
        def qualified():
            config.assert_safe()
            binding._assert_owners()
            return True
        binding.options["hardware_adapter"] = FixedHardwareSettings.from_initialized_device(tasks.device,
            qualified=qualified, write_window=tasks.write_window, current_device=Device.get_device)
    return binding.bind()
