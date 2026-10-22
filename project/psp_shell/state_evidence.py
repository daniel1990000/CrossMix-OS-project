# SPDX-License-Identifier: MIT
"""Private opt-in PPSSPP evidence sessions and trusted Resume capabilities.

The new TPSE1 protocol is data, never authority. A retained session, independent
qualified profile, typed foreground completion and current stopped-writer
authority are all required. No process, shell or emulator is started here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import time
from typing import Callable, Mapping

from bridge.bootstrap import ForegroundIdentity, SpruceReturnEvidence
from .runtime import SPRUCE_COMMIT

UPSTREAM = "d357e6a32934800d3d80b49f910a603e1b069751"
FORMAT = "ppsspp:" + UPSTREAM + ":chunk5-savestart3"
MAX_PACKET = 32768
_SEAL = object()


class StateEvidenceError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _error(code, message):
    raise StateEvidenceError(code, message)


def _text(value, maximum=4096):
    if not isinstance(value, str) or "\0" in value:
        _error("INVALID_STATE_EVIDENCE", "Expected bounded UTF-8 text")
    try:
        if len(value.encode("utf-8")) > maximum:
            _error("INVALID_STATE_EVIDENCE", "State text exceeded its budget")
    except UnicodeError:
        _error("INVALID_STATE_EVIDENCE", "State text is not UTF-8")
    return value


def _hex(value, count=64):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{" + str(count) + "}", value) is not None


def _absolute(value):
    raw = _text(str(value))
    if not raw.startswith("/") or raw.endswith("/") or any(part in {"", ".", ".."} for part in raw[1:].split("/")):
        _error("INVALID_STATE_PATH", "State paths must be absolute without traversal")
    return Path(raw)


def _open_directory(path):
    absolute = _absolute(path)
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _file_hash(path, maximum):
    path = _absolute(path)
    parent = _open_directory(path.parent)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
                _error("INVALID_STATE_FILE", "State inputs must be bounded nonempty regular files")
            digest = hashlib.sha256()
            total = 0
            for chunk in iter(lambda: stream.read(65536), b""):
                total += len(chunk)
                if total > maximum:
                    _error("INVALID_STATE_FILE", "State input grew beyond its budget")
                digest.update(chunk)
            after = os.fstat(stream.fileno())
            named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            def identity(info):
                return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
            if total != before.st_size or identity(before) != identity(after) or identity(after) != identity(named):
                _error("STATE_INPUT_CHANGED", "A state input changed while fingerprinting")
            return digest.hexdigest(), total
    finally:
        os.close(parent)


def encode_packet(magic: bytes, fields: tuple[str, ...] | list[str]) -> bytes:
    result = bytearray(magic)
    for value in fields:
        encoded = _text(value, 8192).encode("utf-8")
        result += str(len(encoded)).encode("ascii") + b":" + encoded + b","
    if len(result) > MAX_PACKET:
        _error("INVALID_STATE_EVIDENCE", "State packet exceeded its budget")
    return bytes(result)


def _decode_packet(data, magic, count):
    if not isinstance(data, bytes) or len(data) > MAX_PACKET or not data.startswith(magic):
        _error("INVALID_STATE_EVIDENCE", "State packet header or budget is invalid")
    offset, fields = len(magic), []
    for _ in range(count):
        end = data.find(b":", offset)
        digits = data[offset:end] if end >= offset else b""
        if not re.fullmatch(rb"0|[1-9][0-9]{0,4}", digits):
            _error("INVALID_STATE_EVIDENCE", "State packet length is not canonical")
        length = int(digits)
        offset = end + 1
        if length > 8192 or data[offset + length:offset + length + 1] != b",":
            _error("INVALID_STATE_EVIDENCE", "State packet field is truncated")
        try:
            fields.append(_text(data[offset:offset + length].decode("utf-8"), 8192))
        except UnicodeError:
            _error("INVALID_STATE_EVIDENCE", "State packet text is not UTF-8")
        offset += length + 1
    if offset != len(data):
        _error("INVALID_STATE_EVIDENCE", "State packet has trailing data")
    return tuple(fields)


@dataclass(frozen=True)
class QualifiedStateProfile:
    profile_id: str
    preset_id: str
    engine_id: str
    executable: Path
    engine_sha256: str
    sd_root: Path
    state_roots: tuple[Path, ...]
    writer_ids: tuple[str, ...]
    principal_sha256: str
    architecture: str = "aarch64"
    state_format_id: str = FORMAT
    hardware_qualified: bool = False
    writer_inventory_qualified: bool = False
    state_save_load_qualified: bool = False
    native_state_launch_qualified: bool = False
    config_hashes: tuple[tuple[str, str], ...] = ()

    def assert_qualified(self):
        if not all(value is True for value in (self.hardware_qualified, self.writer_inventory_qualified,
                                               self.state_save_load_qualified, self.native_state_launch_qualified)):
            _error("STATE_PROFILE_UNQUALIFIED", "Installed state, writer, launch and hardware qualification is required")
        if (not _hex(self.engine_sha256) or not _hex(self.principal_sha256) or self.state_format_id != FORMAT or
                self.architecture not in {"aarch64", "x86_64"} or not self.writer_ids or len(set(self.writer_ids)) != len(self.writer_ids)):
            _error("STATE_PROFILE_UNQUALIFIED", "State profile identities or writer inventory are incomplete")
        for value in (self.profile_id, self.preset_id, self.engine_id, *self.writer_ids):
            if not _text(value, 256):
                _error("STATE_PROFILE_UNQUALIFIED", "A state profile identity is empty")
        root = _absolute(self.sd_root)
        if not _absolute(self.executable).is_relative_to(root) or not self.state_roots:
            _error("STATE_PROFILE_UNQUALIFIED", "Engine or state roots are outside the approved card")
        if any(not _absolute(path).is_relative_to(root) for path in self.state_roots):
            _error("STATE_PROFILE_UNQUALIFIED", "State root is outside the approved card")
        if not self.config_hashes:
            _error("STATE_PROFILE_UNQUALIFIED", "Independent native configuration fingerprints are required")
        for path, expected in self.config_hashes:
            if not _absolute(path).is_relative_to(root) or not _hex(expected) or _file_hash(path, 1024**2)[0] != expected:
                _error("STATE_PROFILE_CHANGED", "Native state configuration differs from its qualified profile")

    @property
    def fingerprint(self):
        values = (self.profile_id, self.preset_id, self.engine_id, str(self.executable), self.engine_sha256,
                  str(self.sd_root), tuple(str(path) for path in self.state_roots), self.writer_ids, self.principal_sha256,
                  self.architecture, self.state_format_id, self.config_hashes)
        return hashlib.sha256(json.dumps(values, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class LaunchIdentity:
    foreground: ForegroundIdentity
    game_id: str
    rom_path: Path
    rom_sha256: str

    def validate(self, profile):
        if type(self.foreground) is not ForegroundIdentity or not all(_hex(value, 32) for value in
                (self.foreground.token, self.foreground.request_id)):
            _error("INVALID_STATE_SESSION", "Exact typed foreground token and request are required")
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.foreground.boot_id) or
                type(self.foreground.generation) is not int or not 0 <= self.foreground.generation <= 10**15 or
                not _text(self.game_id, 192) or not _hex(self.rom_sha256)):
            _error("INVALID_STATE_SESSION", "Launch identity is incomplete")
        if not _absolute(self.rom_path).is_relative_to(_absolute(profile.sd_root)):
            _error("INVALID_STATE_SESSION", "Game is outside the approved card")


@dataclass(frozen=True)
class WriterStoppedEvidence:
    """Trusted in-process write-window observation; never deserialize from card."""
    foreground: ForegroundIdentity
    writer_ids: tuple[str, ...]
    verification_id: str
    assert_current: Callable[[], bool]

    def validate(self, expected, profile):
        if (type(self) is not WriterStoppedEvidence or self.foreground != expected or
                tuple(sorted(self.writer_ids)) != tuple(sorted(profile.writer_ids)) or
                not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,192}", self.verification_id) or not callable(self.assert_current)):
            _error("STATE_WRITERS_UNVERIFIED", "Complete typed writer authority does not match the launch")
        try:
            current = self.assert_current()
        except Exception as error:
            raise StateEvidenceError("STATE_WRITERS_UNVERIFIED", "Writer authority failed") from error
        if current is not True:
            _error("STATE_WRITERS_UNVERIFIED", "The qualified state write window is not current")


class PrivateStateSession:
    """A capability created by the trusted principal; no from-file constructor."""
    def __init__(self, seal, path, descriptor, identity, profile, fields):
        if seal is not _SEAL:
            _error("INVALID_STATE_SESSION", "State sessions must be created by the trusted launch authority")
        self.path, self._directory = path, descriptor
        self.identity, self.profile, self._fields = identity, profile, fields

    @classmethod
    def create(cls, private_root, identity: LaunchIdentity, profile: QualifiedStateProfile, *,
               mode="save", resume: "VerifiedState | None" = None):
        if type(identity) is not LaunchIdentity or type(profile) is not QualifiedStateProfile:
            _error("INVALID_STATE_SESSION", "Typed independent profile and launch identity are required")
        identity.validate(profile)
        private_root = _absolute(private_root)
        if private_root.is_relative_to(_absolute(profile.sd_root)):
            _error("INVALID_STATE_SESSION", "Private state transport must be outside the card")
        parent = _open_directory(private_root)
        os.close(parent)
        if mode not in {"save", "resume"} or (mode == "resume") != (type(resume) is VerifiedState):
            _error("INVALID_STATE_SESSION", "Resume requires a previously verified state capability")
        if resume is not None:
            resume.validate_game(identity.game_id, profile.preset_id, identity.rom_path)
            if resume.identity.rom_sha256 != identity.rom_sha256 or resume.profile != profile:
                _error("INVALID_STATE_SESSION", "Resume state belongs to another qualified game or profile")
        path = Path(tempfile.mkdtemp(prefix="trimui-state-", dir=private_root))
        descriptor = _open_directory(path)
        foreground = identity.foreground
        fields = (secrets.token_hex(16), foreground.request_id, foreground.token, foreground.boot_id,
                  str(foreground.generation), identity.game_id, str(identity.rom_path), identity.rom_sha256,
                  profile.engine_sha256, str(resume.state_path.parent if resume else profile.state_roots[0]), mode,
                  str(resume.state_path) if resume else "", resume.state_sha256 if resume else "", profile.state_format_id,
                  str(resume.slot) if resume else "0")
        try:
            output = os.open("request", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=descriptor)
            with os.fdopen(output, "wb") as stream:
                stream.write(encode_packet(b"TPSE1Q\n", fields))
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(descriptor)
            return cls(_SEAL, path, descriptor, identity, profile, fields)
        except BaseException:
            os.close(descriptor)
            raise

    @property
    def command_environment(self):
        return {"TRIMUI_PROJECT_STATE_REQUEST": str(self.path / "request"),
                "TRIMUI_PROJECT_RESUME_STATE": self._fields[11]}

    @property
    def native_arguments(self):
        values = ["--project-state-session=" + str(self.path / "request")]
        if self._fields[10] == "resume":
            values.append("--state=" + self._fields[11])
        return tuple(values)

    def close(self):
        if self._directory >= 0:
            os.close(self._directory)
            self._directory = -1

    def _read_result(self, name="result"):
        if name not in {"result", "save-completed", "load-completed"}:
            _error("INVALID_STATE_EVIDENCE", "Unknown private state result purpose")
        if self._directory < 0:
            _error("INVALID_STATE_SESSION", "State session was closed")
        owner = os.fstat(self._directory)
        if owner.st_uid != os.getuid() or stat.S_IMODE(owner.st_mode) != 0o700:
            _error("INVALID_STATE_SESSION", "State transport directory lost its private ownership")
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=self._directory)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1 or
                    stat.S_IMODE(before.st_mode) != 0o600 or not 0 < before.st_size <= MAX_PACKET):
                _error("INVALID_STATE_EVIDENCE", "State result must be a private bounded regular file")
            data = stream.read(MAX_PACKET + 1)
            after = os.fstat(stream.fileno())
            named = os.stat(name, dir_fd=self._directory, follow_symlinks=False)
            key = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if key(before) != key(after) or key(after) != key(named) or len(data) != before.st_size:
                _error("STATE_INPUT_CHANGED", "State result changed while being read")
        return _decode_packet(data, b"TPSE1R\n", 27)

    def consume(self, foreground: SpruceReturnEvidence, writers: WriterStoppedEvidence, *, minimum_sequence=1):
        return self._consume_result(foreground, writers, self._read_result(), minimum_sequence)

    def _validate_result_envelope(self, result, minimum_sequence=1):
        if (result[:6] != self._fields[:6] or result[6] not in {"save", "load"} or
                (result[6] == "load" and self._fields[10] != "resume")):
            _error("STATE_SESSION_MISMATCH", "State result does not match the retained foreground session")
        if (not re.fullmatch(r"[1-9][0-9]{0,15}", result[7]) or type(minimum_sequence) is not int or
                not 1 <= minimum_sequence <= int(result[7]) or result[8] not in {"success", "failure"} or
                (result[8] == "failure" and any(result[10:]))):
            _error("STATE_OPERATION_FAILED", "No valid current engine state operation was reported")

    def consume_completed(self, foreground: SpruceReturnEvidence, writers: WriterStoppedEvidence):
        """Check independent native completions, bounded by the final result.

        Later failure retains an earlier genuine save. A load whose old state
        bytes were overwritten can refuse independently of a newer valid save.
        No pathname is inferred and no result is manufactured from state files.
        """
        latest = self._read_result()
        self._validate_result_envelope(latest)
        values, errors = [], (["STATE_OPERATION_FAILED"] if latest[8] == "failure" else [])
        for operation in ("save", "load"):
            if operation == "load" and self._fields[10] != "resume":
                continue
            try:
                result = self._read_result(operation + "-completed")
                self._validate_result_envelope(result)
                if (result[6] != operation or int(result[7]) > int(latest[7]) or
                        (result[7] == latest[7] and result != latest)):
                    _error("STATE_SESSION_MISMATCH", "Completion purpose or sequence differs from final engine report")
                values.append(self._consume_result(foreground, writers, result))
            except FileNotFoundError:
                continue
            except (OSError, StateEvidenceError) as error:
                errors.append(getattr(error, "code", "INVALID_STATE_EVIDENCE"))
        if not values and not errors:
            errors.append("NO_COMPLETED_STATE")
        return tuple(values), (errors[0] if errors else None)

    def _consume_result(self, foreground, writers, result, minimum_sequence=1):
        profile, identity = self.profile, self.identity
        profile.assert_qualified()
        if (type(foreground) is not SpruceReturnEvidence or foreground.foreground != identity.foreground or
                foreground.source_commit != SPRUCE_COMMIT or foreground.principal_sha256 != profile.principal_sha256 or
                foreground.staged_command_absent is not True or foreground.foreground_ended is not True or
                not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,192}", foreground.verification_id)):
            _error("STATE_FOREGROUND_UNVERIFIED", "Exact qualified foreground completion is required")
        if type(writers) is not WriterStoppedEvidence:
            _error("STATE_WRITERS_UNVERIFIED", "A trusted typed writer observation is required")
        writers.validate(identity.foreground, profile)
        self._validate_result_envelope(result, minimum_sequence)
        if result[8] != "success":
            _error("STATE_OPERATION_FAILED", "No current successful engine state operation was reported")
        if (result[13] != str(identity.rom_path) or result[14] != profile.engine_sha256 or result[15] != identity.rom_sha256 or
                result[22] != UPSTREAM or result[23] != "trimui-slot-evidence-v1" or result[25] != profile.architecture or
                result[26] != profile.state_format_id or not result[24] or not all(_hex(result[i]) for i in (14, 15, 16))):
            _error("STATE_IDENTITY_MISMATCH", "State game, engine, source or format identity differs")
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", result[10]) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", result[11]) or
                result[12] != result[10] + "_" + result[11] or not re.fullmatch(r"0|[1-9][0-9]?", result[21])):
            _error("STATE_IDENTITY_MISMATCH", "Native game prefix or slot identity is invalid")
        path = _absolute(result[20])
        if not any(path.is_relative_to(_absolute(root)) and path != _absolute(root) for root in profile.state_roots):
            _error("STATE_PATH_REJECTED", "Engine state path is outside qualified roots")
        if result[6] == "load" and (result[20], result[16], result[21]) != (self._fields[11], self._fields[12], self._fields[14]):
            _error("STATE_IDENTITY_MISMATCH", "Load acknowledgement belongs to another state")
        for field, limit, source in ((17, 512 * 1024**2, profile.executable), (18, 8 * 1024**3, identity.rom_path), (19, 512 * 1024**2, path)):
            if not re.fullmatch(r"[1-9][0-9]{0,12}", result[field]):
                _error("STATE_IDENTITY_MISMATCH", "State size is invalid")
            observed = _file_hash(source, limit)
            if observed != (result[field - 3], int(result[field])):
                _error("STATE_INPUT_CHANGED", "Engine, game or state file no longer matches completion")
        writers.validate(identity.foreground, profile)
        record = VerifiedState(_SEAL, identity, profile, foreground, writers, result)
        return VerifiedLoadCompletion(record) if result[6] == "load" else record


@dataclass(frozen=True, init=False, eq=False)
class VerifiedState:
    """Retained typed capability; never create it from card JSON or a recent row.

    recorded_at_utc and recorded_monotonic_ns observe principal verification
    after foreground completion. The native protocol does not report save time;
    these fields must never be presented as when the checkpoint was saved.
    """
    def __init__(self, seal, identity, profile, foreground, writers, result, *, recorded_at=None, monotonic_ns=None):
        if seal is not _SEAL:
            _error("INVALID_STATE_EVIDENCE", "State records require verified engine and foreground completion")
        for name, value in (("identity", identity), ("profile", profile), ("_foreground", foreground),
                            ("_writers", writers), ("_result", tuple(result)), ("state_path", Path(result[20])),
                            ("state_sha256", result[16]), ("slot", int(result[21])),
                            ("recorded_at_utc", recorded_at or datetime.now(timezone.utc).isoformat()),
                            ("recorded_monotonic_ns", time.monotonic_ns() if monotonic_ns is None else monotonic_ns)):
            object.__setattr__(self, name, value)

    def validate_game(self, game_id, preset_id, rom_path):
        self.profile.assert_qualified()
        if (game_id != self.identity.game_id or preset_id != self.profile.preset_id or
                _absolute(rom_path) != self.identity.rom_path):
            _error("STATE_IDENTITY_MISMATCH", "Resume capability belongs to another game or engine preset")
        self._writers.validate(self.identity.foreground, self.profile)
        for path, digest, limit in ((self.profile.executable, self.profile.engine_sha256, 512 * 1024**2),
                                    (self.identity.rom_path, self.identity.rom_sha256, 8 * 1024**3),
                                    (self.state_path, self.state_sha256, 512 * 1024**2)):
            if _file_hash(path, limit)[0] != digest:
                _error("STATE_INPUT_CHANGED", "A Resume input changed after completion")
        self._writers.validate(self.identity.foreground, self.profile)
        return True


@dataclass(frozen=True)
class VerifiedLoadCompletion:
    state: VerifiedState


@dataclass(frozen=True)
class ResumeInvocation:
    """Scoped data for the existing qualified spruce launcher/principal."""
    session: PrivateStateSession
    rom_path: Path
    state_path: Path

    @property
    def command_environment(self):
        return self.session.command_environment


class PPSSPPResumeAdapter:
    def __init__(self, profile: QualifiedStateProfile, private_root, *,
                 current_foreground: Callable[[object, VerifiedState], LaunchIdentity],
                 stage_existing_launch: Callable[[object, ResumeInvocation], object]):
        if type(profile) is not QualifiedStateProfile or not callable(current_foreground) or not callable(stage_existing_launch):
            _error("INVALID_STATE_ADAPTER", "Resume requires trusted existing foreground and launcher callbacks")
        self.profile, self.private_root = profile, private_root
        self.current_foreground, self.stage_existing_launch = current_foreground, stage_existing_launch

    def __call__(self, model, evidence):
        self.profile.assert_qualified()
        if type(evidence) is not VerifiedState or evidence.profile != self.profile:
            _error("INVALID_STATE_EVIDENCE", "PPSSPP Resume requires a typed completed-state capability")
        evidence.validate_game(evidence.identity.game_id, self.profile.preset_id, getattr(model, "rom_file_path", ""))
        identity = self.current_foreground(model, evidence)
        if type(identity) is not LaunchIdentity:
            _error("INVALID_STATE_SESSION", "Existing foreground owner did not provide an exact new launch identity")
        session = PrivateStateSession.create(self.private_root, identity, self.profile, mode="resume", resume=evidence)
        try:
            return self.stage_existing_launch(model, ResumeInvocation(session, identity.rom_path, evidence.state_path))
        except BaseException:
            session.close()
            raise


def _private_read(directory, name, maximum):
    descriptor = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or
                stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= maximum):
            _error("INVALID_STATE_STORE", "Capability storage must remain private and bounded")
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        key = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if len(raw) != info.st_size or key(info) != key(after) or key(after) != key(named):
            _error("INVALID_STATE_STORE", "Capability storage changed while reading")
        return raw


class StateCapabilityStore:
    """Authenticated, boot-bound capability transfer between fresh helpers.

    The key and records belong in volatile private storage outside the card.
    Only verified completions can be signed. Loading never qualifies a profile
    or a writer; both are independently supplied by reviewed in-process code.
    """
    def __init__(self, path, *, boot_id=None):
        self.path = _absolute(path)
        if boot_id is None:
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", boot_id):
            _error("INVALID_STATE_STORE", "A positive current boot identity is required")
        self.boot_id = boot_id
        parent = _open_directory(self.path.parent)
        try:
            try:
                os.mkdir(self.path.name, 0o700, dir_fd=parent)
            except FileExistsError:
                pass
        finally:
            os.close(parent)
        self._directory = _open_directory(self.path)
        owner = os.fstat(self._directory)
        if owner.st_uid != os.getuid() or stat.S_IMODE(owner.st_mode) != 0o700:
            self.close()
            _error("INVALID_STATE_STORE", "Capability directory must be private to the launch authority")
        try:
            self._key = self._provision_key()
            if len(self._key) != 32:
                _error("INVALID_STATE_STORE", "Capability signing key is invalid")
        except BaseException:
            self.close()
            raise

    def _provision_key(self):
        # Concurrent fresh source/principal helpers must see either no key or
        # one complete key. The lock is private, never card-provided authority.
        lock = os.open(".key-lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                       0o600, dir_fd=self._directory)
        try:
            owner = os.fstat(lock)
            if (not stat.S_ISREG(owner.st_mode) or owner.st_uid != os.getuid() or owner.st_nlink != 1 or
                    stat.S_IMODE(owner.st_mode) != 0o600):
                _error("INVALID_STATE_STORE", "Capability key lock must remain private and regular")
            fcntl.flock(lock, fcntl.LOCK_EX)
            named = os.stat(".key-lock", dir_fd=self._directory, follow_symlinks=False)
            if (owner.st_dev, owner.st_ino) != (named.st_dev, named.st_ino):
                _error("INVALID_STATE_STORE", "Capability key lock changed during provisioning")
            try:
                return _private_read(self._directory, "key", 32)
            except FileNotFoundError:
                pass
            temporary = ".key-new-" + secrets.token_hex(16)
            output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=self._directory)
            try:
                with os.fdopen(output, "wb") as stream:
                    stream.write(secrets.token_bytes(32))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, "key", src_dir_fd=self._directory, dst_dir_fd=self._directory)
                os.fsync(self._directory)
            finally:
                try:
                    os.unlink(temporary, dir_fd=self._directory)
                except FileNotFoundError:
                    pass
            return _private_read(self._directory, "key", 32)
        finally:
            os.close(lock)

    def close(self):
        if getattr(self, "_directory", -1) >= 0:
            os.close(self._directory)
            self._directory = -1

    def _assert_private(self, profile):
        if self._directory < 0 or self.path.is_relative_to(_absolute(profile.sd_root)):
            _error("INVALID_STATE_STORE", "Capability storage must be retained outside the card")
        owner = os.fstat(self._directory)
        if owner.st_uid != os.getuid() or stat.S_IMODE(owner.st_mode) != 0o700:
            _error("INVALID_STATE_STORE", "Capability directory ownership changed")

    @staticmethod
    def _name(game_id, acknowledgement=False):
        return hashlib.sha256(_text(game_id, 192).encode()).hexdigest() + (".load" if acknowledgement else ".state")

    def save(self, session: PrivateStateSession, value):
        acknowledgement = type(value) is VerifiedLoadCompletion
        record = value.state if acknowledgement else value
        if type(session) is not PrivateStateSession or type(record) is not VerifiedState or record.identity != session.identity:
            _error("INVALID_STATE_EVIDENCE", "Only a retained verified session can transfer capabilities")
        if (record._result[6] == "load") != acknowledgement:
            _error("INVALID_STATE_EVIDENCE", "Load acknowledgement and saved-state capabilities are distinct")
        record.validate_game(record.identity.game_id, record.profile.preset_id, record.identity.rom_path)
        self._assert_private(record.profile)
        if record.identity.foreground.boot_id != self.boot_id:
            _error("STATE_SESSION_MISMATCH", "Capability belongs to another boot")
        returned = record._foreground
        foreground = record.identity.foreground
        body = {"schema": 1, "boot_id": self.boot_id, "profile_id": record.profile.profile_id,
                "profile_sha256": record.profile.fingerprint, "recorded_at_utc": record.recorded_at_utc,
                "recorded_monotonic_ns": record.recorded_monotonic_ns,
                "foreground": {"token": foreground.token, "request_id": foreground.request_id,
                    "boot_id": foreground.boot_id, "generation": foreground.generation},
                "principal_sha256": returned.principal_sha256, "verification_id": returned.verification_id,
                "request": session._fields, "result": record._result}
        raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        if len(raw) > MAX_PACKET * 2:
            _error("INVALID_STATE_STORE", "Capability exceeded its storage budget")
        packet = hmac.digest(self._key, b"trimui-state-capability-v1\0" + raw, "sha256").hex().encode() + b"\n" + raw
        temporary = ".new-" + secrets.token_hex(16)
        output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self._directory)
        try:
            with os.fdopen(output, "wb") as stream:
                stream.write(packet)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._name(record.identity.game_id, acknowledgement), src_dir_fd=self._directory, dst_dir_fd=self._directory)
            os.fsync(self._directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=self._directory)
            except FileNotFoundError:
                pass

    def load(self, game_id, profile: QualifiedStateProfile, observe_writers: Callable, *, acknowledgement=False):
        profile.assert_qualified()
        self._assert_private(profile)
        packet = _private_read(self._directory, self._name(game_id, acknowledgement), MAX_PACKET * 2 + 65)
        mac, separator, raw = packet.partition(b"\n")
        expected = hmac.digest(self._key, b"trimui-state-capability-v1\0" + raw, "sha256").hex().encode()
        if not separator or not hmac.compare_digest(mac, expected):
            _error("STATE_CAPABILITY_AUTHENTICATION", "State capability authentication failed")
        try:
            body = json.loads(raw)
            if (set(body) != {"schema", "boot_id", "profile_id", "profile_sha256", "recorded_at_utc", "recorded_monotonic_ns", "foreground", "principal_sha256", "verification_id", "request", "result"} or
                    body["schema"] != 1 or body["boot_id"] != self.boot_id or body["profile_id"] != profile.profile_id or
                    body["profile_sha256"] != profile.fingerprint or type(body["recorded_monotonic_ns"]) is not int or
                    not 0 < body["recorded_monotonic_ns"] <= time.monotonic_ns() or
                    not isinstance(body["recorded_at_utc"], str) or len(body["recorded_at_utc"]) > 64 or
                    len(body["request"]) != 15 or len(body["result"]) != 27 or
                    any(not isinstance(value, str) for value in body["request"] + body["result"])):
                _error("INVALID_STATE_STORE", "Capability structure or profile changed")
            foreground = ForegroundIdentity(**body["foreground"])
            result = tuple(body["result"])
            if result[5] != game_id or foreground.boot_id != self.boot_id:
                _error("STATE_SESSION_MISMATCH", "Stored capability belongs to another game or boot")
            identity = LaunchIdentity(foreground, game_id, Path(result[13]), result[15])
            identity.validate(profile)
            returned = SpruceReturnEvidence(foreground, SPRUCE_COMMIT, body["principal_sha256"], True, True, body["verification_id"])
            writers = observe_writers(foreground, profile)
            # Authentication proves the prior principal-issued completion. The
            # existing profile, writers and every current byte are rechecked.
            session = PrivateStateSession(_SEAL, self.path, self._directory, identity, profile, tuple(body["request"]))
            value = session._consume_result(returned, writers, result)
            if (type(value) is VerifiedLoadCompletion) != bool(acknowledgement):
                _error("INVALID_STATE_STORE", "Stored operation type does not match its capability purpose")
            original = value.state if acknowledgement else value
            restored = VerifiedState(_SEAL, original.identity, original.profile, original._foreground, original._writers,
                                     original._result, recorded_at=body["recorded_at_utc"], monotonic_ns=body["recorded_monotonic_ns"])
            return VerifiedLoadCompletion(restored) if acknowledgement else restored
        except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
            raise StateEvidenceError("INVALID_STATE_STORE", "Cannot parse authenticated state capability") from error

    def game_ids(self):
        """List authenticated record IDs without scanning or hashing the ROM card."""
        names = os.listdir(self._directory)
        if len(names) > 20002:
            _error("INVALID_STATE_STORE", "Capability store exceeded its record budget")
        result = []
        for name in names:
            if re.fullmatch(r"[0-9a-f]{64}\.state", name) is None:
                continue
            try:
                packet = _private_read(self._directory, name, MAX_PACKET * 2 + 65)
            except (OSError, StateEvidenceError):
                continue
            mac, separator, raw = packet.partition(b"\n")
            expected = hmac.digest(self._key, b"trimui-state-capability-v1\0" + raw, "sha256").hex().encode()
            if not separator or not hmac.compare_digest(mac, expected):
                continue
            try:
                body = json.loads(raw)
                game_id = _text(body["result"][5], 192)
                if body["boot_id"] == self.boot_id and self._name(game_id) == name:
                    result.append(game_id)
            except (KeyError, TypeError, ValueError, IndexError):
                continue
        return tuple(result)


class PrincipalStateSessionAuthority:
    """Concrete callbacks for the reviewed ProcessSourceConfiguration.

    The source request is correlated by the principal's sealed command boundary.
    Its ROM model selects data; it never selects code or supplies a profile.
    """
    def __init__(self, *, store: StateCapabilityStore, private_root, profiles: Mapping[str, QualifiedStateProfile],
                 observe_writers: Callable[[ForegroundIdentity, QualifiedStateProfile], WriterStoppedEvidence]):
        if type(store) is not StateCapabilityStore or not callable(observe_writers):
            _error("INVALID_STATE_ADAPTER", "Principal state binding requires a private store and trusted writer authority")
        self.store, self.private_root, self.profiles = store, private_root, dict(profiles)
        self.observe_writers = observe_writers
        self.sessions = {}
        self.last_error = None

    def command_environment(self, foreground, request):
        from bridge.process_source import SourceCommandRequest
        from .adapters.spruce import SourceSnapshotProvider
        if type(request) is not SourceCommandRequest or request.foreground != foreground:
            _error("INVALID_STATE_SESSION", "State launch requires the principal-correlated source model request")
        game = request.source_game
        if game is None or game["system_id"] not in self.profiles:
            return {}
        profile = self.profiles[game["system_id"]]
        profile.assert_qualified()
        provider = SourceSnapshotProvider(profile.sd_root)
        row = provider.game_record(game["system_id"], game["rom_relative"])
        if row["preset_repair_required"] or row["selected_preset"] != profile.preset_id:
            _error("STATE_PROFILE_UNQUALIFIED", "Source-selected engine preset does not match the qualified state engine")
        rom = provider.path(row["rom_path"])
        identity = LaunchIdentity(foreground, row["id"], rom, _file_hash(rom, 8 * 1024**3)[0])
        state_intent = getattr(request, "state_intent", None)
        resume = None
        if state_intent is not None:
            resume = self.store.load(row["id"], profile, self.observe_writers)
            if (state_intent.get("mode") != "resume" or state_intent.get("state_path") != str(resume.state_path) or
                    state_intent.get("state_sha256") != resume.state_sha256 or state_intent.get("slot") != resume.slot):
                _error("STATE_IDENTITY_MISMATCH", "Source Resume intent differs from its authenticated capability")
        session = PrivateStateSession.create(self.private_root, identity, profile, mode="resume" if resume else "save", resume=resume)
        self.sessions[foreground.token] = session
        return session.command_environment

    def completion_observer(self, completion):
        from bridge.principal import PrincipalCompletion
        if type(completion) is not PrincipalCompletion:
            _error("STATE_FOREGROUND_UNVERIFIED", "Only the sealed principal process boundary may observe state completion")
        returned = completion.spruce_return()
        session = self.sessions.pop(returned.foreground.token, None)
        if session is None:
            return None
        try:
            values, error = session.consume_completed(returned, self.observe_writers(returned.foreground, session.profile))
            for value in values:
                self.store.save(session, value)
            self.last_error = error
            return values
        except (FileNotFoundError, StateEvidenceError, OSError) as error:
            # Kernel foreground completion still stands. A failed/missing state
            # result creates no state capability and cannot enable Resume.
            self.last_error = getattr(error, "code", "NO_COMPLETED_STATE")
            return None
        finally:
            session.close()

    def resume_evidence(self):
        records = {}
        for profile in self.profiles.values():
            for game_id in self.store.game_ids():
                try:
                    records[game_id] = self.store.load(game_id, profile, self.observe_writers)
                except (FileNotFoundError, StateEvidenceError, OSError):
                    continue
        return records

    def source_mode_actions(self, device):
        if not callable(getattr(device, "run_game", None)):
            _error("INVALID_STATE_ADAPTER", "Resume must retain the initialized source game authority")
        return {profile.preset_id: {"resume": lambda model, evidence: self.stage_resume(model, evidence, device.run_game)}
                for profile in self.profiles.values()}

    @staticmethod
    def stage_resume(model, evidence, run_existing_game):
        """Source mode callback: journal explicit intent, then existing run_game."""
        from bridge.process_source import capture_state_resume_intent
        if type(evidence) is not VerifiedState or not callable(run_existing_game):
            _error("INVALID_STATE_EVIDENCE", "Source Resume requires a verified typed capability and existing game route")
        evidence.validate_game(evidence.identity.game_id, evidence.profile.preset_id, getattr(model, "rom_file_path", ""))
        capture_state_resume_intent(state_path=str(evidence.state_path), state_sha256=evidence.state_sha256, slot=evidence.slot)
        return run_existing_game(model)
