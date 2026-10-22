"""Frontend-only health and recovery records, independent of optional UI code.

Checksums detect corruption; they are not package signatures or authorization.
These records do not enable spruce's Flip-only boot supervisor on Smart Pro.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable
import uuid

from .runtime import ContractError


_CHECKS = ("first_frame", "input", "settings")
_MAX_GENERATION = (1 << 53) - 1


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _signed(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result.pop("checksum", None)
    result["checksum"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object field")
        result[key] = value
    return result


def _read(path: Path) -> dict[str, Any]:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as source:
            raw = source.read(32769)
        if len(raw) > 32768:
            raise ValueError("health record exceeds limit")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite number")))
        if not isinstance(value, dict) or not isinstance(value.get("checksum"), str):
            raise ValueError("missing checksum")
        if not hmac.compare_digest(_signed(value)["checksum"], value["checksum"]):
            raise ValueError("checksum mismatch")
        return value
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        raise ContractError("CORRUPT_HEALTH", "Frontend health record is invalid or damaged") from exc


def _atomic(path: Path, value: dict[str, Any]) -> None:
    raw = _canonical(_signed(value)) + b"\n"
    if len(raw) > 32768:
        raise ContractError("HEALTH_LIMIT", "Frontend health record exceeds its size limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".frontend-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        if path.is_symlink():
            raise ContractError("UNSAFE_PATH", "Refusing a symlink in frontend recovery state")
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    except OSError as exc:
        raise ContractError("STORAGE_WRITE_FAILED", "Cannot durably replace frontend recovery state") from exc
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _boot_id() -> str:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError as exc:
        raise ContractError("BOOT_ID_UNAVAILABLE", "Cannot establish boot identity for safe frontend recovery") from exc
    if not value or len(value) > 128:
        raise ContractError("BOOT_ID_UNAVAILABLE", "Invalid boot identity")
    return value


def _pid_start(pid: int) -> str | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        parts = stat[stat.rindex(")") + 1:].split()
        if parts[0] in {"Z", "X"}:
            return None
        return parts[19]
    except (OSError, ValueError, IndexError):
        return None


def _owner_alive(pid: int, start: str) -> bool:
    return _pid_start(pid) == start


class FrontendHealth:
    """One writer for frontend health; package current.json has another owner.

    Default device state is App/PSPMode/state. boot_id/process_alive injection
    exists for deterministic host fault fixtures, not target qualification.
    """
    def __init__(self, state_dir: str | Path, *, boot_id: str | None = None,
                 process_alive: Callable[[int, str], bool] | None = None) -> None:
        self.directory = Path(state_dir).absolute()
        self.primary = self.directory / "frontend-health.json"
        self.backup = self.directory / "frontend-health.last-good.json"
        self.foreground = self.directory / "foreground-handoff.json"
        self.marker = self.directory / "force-classic"
        self.boot_id = boot_id or _boot_id()
        if not isinstance(self.boot_id, str) or not self.boot_id or len(self.boot_id) > 128:
            raise ContractError("BOOT_ID_UNAVAILABLE", "Invalid boot identity")
        self.process_alive = process_alive or _owner_alive
        self._own_attempt: str | None = None

    @contextmanager
    def _lock(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.directory / ".frontend-health.lock", os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ContractError("BUSY_HEALTH", "Another frontend health transaction is active", True) from exc
            yield
        finally:
            os.close(descriptor)

    @staticmethod
    def _initial() -> dict[str, Any]:
        return _signed({"schema": 1, "generation": 0, "stable": "classic", "pending": None,
                        "readiness": {key: False for key in _CHECKS}, "failures": 0,
                        "fallback_used": False, "blocked": False, "attempt": None})

    @staticmethod
    def _validate(value: dict[str, Any]) -> dict[str, Any]:
        if type(value.get("schema")) is int and value["schema"] > 1:
            raise ContractError("FUTURE_SCHEMA", "A newer frontend health schema must not be overwritten")
        required = {"schema", "generation", "stable", "pending", "readiness", "failures", "fallback_used", "blocked", "attempt", "checksum"}
        if set(value) != required or value["schema"] != 1 or type(value["schema"]) is not int:
            raise ContractError("CORRUPT_HEALTH", "Unknown frontend health fields or schema")
        if type(value["generation"]) is not int or not 0 <= value["generation"] <= _MAX_GENERATION:
            raise ContractError("CORRUPT_HEALTH", "Invalid frontend generation")
        if not isinstance(value["stable"], str) or value["stable"] not in {"classic", "project"} or (value["pending"] is not None and (not isinstance(value["pending"], str) or value["pending"] not in {"classic", "project"})):
            raise ContractError("CORRUPT_HEALTH", "Invalid interface selection")
        checks = value["readiness"]
        if not isinstance(checks, dict) or set(checks) != set(_CHECKS) or any(type(v) is not bool for v in checks.values()):
            raise ContractError("CORRUPT_HEALTH", "Invalid frontend readiness evidence")
        if type(value["failures"]) is not int or not 0 <= value["failures"] <= 1000000:
            raise ContractError("CORRUPT_HEALTH", "Invalid frontend failure counter")
        if type(value["fallback_used"]) is not bool or type(value["blocked"]) is not bool:
            raise ContractError("CORRUPT_HEALTH", "Invalid frontend recovery flags")
        attempt = value["attempt"]
        if attempt is not None:
            fields = {"id", "boot_id", "pid", "start_id", "interface"}
            if not isinstance(attempt, dict) or set(attempt) != fields or not isinstance(attempt["interface"], str) or attempt["interface"] not in {"classic", "project"} or any(not isinstance(attempt[k], str) or not attempt[k] or len(attempt[k]) > 128 for k in ("id", "boot_id", "start_id")) or type(attempt["pid"]) is not int or attempt["pid"] <= 0:
                raise ContractError("CORRUPT_HEALTH", "Invalid frontend startup identity")
        if value["fallback_used"] and (value["stable"] != "classic" or value["pending"] == "project"):
            raise ContractError("CORRUPT_HEALTH", "Invalid classic fallback selection")
        return value

    def _load(self) -> dict[str, Any]:
        if not os.path.lexists(self.primary) and not os.path.lexists(self.backup):
            return self._initial()
        if os.path.lexists(self.primary):
            try:
                return self._validate(_read(self.primary))
            except ContractError as exc:
                if exc.code == "FUTURE_SCHEMA":
                    raise
        value = self._initial()
        if os.path.lexists(self.backup):
            try:
                value = self._validate(_read(self.backup))
            except ContractError as exc:
                if exc.code == "FUTURE_SCHEMA":
                    raise
        # Never reactivate a stale project version from a backup after a
        # damaged transaction. The separate foreground tombstone is checked
        # before any classic fallback is selected.
        value["stable"], value["pending"], value["attempt"] = "classic", None, None
        value["readiness"] = dict.fromkeys(_CHECKS, False)
        value["failures"] = min(value["failures"] + 1, 1000000)
        value["fallback_used"], value["blocked"] = True, False
        return _signed(value)

    @staticmethod
    def _generation(value: dict[str, Any], expected: int | None) -> None:
        if expected is not None and (type(expected) is not int or expected != value["generation"]):
            raise ContractError("STALE_GENERATION", "Frontend selection changed since it was read", True)
        if value["generation"] >= _MAX_GENERATION:
            raise ContractError("GENERATION_LIMIT", "Frontend generation limit reached")

    def _save(self, value: dict[str, Any]) -> dict[str, Any]:
        # A failed write is propagated; no in-memory success receipt is issued.
        if self.primary.exists():
            try:
                previous = self._validate(_read(self.primary))
            except ContractError as exc:
                if exc.code == "FUTURE_SCHEMA":
                    raise
            else:
                if all(previous["readiness"].values()) and previous["attempt"] is None:
                    _atomic(self.backup, previous)
        value = _signed(value)
        _atomic(self.primary, value)
        if all(value["readiness"].values()) and value["attempt"] is None:
            _atomic(self.backup, value)
        return copy.deepcopy(value)

    def record(self) -> dict[str, Any]:
        with self._lock():
            return copy.deepcopy(self._load())

    def _foreground_record(self) -> dict[str, Any] | None:
        if not os.path.lexists(self.foreground):
            return None
        try:
            value = _read(self.foreground)
            required = {"schema", "generation", "state", "token", "request_id", "boot_id", "checksum"}
            if set(value) != required or value["schema"] != 1 or type(value["schema"]) is not int or type(value["generation"]) is not int or not 0 <= value["generation"] <= _MAX_GENERATION or value["state"] not in {"idle", "delegating"} or any(not isinstance(value[k], str) or len(value[k]) > 192 for k in ("token", "request_id", "boot_id")) or not value["boot_id"]:
                raise ValueError("invalid foreground record")
            return value
        except (ContractError, ValueError, TypeError) as exc:
            raise ContractError("FOREGROUND_UNCERTAIN", "Foreground ownership record is damaged; automatic fallback is blocked") from exc

    def assert_no_foreground(self) -> None:
        value = self._foreground_record()
        if value and value["state"] != "idle" and value["boot_id"] == self.boot_id:
            raise ContractError("FOREGROUND_UNCERTAIN", "A same-boot game handoff may survive; no second interface may start")

    def _choose(self, value: dict[str, Any]) -> str:
        self.assert_no_foreground()
        if value["blocked"]:
            raise ContractError("NO_SAFE_FRONTEND", "The classic fallback also failed; use offline repair instead of another restart loop")
        if self.marker.exists() or value["fallback_used"]:
            return "classic"
        return value["pending"] or value["stable"]

    def choose_interface(self) -> str:
        with self._lock():
            return self._choose(self._load())

    select = choose_interface

    def request(self, interface: str, expected_generation: int) -> dict[str, Any]:
        if interface not in {"classic", "project"}:
            raise ContractError("INVALID_INTERFACE", "Unknown frontend interface")
        with self._lock():
            self.assert_no_foreground()
            value = self._load()
            self._generation(value, expected_generation)
            if interface == "project" and self.marker.exists():
                raise ContractError("FORCED_CLASSIC", "Remove force-classic before explicitly selecting the project interface")
            if value["attempt"] is not None and self._attempt_alive(value["attempt"]):
                raise ContractError("STARTUP_BUSY", "A frontend startup is still active", True)
            value.update(pending=interface, attempt=None, readiness=dict.fromkeys(_CHECKS, False),
                         failures=0, fallback_used=False, blocked=False, generation=value["generation"] + 1)
            return self._save(value)

    def _attempt_alive(self, attempt: dict[str, Any]) -> bool:
        return attempt["boot_id"] == self.boot_id and self.process_alive(attempt["pid"], attempt["start_id"])

    @staticmethod
    def _fail(value: dict[str, Any], interface: str) -> None:
        exhausted = interface == "classic"
        value.update(stable="classic", pending=None, attempt=None, readiness=dict.fromkeys(_CHECKS, False),
                     failures=min(value["failures"] + 1, 1000000), fallback_used=True, blocked=exhausted)

    def begin(self, interface: str | None = None, *, expected_generation: int | None = None) -> dict[str, Any]:
        """Start one attempt before optional imports; use the returned interface.

        An interrupted previous project attempt changes the chosen interface to
        classic even if the caller passed an earlier project selection.
        """
        if interface is not None and interface not in {"classic", "project"}:
            raise ContractError("INVALID_INTERFACE", "Unknown frontend startup interface")
        with self._lock():
            self.assert_no_foreground()
            value = self._load()
            self._generation(value, expected_generation)
            previous = value["attempt"]
            recovered = False
            if previous is not None:
                if previous["id"] == self._own_attempt:
                    return copy.deepcopy(value)
                if self._attempt_alive(previous):
                    raise ContractError("STARTUP_BUSY", "Another frontend startup is active", True)
                self._fail(value, previous["interface"])
                recovered = True
            if value["blocked"]:
                if recovered:
                    value["generation"] += 1
                    self._save(value)
                raise ContractError("NO_SAFE_FRONTEND", "The classic fallback failed; offline repair is required")
            chosen = self._choose(value)
            if interface is not None and not recovered and interface != chosen:
                raise ContractError("STALE_SELECTION", "Startup interface does not match the current selector", True)
            token = uuid.uuid4().hex
            start = _pid_start(os.getpid())
            if start is None:
                raise ContractError("PROCESS_IDENTITY", "Cannot establish frontend startup identity")
            value.update(attempt={"id": token, "boot_id": self.boot_id, "pid": os.getpid(),
                                  "start_id": start, "interface": chosen},
                         readiness=dict.fromkeys(_CHECKS, False), generation=value["generation"] + 1)
            self._own_attempt = token
            return self._save(value)

    def mark_ready(self, *, first_frame: bool, input_ready: bool, settings_ready: bool,
                   attempt_id: str | None = None, expected_generation: int | None = None) -> dict[str, Any]:
        if first_frame is not True or input_ready is not True or settings_ready is not True:
            raise ContractError("NOT_READY", "First frame, input and settings must all be ready before committing the interface")
        with self._lock():
            self.assert_no_foreground()
            value = self._load()
            self._generation(value, expected_generation)
            attempt = value["attempt"]
            if attempt is None or (attempt_id or self._own_attempt) != attempt["id"] or attempt["boot_id"] != self.boot_id:
                raise ContractError("STALE_ATTEMPT", "Readiness does not belong to this frontend startup")
            if attempt["interface"] == "project" and self.marker.exists():
                raise ContractError("FORCED_CLASSIC", "The offline marker changed during project startup")
            value.update(stable=attempt["interface"], pending=None, attempt=None,
                         readiness=dict.fromkeys(_CHECKS, True), generation=value["generation"] + 1)
            if not value["fallback_used"]:
                value["failures"] = 0
            self._own_attempt = None
            return self._save(value)

    def note_failure(self, *, attempt_id: str | None = None, expected_generation: int | None = None) -> dict[str, Any]:
        with self._lock():
            self.assert_no_foreground()
            value = self._load()
            self._generation(value, expected_generation)
            attempt = value["attempt"]
            if attempt is None or (attempt_id or self._own_attempt) != attempt["id"]:
                raise ContractError("STALE_ATTEMPT", "Failure does not belong to this frontend startup")
            self._fail(value, attempt["interface"])
            value["generation"] += 1
            self._own_attempt = None
            return self._save(value)

    def begin_foreground(self, request_id: str) -> str:
        if not isinstance(request_id, str) or not request_id or len(request_id) > 192:
            raise ContractError("INVALID_REQUEST", "Invalid foreground handoff request")
        with self._lock():
            self.assert_no_foreground()
            old = self._foreground_record()
            generation = old["generation"] + 1 if old else 1
            if generation > _MAX_GENERATION:
                raise ContractError("GENERATION_LIMIT", "Foreground generation limit reached")
            token = uuid.uuid4().hex
            _atomic(self.foreground, {"schema": 1, "generation": generation, "state": "delegating",
                                     "token": token, "request_id": request_id, "boot_id": self.boot_id})
            return token

    def note_runtime_failure(self, *, expected_generation: int | None = None) -> dict[str, Any]:
        """Record a view failure after readiness, before choosing a fallback."""
        with self._lock():
            self.assert_no_foreground()
            value = self._load()
            self._generation(value, expected_generation)
            if value["attempt"] is not None:
                raise ContractError("STARTUP_BUSY", "Use the matching startup attempt failure contract")
            self._fail(value, value["stable"])
            value["generation"] += 1
            return self._save(value)

    def delegate_classic(self, attempt_id: str) -> dict[str, Any]:
        """Cancel an unstarted classic attempt without inventing frame evidence.

        The source entry returns to the existing MainMenu implementation. Its
        hardware/readiness proof is a separate integration qualification.
        """
        with self._lock():
            self.assert_no_foreground()
            value = self._load()
            self._generation(value, None)
            attempt = value["attempt"]
            if attempt is None or attempt["id"] != attempt_id or attempt["interface"] != "classic":
                raise ContractError("STALE_ATTEMPT", "No matching unstarted classic handoff exists")
            value.update(attempt=None, stable="classic", pending=None, readiness=dict.fromkeys(_CHECKS, False),
                         generation=value["generation"] + 1)
            self._own_attempt = None
            return self._save(value)

    def clear_foreground(self, token: str, *, verified: bool = False) -> None:
        if verified is not True:
            raise ContractError("RETURN_UNVERIFIED", "A verified spruce return is required to clear foreground ownership")
        with self._lock():
            value = self._foreground_record()
            if value is None or value["token"] != token or value["state"] != "delegating" or value["boot_id"] != self.boot_id:
                raise ContractError("STALE_HANDOFF", "Foreground completion does not match its saved ownership token")
            if value["generation"] >= _MAX_GENERATION:
                raise ContractError("GENERATION_LIMIT", "Foreground generation limit reached")
            value.update(state="idle", generation=value["generation"] + 1)
            _atomic(self.foreground, value)

    def set_force_classic(self, enabled: bool = True) -> None:
        if type(enabled) is not bool:
            raise ContractError("INVALID_MARKER", "Recovery marker state must be a boolean")
        with self._lock():
            if enabled:
                descriptor = os.open(self.marker, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
                with os.fdopen(descriptor, "w", encoding="ascii") as output:
                    output.write("Use the untouched classic frontend after foreground ownership is clear.\n")
                    output.flush()
                    os.fsync(output.fileno())
            else:
                try:
                    self.marker.unlink()
                except FileNotFoundError:
                    pass
