"""Original frontend handoff contracts; spruce remains the process owner.

This module never starts a process, evaluates a command, writes hardware, or
interprets executable data from a library snapshot. Trusted application code
registers callbacks bound to the installed spruce/PyUI provider.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from enum import Enum
import re
import threading
from typing import Any, Callable, Mapping
import uuid


SPRUCE_COMMIT = "d45ff8dfe5756147522b04ae5863d17a90e88b54"
POWER_OFF_ROUTE = "/mnt/SDCARD/spruce/scripts/save_poweroff.sh"


class ContractError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.retryable = code, retryable

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "retryable": self.retryable}


class HandoffRejected(ContractError):
    """Backend guarantees it did not stage a launch or start another owner."""


class LaunchState(str, Enum):
    IDLE = "idle"
    VALIDATING = "validating"
    PREPARING = "preparing"
    RELEASING_UI = "releasing_ui"
    DELEGATING = "delegating"
    DELEGATED = "delegated"
    COLLECTING_RESULT = "collecting_result"
    RESTORING_UI = "restoring_ui"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class LaunchIntent:
    action_id: str
    mode: str
    request_id: str


@dataclass(frozen=True)
class LaunchReceipt:
    request_id: str
    action_id: str
    state: str
    backend_mode: str
    delegated: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegisteredAction:
    action_id: str
    callback: Callable[[LaunchIntent], Any]
    kind: str = "game"
    allowed_modes: tuple[str, ...] = ("normal", "fresh")
    backend_mode: str = "fake"
    validate: Callable[[LaunchIntent], None] | None = None


def _identifier(value: str) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,191}", value))


class ActionRegistry:
    """In-memory capability registry. It deliberately has no from_json loader."""
    def __init__(self) -> None:
        self._actions: dict[str, RegisteredAction] = {}
        self._lock = threading.RLock()

    def register(self, action_id: str, callback: Callable[[LaunchIntent], Any], *,
                 kind: str = "game", allowed_modes: tuple[str, ...] = ("normal", "fresh"),
                 backend_mode: str = "fake", validate: Callable[[LaunchIntent], None] | None = None) -> None:
        if not _identifier(action_id) or not callable(callback) or kind not in {"game", "tool"}:
            raise ContractError("INVALID_ACTION", "Action registration requires a bounded ID and trusted callback")
        if backend_mode not in {"fake", "spruce"} or not allowed_modes or any(m not in {"normal", "fresh", "resume"} for m in allowed_modes):
            raise ContractError("INVALID_ACTION", "Action backend or supported launch modes are invalid")
        with self._lock:
            if action_id in self._actions:
                raise ContractError("DUPLICATE_ACTION", "Action ID is already registered")
            self._actions[action_id] = RegisteredAction(action_id, callback, kind, tuple(allowed_modes), backend_mode, validate)

    def resolve(self, action_id: str) -> RegisteredAction:
        with self._lock:
            if not _identifier(action_id) or action_id not in self._actions:
                raise ContractError("UNKNOWN_ACTION", "This item has no registered launch capability")
            return self._actions[action_id]


@dataclass
class LaunchHooks:
    snapshot: Callable[[], Any]
    stop_background_tasks: Callable[[], None]
    release_renderer: Callable[[], None]
    release_input: Callable[[], None]
    restore_ui: Callable[[Any], None]


@dataclass(frozen=True)
class PreflightReport:
    errors: tuple[tuple[str, str], ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def safe(self) -> bool:
        return not self.errors

    def assert_safe(self) -> None:
        if self.errors:
            code, message = self.errors[0]
            raise ContractError(code, message)

    def as_dict(self) -> dict[str, Any]:
        return {"safe": self.safe, "errors": [{"code": c, "message": m} for c, m in self.errors],
                "warnings": list(self.warnings)}


def original_tsp_preflight(inventory: Mapping[str, Any], preferences: Mapping[str, Any],
                           profile: Mapping[str, Any]) -> PreflightReport:
    """Check read-only evidence; this never registers an action or launches one.

    A snapshot may be examined with this function, but cannot satisfy the live
    inventory/physical-qualification gates. Expected hashes must come from a
    separately qualified profile, not from the snapshot being checked.
    """
    errors: list[tuple[str, str]] = []
    if not isinstance(inventory, Mapping) or not isinstance(preferences, Mapping) or not isinstance(profile, Mapping):
        return PreflightReport((("INVALID_EVIDENCE", "Preflight inputs must be mappings"),))
    if inventory.get("model") != "TG5040" or inventory.get("platform") != "SmartPro" or inventory.get("architecture") != "aarch64":
        errors.append(("UNSUPPORTED_DEVICE", "A positive original TG5040 SmartPro ARM64 identity is required"))
    if profile.get("source_commit") != SPRUCE_COMMIT or inventory.get("source_commit") != SPRUCE_COMMIT:
        errors.append(("UNSUPPORTED_SOURCE", "The selected spruce source revision does not match the qualified profile"))
    if profile.get("firmware_version") != "1.1.1" or inventory.get("firmware_version") != profile.get("firmware_version"):
        errors.append(("UNSUPPORTED_FIRMWARE", "Installed firmware does not match the original-Smart-Pro profile"))
    expected, observed = profile.get("required_hashes"), inventory.get("hashes")
    if not isinstance(expected, Mapping) or not expected or not isinstance(observed, Mapping):
        errors.append(("UNQUALIFIED_PROFILE", "A nonempty independently qualified firmware/runtime hash inventory is required"))
    else:
        for path, digest in expected.items():
            if not isinstance(path, str) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                errors.append(("UNQUALIFIED_PROFILE", "The profile contains an invalid SHA-256 identity"))
                break
            if observed.get(path) != digest:
                errors.append(("RUNTIME_HASH_MISMATCH", "An installed firmware/runtime file differs from the qualified profile"))
                break
    if preferences.get("enableButtonWatchers") is not False:
        errors.append(("UNSAFE_POWER_PREFERENCES", "Keep spruce enableButtonWatchers=false to preserve its power owner"))
    if preferences.get("poweroffCmd") != POWER_OFF_ROUTE:
        errors.append(("UNSAFE_POWER_PREFERENCES", "Power off must use the existing spruce staged save/poweroff route"))
    if inventory.get("live") is not True or profile.get("physical_qualification") is not True:
        errors.append(("HARDWARE_UNQUALIFIED", "Offline snapshots and unqualified profiles cannot authorize device handoff"))
    return PreflightReport(tuple(errors), ("Host evidence does not establish graphics, save, sleep or USB behavior on hardware.",))


@dataclass(frozen=True)
class TransitionBackend:
    callback: Callable[[], Any]
    backend_mode: str = "fake"
    qualified: bool = False
    reboot_required: bool = True


@dataclass(frozen=True)
class TransitionReceipt:
    operation: str
    request_id: str
    backend_mode: str
    delegated: bool
    reboot_required: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExclusiveTransition:
    """Frontend activity guard, not a USB driver or a process supervisor."""
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._leases: dict[str, str] = {}
        self._operation: str | None = None
        self._requests: dict[str, TransitionReceipt | ContractError] = {}

    @property
    def operation(self) -> str | None:
        with self._lock:
            return self._operation

    def acquire(self, kind: str) -> str:
        if kind not in {"game", "index", "write"}:
            raise ContractError("INVALID_ACTIVITY", "Unknown guarded frontend activity")
        with self._lock:
            if self._operation:
                raise ContractError("BUSY_EXCLUSIVE", "USB/power handoff is exclusive", True)
            if kind == "game" and "game" in self._leases.values():
                raise ContractError("BUSY_GAME", "A foreground handoff already owns the session", True)
            token = uuid.uuid4().hex
            self._leases[token] = kind
            return token

    def release(self, token: str) -> None:
        with self._lock:
            if token not in self._leases:
                raise ContractError("INVALID_ACTIVITY", "Activity lease is unknown or already released")
            del self._leases[token]

    @contextmanager
    def activity(self, kind: str):
        token = self.acquire(kind)
        try:
            yield token
        finally:
            self.release(token)

    def perform(self, operation: str, backend: TransitionBackend, *, request_id: str | None = None) -> TransitionReceipt:
        request_id = request_id or uuid.uuid4().hex
        if operation not in {"usb", "power"} or not _identifier(request_id):
            raise ContractError("INVALID_TRANSITION", "Unknown exclusive transition or invalid request ID")
        if not isinstance(backend, TransitionBackend) or not callable(backend.callback) or backend.backend_mode not in {"fake", "spruce"}:
            raise ContractError("INVALID_BACKEND", "An injected registered transition backend is required")
        if backend.backend_mode == "spruce" and not backend.qualified:
            raise ContractError("HARDWARE_UNQUALIFIED", "The device handoff backend has not been qualified")
        if operation == "usb" and not backend.reboot_required:
            raise ContractError("INVALID_TRANSITION", "The selected spruce USB route returns through reboot")
        with self._lock:
            prior = self._requests.get(request_id)
            if prior is not None:
                if isinstance(prior, ContractError):
                    raise prior
                if prior.operation != operation:
                    raise ContractError("REQUEST_CONFLICT", "Request ID was already used for another operation")
                return prior
            if len(self._requests) >= 1024:
                raise ContractError("REQUEST_LIMIT", "Exclusive request history is full; restart safely")
            if self._operation or self._leases:
                raise ContractError("BUSY_ACTIVITY", "Finish game, indexing and writes before USB/power handoff", True)
            self._operation = operation
        try:
            backend.callback()
        except HandoffRejected as exc:
            with self._lock:
                self._operation = None
                self._requests[request_id] = exc
            raise
        except BaseException as exc:
            error = ContractError("HANDOFF_UNCERTAIN", "Exclusive backend outcome is unknown; no new frontend activity may start")
            with self._lock:
                self._requests[request_id] = error
            raise error from exc
        receipt = TransitionReceipt(operation, request_id, backend.backend_mode, True, backend.reboot_required)
        with self._lock:
            self._requests[request_id] = receipt
            # Only explicit host fakes may return directly. Device USB/power
            # remains exclusive until the documented reboot/exit occurs.
            if backend.backend_mode == "fake":
                self._operation = None
        return receipt


class LaunchCoordinator:
    _next = {
        LaunchState.IDLE: {LaunchState.VALIDATING},
        LaunchState.VALIDATING: {LaunchState.PREPARING, LaunchState.IDLE},
        LaunchState.PREPARING: {LaunchState.RELEASING_UI, LaunchState.RESTORING_UI},
        LaunchState.RELEASING_UI: {LaunchState.DELEGATING, LaunchState.RESTORING_UI},
        LaunchState.DELEGATING: {LaunchState.DELEGATED, LaunchState.RESTORING_UI, LaunchState.BLOCKED},
        LaunchState.DELEGATED: {LaunchState.COLLECTING_RESULT},
        LaunchState.COLLECTING_RESULT: {LaunchState.RESTORING_UI},
        LaunchState.RESTORING_UI: {LaunchState.IDLE, LaunchState.BLOCKED},
        LaunchState.BLOCKED: set(),
    }

    def __init__(self, registry: ActionRegistry, hooks: LaunchHooks, *,
                 preflight: Callable[[], PreflightReport] | None = None,
                 exclusive: ExclusiveTransition | None = None, health: Any = None) -> None:
        self.registry, self.hooks, self.preflight = registry, hooks, preflight
        self.exclusive, self.health = exclusive or ExclusiveTransition(), health
        self.state = LaunchState.IDLE
        self.trace: list[str] = [self.state.value]
        self._lock = threading.RLock()
        self._requests: dict[str, tuple[LaunchIntent, LaunchReceipt | ContractError | None]] = {}
        self._snapshot: Any = None
        self._lease: str | None = None
        self._active: LaunchReceipt | None = None
        self._foreground_token: str | None = None

    def _transition(self, next_state: LaunchState) -> None:
        if next_state not in self._next[self.state]:
            raise ContractError("INVALID_STATE", "Unsafe frontend launch state transition")
        self.state = next_state
        self.trace.append(next_state.value)

    def _restore(self) -> None:
        self._transition(LaunchState.RESTORING_UI)
        try:
            self.hooks.restore_ui(self._snapshot)
        except BaseException as exc:
            self._transition(LaunchState.BLOCKED)
            raise ContractError("UI_RESTORE_FAILED", "Frontend restoration failed; manual recovery is required") from exc
        if self._lease is not None:
            self.exclusive.release(self._lease)
            self._lease = None
        self._active = None
        self._transition(LaunchState.IDLE)

    def launch(self, action_id: str, *, mode: str = "normal", request_id: str | None = None) -> LaunchReceipt:
        request_id = request_id or uuid.uuid4().hex
        if not _identifier(request_id):
            raise ContractError("INVALID_REQUEST", "Launch request ID must be a bounded identifier")
        intent = LaunchIntent(action_id, mode, request_id)
        with self._lock:
            if request_id in self._requests:
                old_intent, result = self._requests[request_id]
                if intent != old_intent:
                    raise ContractError("REQUEST_CONFLICT", "Launch request ID was already used with different parameters")
                if isinstance(result, ContractError):
                    raise result
                if result is None:
                    raise ContractError("BUSY_REQUEST", "This launch request is still being processed", True)
                return result
            if self.state != LaunchState.IDLE:
                raise ContractError("BUSY_GAME", "A foreground handoff or recovery is still active", True)
            if len(self._requests) >= 1024:
                raise ContractError("REQUEST_LIMIT", "Launch request history is full; restart safely")
            self._requests[request_id] = (intent, None)
            self._transition(LaunchState.VALIDATING)
        touched_ui = False
        invoked = False
        try:
            action = self.registry.resolve(action_id)
            if mode not in action.allowed_modes:
                raise ContractError("UNSUPPORTED_MODE", "This action has no verified capability for the requested mode")
            if action.backend_mode == "spruce":
                if self.preflight is None:
                    raise ContractError("HARDWARE_UNQUALIFIED", "A qualified original-Smart-Pro preflight is required")
                report = self.preflight()
                if not isinstance(report, PreflightReport):
                    raise ContractError("INVALID_EVIDENCE", "Preflight did not return a typed qualification result")
                report.assert_safe()
            if action.validate:
                action.validate(intent)
            if self.health:
                self.health.assert_no_foreground()
            if self.exclusive.operation:
                raise ContractError("BUSY_EXCLUSIVE", "USB/power handoff is exclusive", True)
            self._transition(LaunchState.PREPARING)
            self._snapshot = self.hooks.snapshot()
            touched_ui = True
            self.hooks.stop_background_tasks()
            self._lease = self.exclusive.acquire("game")
            self._transition(LaunchState.RELEASING_UI)
            self.hooks.release_renderer()
            self.hooks.release_input()
            if self.health:
                self._foreground_token = self.health.begin_foreground(request_id)
            self._transition(LaunchState.DELEGATING)
            invoked = True
            action.callback(intent)
            self._transition(LaunchState.DELEGATED)
            receipt = LaunchReceipt(request_id, action_id, self.state.value, action.backend_mode, True)
            self._active = receipt
            self._requests[request_id] = (intent, receipt)
            return receipt
        except SystemExit:
            # The existing PyUI device callback normally exits its frontend
            # after staging a command. Preserve that ownership transfer and
            # let principal.sh run; never catch it and reopen the display.
            if invoked:
                self._transition(LaunchState.DELEGATED)
                receipt = LaunchReceipt(request_id, action_id, self.state.value, action.backend_mode, True)
                self._active = receipt
                self._requests[request_id] = (intent, receipt)
                raise
            self.state = LaunchState.BLOCKED
            self.trace.append(self.state.value)
            raise
        except BaseException as exc:
            if invoked and not isinstance(exc, HandoffRejected):
                self._transition(LaunchState.BLOCKED)
                error = ContractError("HANDOFF_UNCERTAIN", "The backend may own the display or a game; automatic UI restoration is blocked")
            else:
                try:
                    if self._foreground_token is not None and self.health:
                        self.health.clear_foreground(self._foreground_token, verified=True)
                        self._foreground_token = None
                    if touched_ui:
                        self._restore()
                    elif self.state == LaunchState.PREPARING:
                        # Snapshot failed before any resource release.
                        self._transition(LaunchState.RESTORING_UI)
                        self._transition(LaunchState.IDLE)
                    else:
                        self._transition(LaunchState.IDLE)
                    error = exc if isinstance(exc, ContractError) else ContractError("PREPARATION_FAILED", "Frontend launch preparation failed; the prior view was restored")
                except BaseException as restore_error:
                    self.state = LaunchState.BLOCKED
                    self.trace.append(self.state.value)
                    error = restore_error if isinstance(restore_error, ContractError) else ContractError("UI_RESTORE_FAILED", "Cannot prove that frontend restoration is safe")
            self._requests[request_id] = (intent, error)
            raise error from exc

    def return_from_backend(self, request_id: str, *, verified: bool = False) -> None:
        """Only an external spruce return seam (or explicit fake) may call this.

        A callback returning from staging is not evidence that its game exited.
        """
        with self._lock:
            if self.state != LaunchState.DELEGATED or self._active is None or self._active.request_id != request_id:
                raise ContractError("INVALID_STATE", "No matching delegated frontend action can be collected")
            if self._active.backend_mode != "fake" and not verified:
                raise ContractError("RETURN_UNVERIFIED", "The existing backend must establish that foreground ownership ended")
            self._transition(LaunchState.COLLECTING_RESULT)
            if self._foreground_token is not None and self.health:
                self.health.clear_foreground(self._foreground_token, verified=True)
                self._foreground_token = None
            self._restore()
