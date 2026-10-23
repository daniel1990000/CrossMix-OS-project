# SPDX-License-Identifier: MIT
"""Bounded local host-pilot evidence, never a device-admission authority.

Only fixed event names and opaque digests are retained. A successful append
means the file was fsynced; it does not establish independent-media custody,
physical observation or authenticity against an owner replacing this program.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading

from psp_shell.runtime import ContractError


DIGEST = re.compile(r"[0-9a-f]{64}\Z")
EVENTS = frozenset({"prepared", "started", "action_denied", "return_requested",
                    "completed", "blocked", "expired", "identity_changed",
                    "callback_failed", "clock_failed"})
MAX_EVENTS = 256
MAX_BYTES = 256 * 1024
ZERO = "0" * 64
PROVENANCE = frozenset({"host_fixture", "private_experimental"})


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _fail():
    return ContractError("EXPERIMENTAL_EVIDENCE", "Host pilot evidence could not be durably retained; further actions are blocked")


def _directory(path):
    path = Path(path).absolute()
    if ".." in path.parts:
        raise _fail()
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_fd
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _valid_row(row, sequence, previous):
    fields = {"schema", "provenance", "session", "candidate", "boot", "owner", "sequence",
              "event", "monotonic_ns", "previous", "sha256"}
    if (type(row) is not dict or set(row) != fields or type(row["schema"]) is not int or row["schema"] != 1 or
            row["provenance"] not in PROVENANCE or row["event"] not in EVENTS or
            type(row["sequence"]) is not int or row["sequence"] != sequence or
            type(row["monotonic_ns"]) is not int or row["monotonic_ns"] < 0 or
            row["previous"] != previous or
            any(type(row[name]) is not str or not DIGEST.fullmatch(row[name])
                for name in ("session", "candidate", "boot", "owner", "previous", "sha256"))):
        raise _fail()
    body = {key: value for key, value in row.items() if key != "sha256"}
    if hashlib.sha256(encoded(body)).hexdigest() != row["sha256"]:
        raise _fail()


class HostEvidenceJournal:
    """One private writer and one new journal; records cannot be resumed as authority.

    The caller creates a private output directory outside the fixture payload.
    Directory/file replacement, extra links, changed permissions, a partial
    write or failed fsync poison this writer. There is no rollback/retry path
    that could mislabel an uncertain record as successful.
    """

    def __init__(self, directory, *, session, candidate, boot, owner, provenance="host_fixture"):
        self.directory = Path(directory).absolute()
        self._thread = threading.get_ident()
        self._dir = self._fd = None
        self._failed, self._closed = False, False
        self._sequence, self._bytes, self._previous, self._time = 0, 0, ZERO, -1
        self._content_hash = hashlib.sha256()
        self._binding = dict(session=session, candidate=candidate, boot=boot, owner=owner)
        if type(provenance) is not str or provenance not in PROVENANCE:
            raise _fail()
        self._provenance = provenance
        if any(type(value) is not str or not DIGEST.fullmatch(value) for value in self._binding.values()):
            raise _fail()
        try:
            self._dir = _directory(self.directory)
            info = os.fstat(self._dir)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise _fail()
            self._root_identity = (info.st_dev, info.st_ino)
            self._fd = os.open("events.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                               0o600, dir_fd=self._dir)
            self._file_identity = (os.fstat(self._fd).st_dev, os.fstat(self._fd).st_ino)
            os.fsync(self._fd)
            os.fsync(self._dir)
            self._stamp = os.fstat(self._fd)
        except BaseException as exc:
            self.close()
            raise _fail() from exc

    def _anchor(self):
        if self._failed or self._closed or self._thread != threading.get_ident():
            raise _fail()
        check = _directory(self.directory)
        try:
            root = os.fstat(check)
            info = os.stat("events.jsonl", dir_fd=check, follow_symlinks=False)
            current = os.fstat(self._fd)
            if ((root.st_dev, root.st_ino) != self._root_identity or
                    root.st_uid != os.geteuid() or stat.S_IMODE(root.st_mode) != 0o700 or
                    (info.st_dev, info.st_ino) != self._file_identity or
                    not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                    info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600 or
                    current.st_size != self._bytes or
                    any(getattr(current, key) != getattr(self._stamp, key)
                        for key in ("st_mtime_ns", "st_ctime_ns"))):
                raise _fail()
            reader = os.open("events.jsonl", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=check)
            try:
                read_info = os.fstat(reader)
                raw = os.read(reader, MAX_BYTES + 1)
                after = os.fstat(reader)
                if ((read_info.st_dev, read_info.st_ino) != self._file_identity or
                        len(raw) != self._bytes or hashlib.sha256(raw).digest() != self._content_hash.digest() or
                        any(getattr(after, key) != getattr(self._stamp, key)
                            for key in ("st_size", "st_mtime_ns", "st_ctime_ns"))):
                    raise _fail()
            finally:
                os.close(reader)
        finally:
            os.close(check)

    def append(self, event, monotonic_ns):
        try:
            self._anchor()
            if (type(event) is not str or event not in EVENTS or
                    type(monotonic_ns) is not int or monotonic_ns < self._time or
                    monotonic_ns < 0 or self._sequence >= MAX_EVENTS):
                raise _fail()
            row = dict(schema=1, provenance=self._provenance, **self._binding,
                       sequence=self._sequence, event=event, monotonic_ns=monotonic_ns,
                       previous=self._previous)
            row["sha256"] = hashlib.sha256(encoded(row)).hexdigest()
            raw = encoded(row) + b"\n"
            if self._bytes + len(raw) > MAX_BYTES:
                raise _fail()
            # A short write is uncertain evidence, not a reason to replay it.
            if os.write(self._fd, raw) != len(raw):
                raise _fail()
            os.fsync(self._fd)
            self._bytes += len(raw)
            self._sequence += 1
            self._previous, self._time = row["sha256"], monotonic_ns
            self._content_hash.update(raw)
            self._stamp = os.fstat(self._fd)
            self._anchor()
            return row["sha256"]
        except BaseException as exc:
            self._failed = True
            raise _fail() from exc

    def close(self):
        self._closed = True
        for name in ("_fd", "_dir"):
            descriptor = getattr(self, name, None)
            if descriptor is not None:
                os.close(descriptor)
                setattr(self, name, None)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def read_host_journal(directory):
    """Fresh bounded readback with chain/binding checks; never an admission loader."""
    root = descriptor = None
    try:
        root = _directory(directory)
        root_before = os.fstat(root)
        if root_before.st_uid != os.geteuid() or stat.S_IMODE(root_before.st_mode) != 0o700:
            raise _fail()
        descriptor = os.open("events.jsonl", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o600 or
                not 0 < before.st_size <= MAX_BYTES):
            raise _fail()
        raw = os.read(descriptor, MAX_BYTES + 1)
        after = os.fstat(descriptor)
        anchored = os.stat("events.jsonl", dir_fd=root, follow_symlinks=False)
        if (len(raw) != before.st_size or not raw.endswith(b"\n") or
                (anchored.st_dev, anchored.st_ino) != (before.st_dev, before.st_ino) or
                any(getattr(before, key) != getattr(after, key)
                    for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"))):
            raise _fail()
        lines = raw.splitlines()
        if not 0 < len(lines) <= MAX_EVENTS:
            raise _fail()
        result, previous, last_time, binding = [], ZERO, -1, None
        for index, line in enumerate(lines):
            def unique(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise _fail()
                    value[key] = item
                return value
            row = json.loads(line, object_pairs_hook=unique)
            _valid_row(row, index, previous)
            observed = tuple(row[name] for name in ("session", "candidate", "boot", "owner", "provenance"))
            if (binding is not None and binding != observed) or row["monotonic_ns"] < last_time:
                raise _fail()
            result.append(row)
            binding, previous, last_time = observed, row["sha256"], row["monotonic_ns"]
        named_root = _directory(directory)
        try:
            current_root = os.fstat(named_root)
            current_file = os.stat("events.jsonl", dir_fd=named_root, follow_symlinks=False)
            current = os.fstat(descriptor)
            if ((current_root.st_dev, current_root.st_ino) != (root_before.st_dev, root_before.st_ino) or
                    current_root.st_uid != os.geteuid() or stat.S_IMODE(current_root.st_mode) != 0o700 or
                    (current_file.st_dev, current_file.st_ino) != (before.st_dev, before.st_ino) or
                    any(getattr(before, key) != getattr(current, key)
                        for key in ("st_mode", "st_size", "st_mtime_ns", "st_ctime_ns"))):
                raise _fail()
        finally:
            os.close(named_root)
        return tuple(result)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise _fail() from exc
    finally:
        for descriptor_to_close in (descriptor, root):
            if descriptor_to_close is not None:
                os.close(descriptor_to_close)
