"""Original, journaled settings helpers for the Smart Pro spruce offshoot.

These helpers do not import PyUI or run device commands.  Their callers provide
the trusted, quiescent backend boundary.  A successful host transaction does
not establish FAT32 power-loss durability on the handheld.
"""

from __future__ import annotations

import contextlib
import copy
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
from typing import Callable, Iterable
import uuid


MAX_FILE = 1_048_576
MAX_GENERATION = 9_007_199_254_740_991
DEFAULT_PREFERENCES = {
    "interface": "classic",
    "theme": "psp",
    "motion": True,
    "sound": True,
    "text_scale": 1.0,
    "high_contrast": False,
    "confirm": "south",
}


class SettingsError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable

    def as_dict(self) -> dict:
        return {"code": self.code, "message": str(self), "retryable": self.retryable}


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise SettingsError(code, message)


def _fields(value: dict, allowed: Iterable[str], required: Iterable[str]) -> None:
    _require(isinstance(value, dict), "INVALID_ARGUMENT", "Expected an object")
    unknown = set(value) - set(allowed)
    _require(not unknown, "UNKNOWN_FIELD", "Unknown request field")
    _require(set(required) <= set(value), "INVALID_ARGUMENT", "A required field is missing")


def _identifier(value, field: str) -> str:
    _require(isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value)),
             "INVALID_ARGUMENT", f"Invalid {field}")
    return value


def _generation(value) -> int:
    _require(type(value) is int and 0 <= value <= MAX_GENERATION,
             "INVALID_ARGUMENT", "Invalid settings generation")
    return value


def _schema(value: dict) -> None:
    _require(isinstance(value, dict) and type(value.get("schema")) is int,
             "INVALID_SCHEMA", "Missing configuration schema")
    _require(value["schema"] == 1, "UNSUPPORTED_SCHEMA", "Unsupported configuration schema")


def _encoded(value) -> bytes:
    try:
        result = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                             allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as error:
        raise SettingsError("INVALID_CONFIG", "Configuration cannot be encoded") from error
    _require(len(result) <= MAX_FILE, "TOO_LARGE", "Configuration exceeds its byte budget")
    return result


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _io_error(error: OSError) -> SettingsError:
    code = "STORAGE_ERROR"
    if error.errno in (errno.EROFS, errno.EACCES, errno.EPERM):
        code = "STORAGE_READ_ONLY"
    elif error.errno in (errno.ENOSPC, errno.EDQUOT):
        code = "STORAGE_FULL"
    return SettingsError(code, "The settings file could not be written", True)


def _directory(path: Path) -> Path:
    path = Path(path).absolute()
    # Existing symlink components are not accepted as writable state roots.
    for parent in (*reversed(path.parents), path):
        if parent.is_symlink():
            raise SettingsError("UNSAFE_PATH", "Settings directories cannot be symlinks")
    try:
        path.mkdir(parents=True, exist_ok=True)
        _require(path.is_dir(), "UNSAFE_PATH", "Settings state must be a directory")
        return path.resolve()
    except OSError as error:
        raise _io_error(error) from error


def _read(path: Path, optional: bool = False) -> bytes | None:
    try:
        info = path.lstat()
        _require(stat.S_ISREG(info.st_mode), "UNSAFE_PATH", "Configuration must be a regular file")
        _require(info.st_size <= MAX_FILE, "TOO_LARGE", "Configuration exceeds its byte budget")
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            _require(stat.S_ISREG(opened.st_mode), "UNSAFE_PATH", "Configuration must be a regular file")
            result = stream.read(MAX_FILE + 1)
        _require(len(result) <= MAX_FILE, "TOO_LARGE", "Configuration exceeds its byte budget")
        return result
    except FileNotFoundError:
        if optional:
            return None
        raise SettingsError("MISSING_CONFIG", "A required configuration file is missing") from None
    except OSError as error:
        raise _io_error(error) from error


def _json_bytes(data: bytes) -> dict:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise SettingsError("INVALID_CONFIG", "Configuration is not valid bounded JSON") from error
    _require(isinstance(value, dict), "INVALID_CONFIG", "Configuration must be an object")
    return value


def _json(path: Path) -> dict:
    return _json_bytes(_read(path))


def _sync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path: Path, data: bytes, mode: int | None = None) -> None:
    """Replace one regular file using a flushed temporary sibling."""
    _require(len(data) <= MAX_FILE, "TOO_LARGE", "Configuration exceeds its byte budget")
    existing = _read(path, optional=True)
    if existing is not None:
        _require(stat.S_IMODE(path.stat().st_mode) & 0o222 != 0,
                 "STORAGE_READ_ONLY", "The configuration file is read-only")
    if mode is None:
        mode = stat.S_IMODE(path.stat().st_mode) if existing is not None else 0o600
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".trimui-settings-", dir=path.parent)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode & 0o777)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # The final-path check prevents an ordinary symlink replacement. The
        # root-runtime design does not claim isolation from another root actor.
        _read(path, optional=True)
        os.replace(temporary, path)
        temporary = None
        _sync_directory(path.parent)
    except OSError as error:
        raise _io_error(error) from error
    finally:
        if temporary:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)


_thread_locks: dict[str, threading.RLock] = {}
_thread_locks_guard = threading.Lock()


@contextlib.contextmanager
def _locked(path: Path):
    key = str(path)
    with _thread_locks_guard:
        lock = _thread_locks.setdefault(key, threading.RLock())
    with lock:
        try:
            fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "rb") as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        except OSError as error:
            raise _io_error(error) from error


class _Transactions:
    """Multi-file rollback journal; target allowlisting belongs to the owner."""

    def __init__(self, directory: Path, validate: Callable, fault_hook=None,
                 before_recovery: Callable | None = None,
                 before_write: Callable | None = None):
        self.directory = _directory(directory)
        self.validate = validate
        self.fault_hook = fault_hook
        self.before_recovery = before_recovery
        self.before_write = before_write

    def _records(self) -> list[Path]:
        result = sorted(self.directory.glob("*.json"))
        _require(len(result) <= 8192, "TRANSACTION_CAPACITY", "Archive old settings journals before continuing")
        return result

    def _load(self, path: Path) -> dict:
        value = _json(path)
        _schema(value)
        _identifier(value.get("id"), "transaction ID")
        _require(value["id"] + ".json" == path.name, "INVALID_TRANSACTION", "Journal identity mismatch")
        _require(value.get("status") in {"prepared", "applying", "rolling_back", "conflict", "committed", "rolled_back"},
                 "INVALID_TRANSACTION", "Unknown journal state")
        files = value.get("files")
        _require(isinstance(files, list) and 0 < len(files) <= 16,
                 "INVALID_TRANSACTION", "Invalid transaction files")
        for item in files:
            _require(isinstance(item, dict) and isinstance(item.get("path"), str) and
                     type(item.get("before_exists")) is bool and type(item.get("mode")) is int,
                     "INVALID_TRANSACTION", "Invalid transaction file")
            for name in ("before_sha256", "after_sha256"):
                _require(isinstance(item.get(name), str) and bool(re.fullmatch("[a-f0-9]{64}", item[name])),
                         "INVALID_TRANSACTION", "Invalid snapshot digest")
        self.validate(value)
        return value

    def journal(self, transaction_id: str) -> dict:
        return self._load(self.directory / (_identifier(transaction_id, "transaction ID") + ".json"))

    def _persist(self, value: dict) -> None:
        _atomic_write(self.directory / (value["id"] + ".json"), _encoded(value))

    def hit(self, point: str, index: int = 0) -> None:
        if self.fault_hook:
            self.fault_hook(point, index)

    def replay(self, request_id: str, operation: str, resource: str) -> dict | None:
        for path in self._records():
            value = self._load(path)
            if value.get("request_id") != request_id:
                continue
            _require(value.get("operation") == operation and value.get("resource") == resource,
                     "IDEMPOTENCY_CONFLICT", "Request ID was used for a different operation")
            if value["status"] == "committed":
                result = copy.deepcopy(value["result"])
                result["idempotent"] = True
                return result
        return None

    def snapshot(self, journal: dict, index: int, after: bool = False) -> bytes:
        name = "after" if after else "before"
        data = _read(self.directory / journal["id"] / f"{index}.{name}")
        _require(_sha(data) == journal["files"][index][name + "_sha256"],
                 "CORRUPT_BACKUP", "Configuration snapshot checksum failed")
        return data

    def commit(self, transaction_id: str, request_id: str, operation: str, resource: str,
               changes: list[tuple[Path, bytes | None, bytes]], metadata: dict, result: dict,
               before_apply: Callable | None = None) -> None:
        _require(0 < len(changes) <= 16, "INVALID_TRANSACTION", "Invalid transaction size")
        snapshot_dir = _directory(self.directory / transaction_id)
        value = {"schema": 1, "id": transaction_id, "request_id": request_id,
                 "operation": operation, "resource": resource, "status": "prepared",
                 "metadata": metadata, "result": result, "files": []}
        for index, (path, before, after) in enumerate(changes):
            _require(_read(path, optional=True) == before, "STALE_SNAPSHOT", "Configuration changed since preview")
            mode = stat.S_IMODE(path.stat().st_mode) if before is not None else 0o600
            _require(mode & 0o222 != 0, "STORAGE_READ_ONLY", "A configuration target is read-only")
            _atomic_write(snapshot_dir / f"{index}.before", before or b"")
            _atomic_write(snapshot_dir / f"{index}.after", after)
            value["files"].append({"path": str(path), "before_exists": before is not None,
                                   "before_sha256": _sha(before or b""), "after_sha256": _sha(after), "mode": mode})
        self.validate(value)
        self._persist(value)
        try:
            self.hit("prepared")
            if before_apply:
                before_apply(value, self._persist)
            value["status"] = "applying"
            self._persist(value)
            for index, (path, before, after) in enumerate(changes):
                self.validate(value)
                if self.before_write:
                    self.before_write(value)
                _require(_read(path, optional=True) == before, "STALE_SNAPSHOT", "Configuration changed during commit")
                self.hit("before_replace", index)
                _atomic_write(path, after, value["files"][index]["mode"])
                self.hit("after_replace", index)
            _require(all(_read(path) == after for path, _before, after in changes),
                     "CONFIG_WRITER_CONFLICT", "Another writer changed a committed target")
            self.hit("before_commit", len(changes))
            value["status"] = "committed"
            self._persist(value)
            self.hit("after_commit", len(changes))
        except Exception as cause:
            if value["status"] != "committed":
                # Preserve the journal if rollback cannot establish ownership.
                # A process death is recovered at the next owner startup.
                try:
                    self._recover_one(value)
                except SettingsError as recovery_error:
                    raise recovery_error from cause
            raise

    def recover(self) -> None:
        for path in self._records():
            value = self._load(path)
            if value["status"] not in {"committed", "rolled_back"}:
                self._recover_one(value)

    def _recover_one(self, value: dict) -> None:
        self.validate(value)
        if value["status"] in {"committed", "rolled_back"}:
            return
        for index, item in enumerate(value["files"]):
            before = self.snapshot(value, index)
            after = self.snapshot(value, index, True)
            current = _read(Path(item["path"]), optional=True)
            original = before if item["before_exists"] else None
            if current not in (original, after):
                value["status"] = "conflict"
                self._persist(value)
                raise SettingsError("RECOVERY_CONFLICT", "An external configuration edit prevents automatic recovery")
        if self.before_recovery:
            self.before_recovery(value, self._persist)
        value["status"] = "rolling_back"
        self._persist(value)
        for index in reversed(range(len(value["files"]))):
            item = value["files"][index]
            path = Path(item["path"])
            if self.before_write:
                self.before_write(value)
            before = self.snapshot(value, index) if item["before_exists"] else None
            current = _read(path, optional=True)
            _require(current in (before, self.snapshot(value, index, True)),
                     "RECOVERY_CONFLICT", "A target changed during recovery")
            if current == before:
                continue
            if item["before_exists"]:
                _atomic_write(path, before, item["mode"])
            elif path.exists():
                path.unlink()
                _sync_directory(path.parent)
        value["status"] = "rolled_back"
        self._persist(value)


def _check_generation(params: dict, state: dict) -> int:
    current = _generation(state.get("generation"))
    _require(_generation(params.get("expected_generation")) == current,
             "STALE_GENERATION", "Configuration generation changed")
    _require(current < MAX_GENERATION, "GENERATION_EXHAUSTED", "Configuration generation is exhausted")
    return current


def _preference(key: str, value) -> None:
    if key in {"motion", "sound", "high_contrast"}:
        valid = type(value) is bool
    elif key == "text_scale":
        valid = type(value) in {int, float} and 0.75 <= value <= 1.75 and math.isfinite(value)
    elif key == "confirm":
        valid = value in ("south", "east")
    elif key == "interface":
        valid = value in ("classic", "project")
    elif key == "theme":
        valid = value in ("psp", "retropass")
    else:
        raise SettingsError("UNSUPPORTED_SETTING", "Unknown shell preference")
    _require(valid, "INVALID_SETTING", f"Invalid {key} preference")


class SettingsStore:
    """Owns only the original project's preference file, not spruce settings."""

    def __init__(self, state_dir, *, fault_hook=None, default_theme="psp"):
        _preference("theme", default_theme)
        self.state_dir = _directory(Path(state_dir))
        self.target = self.state_dir / "preferences.json"
        self.lock = self.state_dir / "preferences.lock"
        self.previews = _directory(self.state_dir / "previews")
        self.fault_hook = fault_hook
        with _locked(self.lock):
            self._transactions().recover()
            if _read(self.target, optional=True) is None:
                _atomic_write(self.target, _encoded({"schema": 1, "generation": 0,
                                                    "preferences": {**DEFAULT_PREFERENCES, "theme": default_theme}}))
            self._state()

    def _state(self) -> dict:
        state = _json(self.target)
        _schema(state)
        _generation(state.get("generation"))
        preferences = state.get("preferences")
        _require(isinstance(preferences, dict) and
                 set(preferences) in (set(DEFAULT_PREFERENCES), set(DEFAULT_PREFERENCES) - {"theme"}),
                 "INVALID_CONFIG", "Unknown or missing preference keys")
        # Older installations predate dashboard styles. Preserve their PSP
        # appearance and generation without rewriting their settings on read.
        preferences.setdefault("theme", "psp")
        for key, value in preferences.items():
            _preference(key, value)
        return state

    def _validate_journal(self, journal: dict) -> None:
        _require(len(journal["files"]) == 1 and journal["files"][0]["path"] == str(self.target),
                 "UNSAFE_PATH", "Preference journal targets an unowned file")

    def _transactions(self) -> _Transactions:
        return _Transactions(self.state_dir / "transactions", self._validate_journal, self.fault_hook)

    @staticmethod
    def _response(state: dict) -> dict:
        return {"schema": 1, "generation": state["generation"],
                "preferences": copy.deepcopy(state["preferences"])}

    def get(self) -> dict:
        with _locked(self.lock):
            self._transactions().recover()
            return self._response(self._state())

    def preview(self, params: dict) -> dict:
        _fields(params, {"changes", "expected_generation"}, {"changes", "expected_generation"})
        changes = params["changes"]
        _require(isinstance(changes, dict) and 0 < len(changes) <= len(DEFAULT_PREFERENCES),
                 "INVALID_ARGUMENT", "Expected a bounded nonempty change object")
        with _locked(self.lock):
            self._transactions().recover()
            state = self._state()
            generation = _check_generation(params, state)
            next_state = copy.deepcopy(state)
            diff = []
            for key, value in changes.items():
                _preference(key, value)
                before = state["preferences"][key]
                if before != value:
                    diff.append({"key": key, "before": before, "after": value})
                    next_state["preferences"][key] = value
            _require(bool(diff), "NO_CHANGES", "Preferences already match")
            preview_id = "preview-" + uuid.uuid4().hex
            record = {"schema": 1, "preview_id": preview_id, "generation": generation,
                      "base_sha256": _sha(_read(self.target)), "diff": diff}
            _atomic_write(self.previews / (preview_id + ".json"), _encoded(record))
            return {"preview_id": preview_id, "generation": generation, "expected_generation": generation,
                    "diff": diff, "preferences": next_state["preferences"]}

    def apply(self, params: dict) -> dict:
        _fields(params, {"preview_id", "request_id", "expected_generation"},
                {"preview_id", "request_id", "expected_generation"})
        preview_id = _identifier(params["preview_id"], "preview ID")
        request_id = _identifier(params["request_id"], "request ID")
        _generation(params["expected_generation"])
        with _locked(self.lock):
            transactions = self._transactions()
            transactions.recover()
            replay = transactions.replay(request_id, "apply", preview_id)
            if replay is not None:
                return replay
            record = _json(self.previews / (preview_id + ".json"))
            _schema(record)
            state = self._state()
            generation = _check_generation(params, state)
            before = _read(self.target)
            _require(record.get("preview_id") == preview_id and record.get("generation") == generation and
                     record.get("base_sha256") == _sha(before), "STALE_SNAPSHOT", "Preferences changed since preview")
            diff = record.get("diff")
            _require(isinstance(diff, list) and 0 < len(diff) <= len(DEFAULT_PREFERENCES),
                     "INVALID_PREVIEW", "Invalid preference preview")
            next_state = copy.deepcopy(state)
            keys = set()
            for change in diff:
                _fields(change, {"key", "before", "after"}, {"key", "before", "after"})
                key = change["key"]
                _preference(key, change["after"])
                _require(key not in keys and state["preferences"][key] == change["before"],
                         "INVALID_PREVIEW", "Invalid preference ownership diff")
                keys.add(key)
                next_state["preferences"][key] = change["after"]
            next_state["generation"] = generation + 1
            transaction_id = "tx-" + uuid.uuid4().hex
            result = {**self._response(next_state), "transaction_id": transaction_id,
                      "applied": True, "idempotent": False}
            transactions.commit(transaction_id, request_id, "apply", preview_id,
                                [(self.target, before, _encoded(next_state))], {"diff": diff}, result)
            return result

    def undo(self, params: dict) -> dict:
        _fields(params, {"transaction_id", "request_id", "expected_generation"},
                {"transaction_id", "request_id", "expected_generation"})
        original_id = _identifier(params["transaction_id"], "transaction ID")
        request_id = _identifier(params["request_id"], "request ID")
        _generation(params["expected_generation"])
        with _locked(self.lock):
            transactions = self._transactions()
            transactions.recover()
            replay = transactions.replay(request_id, "undo", original_id)
            if replay is not None:
                return replay
            original = transactions.journal(original_id)
            _require(original["status"] == "committed" and original.get("operation") == "apply",
                     "INVALID_TRANSACTION", "Only committed preference changes can be undone")
            state = self._state()
            generation = _check_generation(params, state)
            next_state = copy.deepcopy(state)
            for change in original["metadata"]["diff"]:
                key = change["key"]
                _preference(key, change["before"])
                _require(state["preferences"][key] == change["after"],
                         "UNDO_CONFLICT", "A preference was edited after this transaction")
                next_state["preferences"][key] = change["before"]
            next_state["generation"] = generation + 1
            transaction_id = "tx-" + uuid.uuid4().hex
            result = {**self._response(next_state), "transaction_id": transaction_id,
                      "undone_transaction_id": original_id, "applied": True, "idempotent": False}
            transactions.commit(transaction_id, request_id, "undo", original_id,
                                [(self.target, _read(self.target), _encoded(next_state))],
                                {"undone_transaction_id": original_id}, result)
            return result

    def recover(self) -> None:
        with _locked(self.lock):
            self._transactions().recover()


class SpruceConfigTransaction:
    """Original adapter for declared spruce menu selections.

    `backend(change)` must apply an absolute setting idempotently and return
    True (or {"ok": True}). It must also support the inverse change for failure
    compensation/recovery. It receives category/key/before/after, never a
    command from the caller. `quiescent()` is a trusted runtime guard.
    """

    def __init__(self, config_path, state_dir, *, quiescent: Callable,
                 backend: Callable, device_names=("TRIMUI_SMART_PRO", "TRIMUI_A133P"),
                 fault_hook=None):
        self.target = Path(config_path).absolute()
        _read(self.target)  # Read-only target validation; do not seed/reset it.
        _require(not any(parent.is_symlink() for parent in self.target.parents),
                 "UNSAFE_PATH", "Spruce configuration path cannot traverse symlinks")
        self.target = self.target.resolve()
        self.state_dir = _directory(Path(state_dir))
        self.meta = self.state_dir / "generation.json"
        self.lock = self.state_dir / "spruce-settings.lock"
        self.previews = _directory(self.state_dir / "previews")
        self.quiescent = quiescent
        self.backend = backend
        self.device_names = set(device_names)
        self.fault_hook = fault_hook
        with _locked(self.lock):
            self._transactions().recover()
            if _read(self.meta, optional=True) is None:
                _atomic_write(self.meta, _encoded({"schema": 1, "generation": 0}))

    def _guard(self) -> None:
        _require(self.quiescent() is True, "BUSY_WRITER", "A quiescent configuration-write window is required")

    def _validate_journal(self, journal: dict) -> None:
        _require([item["path"] for item in journal["files"]] == [str(self.target), str(self.meta)],
                 "UNSAFE_PATH", "Spruce journal targets an unowned file")

    def _transactions(self) -> _Transactions:
        return _Transactions(self.state_dir / "transactions", self._validate_journal,
                             self.fault_hook, self._compensate, lambda _: self._guard())

    def _meta(self) -> dict:
        value = _json(self.meta)
        _schema(value)
        _generation(value.get("generation"))
        return value

    def snapshot(self) -> dict:
        """Read a digest and option names without writing the authority."""
        data = _read(self.target)
        value = _json_bytes(data)
        options = value.get("menuOptions", {})
        _require(isinstance(options, dict), "INVALID_CONFIG", "Invalid spruce menu categories")
        return {"generation": self._meta()["generation"], "sha256": _sha(data),
                "categories": {category: list(entries) for category, entries in options.items()
                               if isinstance(entries, dict)}}

    def _selection(self, data: dict, change: dict) -> dict:
        _fields(change, {"category", "key", "value"}, {"category", "key", "value"})
        category, key, value = change["category"], change["key"], change["value"]
        _require(isinstance(category, str) and isinstance(key, str), "INVALID_ARGUMENT", "Invalid setting identity")
        try:
            option = data["menuOptions"][category][key]
        except (KeyError, TypeError) as error:
            raise SettingsError("UNSUPPORTED_SETTING", "Unknown spruce setting") from error
        _require(isinstance(option, dict) and "selected" in option, "INVALID_CONFIG", "Malformed spruce setting")
        devices = option.get("devices")
        _require(devices is None or isinstance(devices, list) and all(isinstance(item, str) for item in devices),
                 "INVALID_CONFIG", "Malformed setting device filter")
        _require(devices is None or bool(self.device_names.intersection(devices)),
                 "UNSUPPORTED_SETTING", "Setting is unavailable on the original Smart Pro")
        allowed = []
        options = option.get("options", [])
        _require(isinstance(options, list) and len(options) <= 256, "INVALID_CONFIG", "Malformed setting options")
        for item in options:
            if isinstance(item, str):
                allowed.append(item)
            elif isinstance(item, dict):
                item_devices = item.get("devices", [])
                _require(isinstance(item.get("label"), str) and isinstance(item_devices, list) and
                         all(isinstance(device, str) for device in item_devices),
                         "INVALID_CONFIG", "Malformed device-specific setting option")
                if not item_devices or self.device_names.intersection(item_devices):
                    allowed.append(item["label"])
            else:
                raise SettingsError("INVALID_CONFIG", "Malformed setting option")
        # Free text can contain credentials. It needs its own explicit backend,
        # validation and redaction contract; this selection adapter declines it.
        _require(isinstance(value, str) and value in allowed, "INVALID_SETTING", "Setting value is not an allowed device option")
        return {"category": category, "key": key, "before": copy.deepcopy(option["selected"]), "after": value}

    def preview(self, params: dict) -> dict:
        _fields(params, {"changes", "expected_generation"}, {"changes", "expected_generation"})
        changes = params["changes"]
        _require(isinstance(changes, list) and 0 < len(changes) <= 16, "INVALID_ARGUMENT", "Expected a bounded selection list")
        with _locked(self.lock):
            self._transactions().recover()
            meta = self._meta()
            generation = _check_generation(params, meta)
            before = _read(self.target)
            data = _json_bytes(before)
            diff = [self._selection(data, item) for item in changes]
            identities = [(item["category"], item["key"]) for item in diff]
            _require(len(set(identities)) == len(identities), "INVALID_ARGUMENT", "Duplicate selection")
            diff = [item for item in diff if item["before"] != item["after"]]
            _require(bool(diff), "NO_CHANGES", "Selections already match")
            preview_id = "preview-" + uuid.uuid4().hex
            _atomic_write(self.previews / (preview_id + ".json"), _encoded(
                {"schema": 1, "preview_id": preview_id, "generation": generation,
                 "base_sha256": _sha(before), "meta_sha256": _sha(_read(self.meta)), "diff": diff}))
            return {"preview_id": preview_id, "generation": generation, "diff": diff}

    def _call_backend(self, change: dict) -> None:
        self._guard()
        try:
            outcome = self.backend(copy.deepcopy(change))
        except Exception as error:
            raise SettingsError("BACKEND_FAILED", "The settings backend failed; the selected value was not committed") from error
        _require(outcome is True or isinstance(outcome, dict) and outcome.get("ok") is True,
                 "BACKEND_FAILED", "The settings backend rejected the change")

    def _compensate(self, journal: dict, persist: Callable) -> None:
        self._guard()
        steps = journal["metadata"].get("backend_steps", [])
        for index in reversed(range(len(steps))):
            if steps[index] == "reverted":
                continue
            change = journal["metadata"]["diff"][index]
            inverse = {**change, "before": change["after"], "after": change["before"]}
            try:
                self._call_backend(inverse)
            except SettingsError as error:
                raise SettingsError("BACKEND_RECONCILE_REQUIRED", "Backend recovery could not be proved; keep the journal for review") from error
            steps[index] = "reverted"
            persist(journal)

    def _commit(self, params: dict, operation: str) -> dict:
        resource_key = "preview_id" if operation == "apply" else "transaction_id"
        _fields(params, {resource_key, "request_id", "expected_generation"},
                {resource_key, "request_id", "expected_generation"})
        resource = _identifier(params[resource_key], resource_key)
        request_id = _identifier(params["request_id"], "request ID")
        _generation(params["expected_generation"])
        with _locked(self.lock):
            self._guard()
            transactions = self._transactions()
            transactions.recover()
            replay = transactions.replay(request_id, operation, resource)
            if replay is not None:
                return replay
            meta = self._meta()
            generation = _check_generation(params, meta)
            before = _read(self.target)
            data = _json_bytes(before)
            if operation == "apply":
                record = _json(self.previews / (resource + ".json"))
                _schema(record)
                _require(record.get("preview_id") == resource and record.get("generation") == generation and
                         record.get("base_sha256") == _sha(before) and record.get("meta_sha256") == _sha(_read(self.meta)),
                         "STALE_SNAPSHOT", "Spruce configuration changed since preview")
                diff = record.get("diff", [])
            else:
                record = transactions.journal(resource)
                _require(record["status"] == "committed" and record.get("operation") == "apply",
                         "INVALID_TRANSACTION", "Only committed selections can be undone")
                diff = [{**item, "before": item["after"], "after": item["before"]}
                        for item in record["metadata"]["diff"]]
            _require(isinstance(diff, list) and 0 < len(diff) <= 16, "INVALID_PREVIEW", "Invalid selection diff")
            for item in diff:
                selected = self._selection(data, {"category": item["category"], "key": item["key"], "value": item["after"]})
                _require(selected["before"] == item["before"], "UNDO_CONFLICT" if operation == "undo" else "STALE_SNAPSHOT",
                         "A selected option was edited externally")
                data["menuOptions"][item["category"]][item["key"]]["selected"] = item["after"]
            next_meta = {**meta, "generation": generation + 1}
            transaction_id = "tx-" + uuid.uuid4().hex
            result = {"transaction_id": transaction_id, "generation": generation + 1,
                      "applied": True, "idempotent": False}
            if operation == "undo":
                result["undone_transaction_id"] = resource
            metadata = {"diff": diff, "backend_steps": []}

            def run_backend(journal: dict, persist: Callable):
                for index, change in enumerate(diff):
                    journal["metadata"]["backend_steps"].append("started")
                    persist(journal)  # A crash makes the absolute inverse replayable.
                    self._call_backend(change)
                    journal["metadata"]["backend_steps"][index] = "succeeded"
                    persist(journal)
                    transactions.hit("after_backend", index)

            transactions.commit(transaction_id, request_id, operation, resource,
                                [(self.target, before, _encoded(data)),
                                 (self.meta, _read(self.meta), _encoded(next_meta))],
                                metadata, result, run_backend)
            return result

    def apply(self, params: dict) -> dict:
        return self._commit(params, "apply")

    def undo(self, params: dict) -> dict:
        return self._commit(params, "undo")

    def recover(self) -> None:
        with _locked(self.lock):
            self._transactions().recover()
