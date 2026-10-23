# SPDX-License-Identifier: MIT
"""Host-testable foundations for a single view-only experimental case.

This module has no device entry, configuration loader or process launcher. Its
only factory explicitly admits synthetic host fixtures. It cannot satisfy R05,
D02/D03 or production qualification, and is not called by shipped PyUI. The
future fixed device entry still requires independent implementation/review.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import threading
import time

from psp_shell.runtime import ContractError, SPRUCE_COMMIT
from .experimental_journal import DIGEST, HostEvidenceJournal, encoded


PYUI_TREE = "4d0bdb3111d9226fbacbea6c89d65e540620e21e"
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
BOOT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
VIEW_ACTIONS = frozenset({"navigate", "render", "poll_input", "read_library", "search"})
MAX_FILES, MAX_BYTES = 2048, 64 * 1024 * 1024
_HOST_SEAL = object()


def _error(code="EXPERIMENTAL_REJECTED"):
    return ContractError(code, "Host experimental case is unavailable or blocked; no device qualification is granted")


def _relative(value):
    if (type(value) is not str or not value or len(value) > 1024 or "\\" in value or
            any(ord(char) < 32 for char in value) or
            PurePosixPath(value).is_absolute() or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise _error()
    return value


@dataclass(frozen=True)
class ExpectedFile:
    path: str
    sha256: str

    def __post_init__(self):
        _relative(self.path)
        if type(self.sha256) is not str or not DIGEST.fullmatch(self.sha256):
            raise _error()


@dataclass(frozen=True)
class HostCandidate:
    """Independent reviewed workstation bindings, never derived by admission.

    Package/key/source digests bind an already reviewed build. This type does
    not verify a package signature or prove the origins of supplied hashes.
    `files` is the exact whole fixture payload inventory, including imports.
    """

    frontend_commit: str
    source_inventory_sha256: str
    release_descriptor_sha256: str
    package_sha256: str
    signer_sha256: str
    files: tuple[ExpectedFile, ...]
    spruce_commit: str = SPRUCE_COMMIT
    pyui_tree: str = PYUI_TREE

    def __post_init__(self):
        if (type(self.frontend_commit) is not str or not COMMIT.fullmatch(self.frontend_commit) or
                self.spruce_commit != SPRUCE_COMMIT or self.pyui_tree != PYUI_TREE or
                any(type(getattr(self, name)) is not str or not DIGEST.fullmatch(getattr(self, name))
                    for name in ("source_inventory_sha256", "release_descriptor_sha256", "package_sha256", "signer_sha256")) or
                type(self.files) is not tuple or not 0 < len(self.files) <= MAX_FILES or
                any(type(item) is not ExpectedFile for item in self.files) or
                len({item.path for item in self.files}) != len(self.files)):
            raise _error()
        object.__setattr__(self, "files", tuple(sorted(self.files, key=lambda item: item.path)))

    @property
    def sha256(self):
        return hashlib.sha256(encoded(asdict(self))).hexdigest()


def inspect_host_fixture(root):
    """Read an exact bounded fixture tree without following links or running it.

    The conventional device root is refused. Arbitrary removable media cannot
    be identified just from a path; the caller must supply synthetic content.
    No target can be admitted because the observation provenance remains host.
    """
    root = Path(root).absolute()
    if ".." in root.parts or root == Path("/mnt/SDCARD") or Path("/mnt/SDCARD") in root.parents:
        raise _error("INVALID_FIXTURE")
    from .experimental_journal import _directory
    descriptor = None
    try:
        descriptor = _directory(root)
        root_before = os.fstat(descriptor)
        files, total, entries = [], 0, 0

        def walk(fd, prefix="", depth=0):
            nonlocal total, entries
            if depth > 32:
                raise _error()
            before = os.fstat(fd)
            names = []
            with os.scandir(fd) as listing:
                for entry in listing:
                    names.append(entry.name)
                    if len(names) > MAX_FILES or entries + len(names) > MAX_FILES * 2:
                        raise _error()
            names.sort()
            for name in names:
                entries += 1
                if entries > MAX_FILES * 2:
                    raise _error()
                relative = _relative(prefix + name)
                item = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(item.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        check = os.fstat(child)
                        if (item.st_dev, item.st_ino) != (check.st_dev, check.st_ino):
                            raise _error()
                        walk(child, relative + "/", depth + 1)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(item.st_mode) and item.st_nlink == 1:
                    if len(files) >= MAX_FILES or total + item.st_size > MAX_BYTES:
                        raise _error()
                    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                    try:
                        check = os.fstat(child)
                        if (item.st_dev, item.st_ino) != (check.st_dev, check.st_ino) or not stat.S_ISREG(check.st_mode):
                            raise _error()
                        value, count = hashlib.sha256(), 0
                        while count <= item.st_size:
                            block = os.read(child, min(65536, item.st_size + 1 - count))
                            if not block:
                                break
                            count += len(block)
                            value.update(block)
                        after = os.fstat(child)
                        if (count != item.st_size or any(getattr(item, key) != getattr(after, key)
                                for key in ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns"))):
                            raise _error()
                        files.append(ExpectedFile(relative, value.hexdigest()))
                        total += count
                    finally:
                        os.close(child)
                else:
                    raise _error()
            after = os.fstat(fd)
            if any(getattr(before, key) != getattr(after, key)
                   for key in ("st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")):
                raise _error()

        walk(descriptor)
        verify = _directory(root)
        try:
            root_after = os.fstat(verify)
            if (root_before.st_dev, root_before.st_ino) != (root_after.st_dev, root_after.st_ino):
                raise _error()
        finally:
            os.close(verify)
        return tuple(sorted(files, key=lambda item: item.path))
    except (OSError, ValueError, TypeError) as exc:
        raise _error() from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


@dataclass(frozen=True)
class HostObservation:
    boot_id: str
    principal_pid: int
    principal_start: str
    files: tuple[ExpectedFile, ...]
    preferences_ready: bool
    owners_ready: bool
    dirty: bool = False
    staged_command: bool = False
    live_device: bool = False

    def __post_init__(self):
        if (type(self.boot_id) is not str or not BOOT.fullmatch(self.boot_id) or
                type(self.principal_pid) is not int or self.principal_pid <= 0 or
                type(self.principal_start) is not str or not self.principal_start.isascii() or not self.principal_start.isdigit() or
                type(self.files) is not tuple or any(type(item) is not ExpectedFile for item in self.files) or
                any(type(getattr(self, name)) is not bool for name in
                    ("preferences_ready", "owners_ready", "dirty", "staged_command", "live_device"))):
            raise _error()

    @property
    def owner_sha256(self):
        return hashlib.sha256(encoded([self.principal_pid, self.principal_start])).hexdigest()


@dataclass(frozen=True)
class HostReturnObservation:
    owners_restored: bool
    idle: bool
    classic_frame_ready: bool
    classic_input_ready: bool
    staged_command: bool = False

    def safe(self):
        return (all(type(getattr(self, name)) is bool for name in self.__dataclass_fields__) and
                self.owners_restored and self.idle and self.classic_frame_ready and
                self.classic_input_ready and not self.staged_command)


class HostViewAdmission:
    """Single-use host capability with cooperative, owner-thread-only decisions.

    Deadlines are checked before/after callbacks. They cannot interrupt blocked
    SDL, input or restoration calls, terminate processes, or prove real return.
    A blocked/uncertain case never supplies permission to start classic.
    """

    def __init__(self, seal, candidate, observe, journal, clock, now, startup_window, view_seconds, return_seconds):
        if seal is not _HOST_SEAL:
            raise _error()
        self._candidate, self._observe, self.journal, self._clock = candidate, observe, journal, clock
        self._thread, self._last_time = threading.get_ident(), now
        self._startup_deadline, self._view_seconds, self._return_seconds = now + startup_window, view_seconds, return_seconds
        self._phase, self._view_deadline, self._return_deadline = "prepared", None, None
        self._identity = None

    def __copy__(self):
        raise TypeError("Host admissions cannot be copied")

    def __deepcopy__(self, _):
        raise TypeError("Host admissions cannot be copied")

    def __reduce_ex__(self, _):
        raise TypeError("Host admissions cannot be serialized")

    @property
    def phase(self):
        return self._phase

    @property
    def classic_return_permitted(self):
        return self._phase == "completed"

    def _now(self):
        if threading.get_ident() != self._thread:
            self._phase = "blocked"
            raise _error()
        try:
            value = self._clock()
        except BaseException:
            self._phase = "blocked"
            self._record("clock_failed", self._last_time)
            raise _error("EXPERIMENTAL_CLOCK") from None
        if (type(value) not in {int, float} or not math.isfinite(value) or value < self._last_time or value < 0):
            self._phase = "blocked"
            self._record("clock_failed", self._last_time)
            raise _error("EXPERIMENTAL_CLOCK")
        self._last_time = value
        return value

    def _record(self, event, now):
        try:
            self.journal.append(event, int(now * 1_000_000_000))
        except BaseException:
            self._phase = "blocked"
            raise

    def _blocked(self, event, now):
        self._phase = "blocked"
        self._record(event, now)
        raise _error()

    def _check_identity(self, now):
        try:
            observed = self._observe()
            valid = (type(observed) is HostObservation and observed.live_device is False and
                     observed.files == self._candidate.files and observed.preferences_ready and
                     observed.owners_ready and not observed.dirty and not observed.staged_command)
            identity = (observed.boot_id, observed.principal_pid, observed.principal_start) if valid else None
        except BaseException:
            self._blocked("identity_changed", now)
        if not valid or self._identity is not None and identity != self._identity:
            self._blocked("identity_changed", now)
        self._identity = identity
        return observed

    def begin(self):
        if self._phase != "prepared":
            raise _error("EXPERIMENTAL_REPLAY")
        now = self._now()
        if now >= self._startup_deadline:
            self._blocked("expired", now)
        self._check_identity(now)
        now = self._now()
        if now >= self._startup_deadline:
            self._blocked("expired", now)
        self._phase, self._view_deadline = "running", now + self._view_seconds
        self._record("started", now)

    def request_return(self):
        now = self._now()
        if self._phase == "return_requested":
            if now >= self._return_deadline:
                self._blocked("expired", now)
            return False
        if self._phase != "running":
            raise _error()
        self._check_identity(now)
        now = self._now()
        self._phase, self._return_deadline = "return_requested", now + self._return_seconds
        self._record("return_requested", now)
        return True

    def poll(self):
        now = self._now()
        if self._phase == "running":
            self._check_identity(now)
            now = self._now()
            if now >= self._view_deadline:
                self.request_return()
            return self._phase
        if self._phase == "return_requested":
            self._check_identity(now)
            now = self._now()
            if now >= self._return_deadline:
                self._blocked("expired", now)
            return self._phase
        raise _error()

    def perform(self, action, callback):
        """Guard one trusted view callback; strings cannot resolve callbacks."""
        now = self._now()
        if self._phase != "running":
            raise _error()
        if type(action) is not str or action not in VIEW_ACTIONS:
            self._blocked("action_denied", now)
        if not callable(callback):
            self._blocked("callback_failed", now)
        if self.poll() != "running":
            return False
        try:
            callback()
        except BaseException:
            self._blocked("callback_failed", self._now())
        self.poll()
        return self._phase == "running"

    def complete_return(self, restore):
        now = self._now()
        if self._phase != "return_requested":
            raise _error()
        self.poll()
        if not callable(restore):
            self._blocked("callback_failed", now)
        try:
            result = restore()
        except BaseException:
            self._blocked("callback_failed", self._now())
        now = self._now()
        self._check_identity(now)
        now = self._now()
        if now >= self._return_deadline or type(result) is not HostReturnObservation or not result.safe():
            self._blocked("blocked", now)
        self._record("completed", now)
        self._phase = "completed"

    def close(self):
        # Closing evidence never clears or completes an active lifetime.
        if self._phase != "completed":
            self._phase = "blocked"
        self.journal.close()


def prepare_host_view(candidate, observe, evidence_directory, *, clock=time.monotonic,
                      startup_window=60, view_seconds=120, return_seconds=5):
    """Prepare a host fixture only. There is deliberately no device factory.

    Trusted code supplies independent expected hashes and an observation
    callback. Serialized records, profiles, flags and environment values are
    not consumed. References for real source-use/backups are not invented.
    """
    if type(candidate) is not HostCandidate or not callable(observe) or not callable(clock):
        raise _error()
    for value, maximum in ((startup_window, 60), (view_seconds, 120), (return_seconds, 5)):
        if type(value) not in {int, float} or not math.isfinite(value) or not 0 < value <= maximum:
            raise _error()
    observed = observe()
    if (type(observed) is not HostObservation or observed.live_device is not False or
            observed.files != candidate.files or not observed.preferences_ready or not observed.owners_ready or
            observed.dirty or observed.staged_command):
        raise _error()
    now = clock()
    if type(now) not in {int, float} or not math.isfinite(now) or now < 0:
        raise _error()
    journal = HostEvidenceJournal(evidence_directory, session=secrets.token_hex(32), candidate=candidate.sha256,
                                  boot=hashlib.sha256(observed.boot_id.encode("ascii")).hexdigest(),
                                  owner=observed.owner_sha256)
    try:
        result = HostViewAdmission(_HOST_SEAL, candidate, observe, journal, clock, now,
                                   startup_window, view_seconds, return_seconds)
        result._identity = (observed.boot_id, observed.principal_pid, observed.principal_start)
        result._record("prepared", now)
        return result
    except BaseException:
        journal.close()
        raise
