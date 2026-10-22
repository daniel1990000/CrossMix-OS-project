#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare and record a private, operator-run TG5040 acceptance session.

Collection is read-only apart from the explicit session directory. This tool
never starts games, signals processes, exports USB, restores saves, changes
hardware or activates profiles. Operator results remain claims for review.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import uuid

from inventory import collect as inventory_collect
from installed_runtime import InstalledTree, collect as runtime_collect

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = PROJECT / "packaging/profiles/spruce454-tg5040-development.json"
MAX_JSON = 4 * 1024 * 1024
MAX_SAVE = 64 * 1024 * 1024
CASES = {
    "restore": "Prove original card, internal launcher/scene and offline classic recovery on a spare/restorable setup.",
    "boot": "Cold boot classic and project views, real first-frame input, force-classic recovery and failed-init fallback.",
    "input": "Built-in sticks/buttons, physical Confirm/Back, held keys, controller disconnect and recovery chord.",
    "library": "Unicode/duplicate filenames, favorites/recents persistence, per-game preset identity and advanced routes.",
    "launch_return": "Launch/quit each qualified engine; prove foreground subtree ended before UI/input ownership returns.",
    "save_resume": "Battery saves stay intact; exact completed state evidence and verified state-load acknowledgement match game/engine/session.",
    "native_controls": "PPSSPP/RetroArch native widgets and per-game overlays; menu convention leaves gameplay controls unchanged.",
    "appearance": "Normal/high contrast, scaling, motion, native themes and readable advanced-screen exceptions on the physical panel.",
    "settings": "Existing brightness/sound/network/controller authorities, preview/apply/undo and competing-writer refusal.",
    "power_sleep": "Normal save-safe exit, sleep/wake, audio, low battery and existing power-off owner; no competing watcher.",
    "usb": "Stop storage users, clean unmount/export and return; reject failed staging without mounted-card export.",
    "storage_updates": "FAT/exFAT interrupted config/overlay transactions, update coexistence and rollback without restoring older saves.",
    "ports": "Each selected port's exact engine/runtime/owner data, input, save persistence and fixed-scene measurements.",
}
_SESSION = ContextVar("device_acceptance_session", default=None)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def no_links(path):
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("session paths cannot traverse parent directories")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("session paths cannot contain symlinks")
    return path


def directory_fd(path):
    """Open every component without following links; retain a locked session."""
    path = no_links(path)
    anchor = _SESSION.get()
    if anchor is not None and path.is_relative_to(anchor[0]):
        fd, parts = os.dup(anchor[1]), path.relative_to(anchor[0]).parts
    else:
        fd, parts = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC), path.parts[1:]
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def exists(path):
    path = no_links(path)
    parent = directory_fd(path.parent)
    try:
        try:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False
    finally:
        os.close(parent)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("session JSON contains duplicate keys")
        value[key] = item
    return value


def read_json(path):
    path = no_links(path)
    parent = directory_fd(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_JSON:
                raise ValueError("session JSON must be a bounded regular file")
            raw = stream.read(MAX_JSON + 1)
            after = os.fstat(stream.fileno())
            named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            key = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
            if len(raw) != info.st_size or key(info) != key(after) or key(after) != key(named):
                raise ValueError("session JSON changed while reading")
        value = json.loads(raw, object_pairs_hook=unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite session JSON")))
        if not isinstance(value, dict):
            raise ValueError("session JSON must be an object")
        return value, digest(raw)
    finally:
        os.close(parent)


def put_new(path, value):
    raw = encoded(value)
    if len(raw) > MAX_JSON:
        raise ValueError("session evidence exceeded its budget")
    path = no_links(path)
    parent = directory_fd(path.parent)
    try:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
    finally:
        os.close(parent)
    return digest(raw)


@contextmanager
def locked(session):
    session = no_links(session)
    parent = directory_fd(session)
    fd, token = None, None
    try:
        info = os.fstat(parent)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("acceptance session must be a private 0700 directory")
        fd = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or
                stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("acceptance session lock must be a private regular file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        token = _SESSION.set((session, parent))
        yield session
    finally:
        if token is not None:
            _SESSION.reset(token)
        if fd is not None:
            os.close(fd)
        os.close(parent)


def manifest(session):
    value, _ = read_json(Path(session) / "session.json")
    if (value.get("kind") != "tg5040-device-acceptance-session" or type(value.get("schema")) is not int or value.get("schema") != 1
            or not re.fullmatch(r"[0-9a-f]{32}", value.get("session_id", ""))
            or value.get("required_cases") != list(CASES) or value.get("cases") != CASES
            or value.get("hardware_qualified") is not False or value.get("automatic_activation") is not False):
        raise ValueError("acceptance session identity or case set is invalid")
    profile, profile_hash = read_json(Path(session) / "expected-profile.json")
    if profile_hash != value.get("profile_sha256"):
        raise ValueError("the retained expected profile changed")
    return value, profile


def create(output, profile=DEFAULT_PROFILE):
    output = no_links(output)
    expected, _ = read_json(profile)
    if expected.get("model") != "trimui-smart-pro" or expected.get("architecture") != "aarch64":
        raise ValueError("select the original Smart Pro ARM64 profile")
    parent = directory_fd(output.parent)
    try:
        os.mkdir(output.name, mode=0o700, dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)
    try:
        profile_hash = put_new(output / "expected-profile.json", expected)
        value = {"schema": 1, "kind": "tg5040-device-acceptance-session", "session_id": uuid.uuid4().hex,
                 "created_at": datetime.now(timezone.utc).isoformat(), "target": "TG5040",
                 "profile_sha256": profile_hash, "required_cases": list(CASES),
                 "hardware_qualified": False, "automatic_activation": False,
                 "cases": CASES, "privacy": "Private local evidence; no automatic upload or raw save contents."}
        put_new(output / "session.json", value)
        return value
    except BaseException:
        # Preserve any written evidence; never remove an operator-owned tree.
        raise


def save_name(relative):
    if not isinstance(relative, str):
        raise ValueError("save selection must be relative text")
    path = PurePosixPath(relative)
    if (path.is_absolute() or path.parts[:1] != ("Saves",)
            or any(p in {".", ".."} for p in path.parts) or str(path) != relative
            or len(relative) > 4096 or any(ord(c) < 32 for c in relative)):
        raise ValueError("select exact relative files under Saves/; no directory scanning")
    return path


def save_identity(tree, relative):
    path = save_name(relative)
    # Installed runtime inspection follows symlinks within its virtual root.
    # Owner-selected save files deliberately use a stricter no-link boundary.
    parent_path = tree.card.joinpath(*path.parts[:-1])
    parent = tree._directory(parent_path)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SAVE:
                raise ValueError("selected save must be a regular file of at most 64 MiB")
            h, remaining = hashlib.sha256(), before.st_size
            while remaining:
                block = stream.read(min(1024 * 1024, remaining))
                if not block:
                    raise ValueError("selected save changed during hashing")
                h.update(block)
                remaining -= len(block)
            extra = stream.read(1)
            after = os.fstat(stream.fileno())
            named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            key = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
            if extra or key(before) != key(after) or key(after) != key(named):
                raise ValueError("selected save changed during hashing")
            current = tree._directory(parent_path)
            try:
                if key(os.fstat(parent))[:2] != key(os.fstat(current))[:2]:
                    raise ValueError("selected save directory changed during hashing")
            finally:
                os.close(current)
            return {"path": relative, "size": before.st_size, "sha256": h.hexdigest()}
    finally:
        os.close(parent)


def checksummed(value):
    return dict(value, content_sha256=digest(encoded(value)))


def validate_content(value, label):
    body = {key: item for key, item in value.items() if key != "content_sha256"}
    if value.get("content_sha256") != digest(encoded(body)):
        raise ValueError(label + " changed: content checksum is invalid")


def snapshot_value(session, identity, phase):
    value, hashed = read_json(Path(session) / (phase + ".json"))
    if (value.get("kind") != "read-only-acceptance-snapshot" or type(value.get("schema")) is not int or value.get("schema") != 1
            or value.get("phase") != phase or value.get("session_id") != identity["session_id"]
            or value.get("hardware_qualified") is not False or value.get("automatic_activation") is not False):
        raise ValueError("snapshot changed or belongs to another acceptance session")
    validate_content(value, "snapshot")
    saves = value.get("save_hashes_only")
    if not isinstance(saves, list) or len(saves) > 64:
        raise ValueError("snapshot save identities are invalid")
    names = set()
    for row in saves:
        if (not isinstance(row, dict) or set(row) != {"path", "size", "sha256"} or
                type(row["size"]) is not int or not 0 <= row["size"] <= MAX_SAVE or
                not isinstance(row["sha256"], str) or re.fullmatch("[0-9a-f]{64}", row["sha256"]) is None):
            raise ValueError("snapshot save identity is invalid")
        save_name(row["path"])
        if row["path"] in names:
            raise ValueError("snapshot contains duplicate save identities")
        names.add(row["path"])
    context = value.get("capture_context")
    if (not isinstance(context, dict) or set(context) != {"root", "sd_root"} or
            any(not isinstance(item, dict) or set(item) != {"path", "device", "inode"} or
                not isinstance(item["path"], str) or not item["path"].startswith("/") or
                type(item["device"]) is not int or type(item["inode"]) is not int
                for item in context.values())):
        raise ValueError("snapshot capture context is invalid")
    return value, hashed


def capture(session, phase, root=Path("/"), sd_root=Path("/mnt/SDCARD"), *, saves=(), pid=None):
    if phase not in {"before", "after"} or len(saves) > 64 or len(set(saves)) != len(saves):
        raise ValueError("choose before/after and at most 64 distinct exact save files")
    session, sd_root = no_links(session), Path(sd_root).resolve(strict=True)
    if session.resolve().is_relative_to(sd_root):
        raise ValueError("keep the acceptance session outside the inspected card")
    with locked(session):
        identity, profile = manifest(session)
        target = session / (phase + ".json")
        if exists(target):
            raise ValueError("snapshot already exists; use a new acceptance session")
        if phase == "after" and not exists(session / "before.json"):
            raise ValueError("capture the before snapshot first")
        tree = InstalledTree(root, sd_root)
        context = {name: {"path": str(path), "device": tree._identities[path][0], "inode": tree._identities[path][1]}
                   for name, path in (("root", tree.root), ("sd_root", tree.card))}
        value = {"schema": 1, "kind": "read-only-acceptance-snapshot", "session_id": identity["session_id"],
                 "phase": phase, "captured_at": datetime.now(timezone.utc).isoformat(),
                 "capture_context": context,
                 "inventory": inventory_collect(root, sd_root, profile),
                 "save_hashes_only": [save_identity(tree, name) for name in sorted(saves)],
                 "runtime": runtime_collect(root, sd_root, "/mnt/SDCARD/Emu/PSP/PPSSPPSDL_TrimUI", pid=pid)
                            if pid is not None else None,
                 "hardware_qualified": False, "automatic_activation": False}
        if phase == "after":
            before, before_hash = snapshot_value(session, identity, "before")
            if before["capture_context"] != context:
                raise ValueError("inspected root/card filesystem identity changed; use a separate session")
            value["baseline_sha256"] = before_hash
            old = {row["path"]: row for row in before["save_hashes_only"]}
            if set(old) != set(saves):
                raise ValueError("before/after snapshots must select the same save files")
            value["save_comparison"] = [{"path": row["path"], "unchanged": row == old[row["path"]]}
                                        for row in value["save_hashes_only"]]
        for path in (tree.root, tree.card):
            current = tree._directory(path)
            os.close(current)
        value = checksummed(value)
        put_new(target, value)
        return value


def attempts(session, identity, case):
    directory = Path(session) / case
    if not exists(directory):
        return []
    records, previous = [], None
    fd = directory_fd(directory)
    try:
        files = sorted(os.listdir(fd))
    finally:
        os.close(fd)
    if len(files) > 100:
        raise ValueError("case attempt budget exceeded")
    for number, name in enumerate(files, 1):
        if name != "%03d.json" % number:
            raise ValueError("case attempt sequence changed")
        value, hashed = read_json(directory / name)
        validate_content(value, "case evidence")
        if (type(value.get("schema")) is not int or value.get("schema") != 1 or value.get("session_id") != identity["session_id"] or value.get("case") != case
                or value.get("previous_sha256") != previous or value.get("status") not in {"pass", "fail", "blocked"}
                or value.get("hardware_qualified") is not False or not isinstance(value.get("note"), str)
                or not value["note"].strip() or len(value["note"]) > 2048 or not isinstance(value.get("snapshot_sha256"), dict)
                or any(phase not in {"before", "after"} or not isinstance(hashed, str) or re.fullmatch("[0-9a-f]{64}", hashed) is None
                       for phase, hashed in value["snapshot_sha256"].items())):
            raise ValueError("case evidence chain is inconsistent")
        records.append((value, hashed))
        previous = hashed
    return records


def record(session, case, status, note):
    if case not in CASES or status not in {"pass", "fail", "blocked"}:
        raise ValueError("select a declared case and pass/fail/blocked")
    if not isinstance(note, str) or not note.strip() or len(note) > 2048:
        raise ValueError("record a bounded description of the actual observation")
    with locked(session) as session:
        identity, _ = manifest(session)
        previous = attempts(session, identity, case)
        if len(previous) >= 100:
            raise ValueError("case attempt budget exceeded")
        evidence = {}
        for phase in ("before", "after"):
            if exists(session / (phase + ".json")):
                snapshot, hashed = snapshot_value(session, identity, phase)
                evidence[phase] = hashed
        directory = session / case
        parent = directory_fd(session)
        try:
            try:
                os.mkdir(case, mode=0o700, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                pass
        finally:
            os.close(parent)
        value = {"schema": 1, "session_id": identity["session_id"], "case": case, "status": status,
                 "observed_at": datetime.now(timezone.utc).isoformat(), "note": note,
                 "snapshot_sha256": evidence, "previous_sha256": previous[-1][1] if previous else None,
                 "provenance": "operator observation; independent review required", "hardware_qualified": False}
        value = checksummed(value)
        put_new(directory / ("%03d.json" % (len(previous) + 1)), value)
        return value


def report(session):
    with locked(session) as session:
        identity, _ = manifest(session)
        snapshots = {}
        for phase in ("before", "after"):
            if exists(session / (phase + ".json")):
                snapshot, hashed = snapshot_value(session, identity, phase)
                snapshots[phase] = {"sha256": hashed, "value": snapshot}
        if "after" in snapshots and ("before" not in snapshots or
                snapshots["after"]["value"].get("baseline_sha256") != snapshots["before"]["sha256"]):
            raise ValueError("after snapshot baseline changed")
        if "after" in snapshots:
            before, after = snapshots["before"]["value"], snapshots["after"]["value"]
            old = {row["path"]: row for row in before["save_hashes_only"]}
            if before["capture_context"] != after["capture_context"] or set(old) != {row["path"] for row in after["save_hashes_only"]}:
                raise ValueError("before/after filesystem or save selection changed")
            comparison = [{"path": row["path"], "unchanged": row == old[row["path"]]} for row in after["save_hashes_only"]]
            if comparison != after.get("save_comparison"):
                raise ValueError("after save comparison is inconsistent")
        results = {}
        for case in CASES:
            values = attempts(session, identity, case)
            results[case] = {"status": values[-1][0]["status"] if values else "not_run", "attempts": len(values)}
            for attempt, _ in values:
                for phase, expected in attempt["snapshot_sha256"].items():
                    if phase not in snapshots or expected != snapshots[phase]["sha256"]:
                        raise ValueError("referenced snapshot changed")
        return {"schema": 1, "kind": "device-acceptance-review", "session_id": identity["session_id"],
                "cases": results, "operator_cases_all_pass": all(row["status"] == "pass" for row in results.values()),
                "snapshots_complete": len(snapshots) == 2,
                "snapshot_sha256": {key: value["sha256"] for key, value in snapshots.items()},
                "hardware_qualified": False, "automatic_activation": False, "review_required": True,
                "limits": "Operator notes and recorded hashes cannot mint a trusted installed profile or certify physical behavior."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("prepare")
    create_parser.add_argument("--output", type=Path, required=True)
    create_parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--session", type=Path, required=True)
    capture_parser.add_argument("--phase", choices=("before", "after"), required=True)
    capture_parser.add_argument("--root", type=Path, default=Path("/"))
    capture_parser.add_argument("--sd-root", type=Path, default=Path("/mnt/SDCARD"))
    capture_parser.add_argument("--save", action="append", default=[])
    capture_parser.add_argument("--pid", type=int)
    record_parser = commands.add_parser("record")
    record_parser.add_argument("--session", type=Path, required=True)
    record_parser.add_argument("--case", choices=tuple(CASES), required=True)
    record_parser.add_argument("--status", choices=("pass", "fail", "blocked"), required=True)
    record_parser.add_argument("--note", required=True)
    report_parser = commands.add_parser("report")
    report_parser.add_argument("--session", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            value = create(args.output, args.profile)
        elif args.command == "capture":
            value = capture(args.session, args.phase, args.root, args.sd_root, saves=args.save, pid=args.pid)
        elif args.command == "record":
            value = record(args.session, args.case, args.status, args.note)
        else:
            value = report(args.session)
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        print("device-acceptance: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
