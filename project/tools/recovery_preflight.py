#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare offline backup/restore bytes; never copy, restore or activate anything.

Manifests are private consistency evidence, not authenticated device qualification.
Roots must be stopped/offline directory trees. This is not a sector-image checker.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import sys

MAX_ENTRIES = 250_000
MAX_BYTES = 2 * 1024 ** 4
MAX_MANIFEST = 64 * 1024 ** 2
MAX_DEPTH = 64
SCOPES = ("card-files", "saves", "internal-files")


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def clean_path(value):
    path = Path(value).absolute()
    if ".." in path.parts:
        raise ValueError("paths cannot contain parent traversal")
    return path


def directory_fd(value):
    path = clean_path(value)
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in path.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def relative_name(value):
    if (not isinstance(value, str) or not value or value == "." or len(value.encode("utf-8")) > 4096
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or "\\" in value or value.startswith("/")
            or value != str(PurePosixPath(value)) or ".." in PurePosixPath(value).parts):
        raise ValueError("invalid manifest relative path")
    return value


def scan_tree(value, scope, *, max_entries=MAX_ENTRIES, max_bytes=MAX_BYTES):
    if scope not in SCOPES or not 0 < max_entries <= MAX_ENTRIES or not 0 <= max_bytes <= MAX_BYTES:
        raise ValueError("invalid scope or inventory budget")
    root = clean_path(value)
    root_fd = directory_fd(root)
    entries, byte_count = [], 0
    root_info = os.fstat(root_fd)

    def visit(fd, prefix, depth):
        nonlocal byte_count
        if depth > MAX_DEPTH:
            raise ValueError("tree exceeds depth budget")
        before_dir = os.fstat(fd)
        names = []
        with os.scandir(fd) as children:
            for child in children:
                if len(names) + len(entries) >= max_entries:
                    raise ValueError("tree exceeds entry budget")
                names.append(child.name)
        for name in sorted(names):
            relative = relative_name(prefix + name)
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            entry = {"path": relative}
            if scope == "internal-files":
                entry.update(mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)
            if stat.S_ISDIR(info.st_mode):
                entry["type"] = "directory"
                entries.append(entry)
                if len(entries) > max_entries:
                    raise ValueError("tree exceeds entry budget")
                child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                   dir_fd=fd)
                try:
                    if fingerprint(info) != fingerprint(os.fstat(child_fd)):
                        raise ValueError("directory changed before inspection")
                    visit(child_fd, relative + "/", depth + 1)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(info.st_mode):
                if info.st_nlink != 1:
                    raise ValueError("multiply linked files require a separately reviewed backup")
                byte_count += info.st_size
                if byte_count > max_bytes:
                    raise ValueError("tree exceeds byte budget")
                file_fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  dir_fd=fd)
                with os.fdopen(file_fd, "rb") as stream:
                    before = os.fstat(stream.fileno())
                    if not stat.S_ISREG(before.st_mode) or fingerprint(info) != fingerprint(before):
                        raise ValueError("file changed before hashing")
                    h, remaining = hashlib.sha256(), before.st_size
                    while remaining:
                        block = stream.read(min(1024 ** 2, remaining))
                        if not block:
                            raise ValueError("file shortened during hashing")
                        h.update(block)
                        remaining -= len(block)
                    if stream.read(1) or fingerprint(before) != fingerprint(os.fstat(stream.fileno())):
                        raise ValueError("file changed during hashing")
                if fingerprint(before) != fingerprint(os.stat(name, dir_fd=fd, follow_symlinks=False)):
                    raise ValueError("file name changed during hashing")
                entry.update(type="file", size=before.st_size, sha256=h.hexdigest())
                entries.append(entry)
            elif stat.S_ISLNK(info.st_mode):
                target = os.readlink(name, dir_fd=fd)
                if len(os.fsencode(target)) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in target):
                    raise ValueError("invalid symlink target")
                if fingerprint(info) != fingerprint(os.stat(name, dir_fd=fd, follow_symlinks=False)):
                    raise ValueError("symlink changed during inspection")
                entry.update(type="symlink", target=target)
                entries.append(entry)
            else:
                raise ValueError("special files cannot be verified by the file-tree checker")
            if len(entries) > max_entries:
                raise ValueError("tree exceeds entry budget")
        if fingerprint(before_dir) != fingerprint(os.fstat(fd)):
            raise ValueError("directory changed during inspection")

    try:
        visit(root_fd, "", 0)
        if not entries:
            raise ValueError("empty trees cannot establish backup coverage")
        # Anchor the supplied pathname as well as all opened children.
        check_fd = directory_fd(root)
        try:
            if fingerprint(root_info) != fingerprint(os.fstat(check_fd)):
                raise ValueError("tree root changed during inspection")
        finally:
            os.close(check_fd)
    finally:
        os.close(root_fd)
    result = {"entries": sorted(entries, key=lambda entry: entry["path"]), "bytes": byte_count,
              "root_identity": {"device": root_info.st_dev, "inode": root_info.st_ino}}
    if scope == "internal-files":
        result["root_metadata"] = {"mode": stat.S_IMODE(root_info.st_mode),
                                   "uid": root_info.st_uid, "gid": root_info.st_gid}
    return result


def differences(expected, observed):
    before = {entry["path"]: entry for entry in expected}
    after = {entry["path"]: entry for entry in observed}
    return [{"path": name, "status": "missing" if name not in after else
             "unlisted" if name not in before else "changed"}
            for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)]


def tree_differences(expected, observed, scope):
    delta = differences(expected["entries"], observed["entries"])
    if scope == "internal-files" and expected["root_metadata"] != observed["root_metadata"]:
        delta.insert(0, {"path": ".", "status": "metadata_changed"})
    return delta


def independent_roots(*roots):
    paths = [clean_path(root) for root in roots]
    identities = []
    for path in paths:
        fd = directory_fd(path)
        try:
            info = os.fstat(fd)
            identities.append((info.st_dev, info.st_ino))
        finally:
            os.close(fd)
    for i, path in enumerate(paths):
        for j in range(i):
            other = paths[j]
            if path == other or path in other.parents or other in path.parents or identities[i] == identities[j]:
                raise ValueError("source, backup and restored trees must be separate and nonoverlapping")
    return paths


@contextmanager
def anchored_roots(*roots):
    """Retain each original root and recheck every supplied path after the batch."""
    paths = independent_roots(*roots)
    fds = []
    try:
        for path in paths:
            fds.append(directory_fd(path))
        before = [os.fstat(fd) for fd in fds]
        identities = [(info.st_dev, info.st_ino) for info in before]
        if len(set(identities)) != len(identities):
            raise ValueError("inspected root identities alias one another")
        yield paths
        for path, initial, retained in zip(paths, before, fds):
            check_fd = directory_fd(path)
            try:
                if (fingerprint(initial) != fingerprint(os.fstat(check_fd))
                        or fingerprint(initial) != fingerprint(os.fstat(retained))):
                    raise ValueError("an inspected root changed across the scan batch")
            finally:
                os.close(check_fd)
    finally:
        for fd in fds:
            os.close(fd)


def record(source, backup, scope):
    with anchored_roots(source, backup) as (source, backup):
        original, copied = scan_tree(source, scope), scan_tree(backup, scope)
        if original["root_identity"] == copied["root_identity"]:
            raise ValueError("source and backup observations alias one another")
        delta = tree_differences(original, copied, scope)
    return {"kind": "tg5040-offline-backup-manifest", "schema": 1, "scope": scope,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_tree": original, "backup_tree_identity": copied["root_identity"],
            "source_backup_match": not delta, "differences": delta,
            "inventory_sha256": hashlib.sha256(encoded(original["entries"])).hexdigest(),
            "physical_restore_tested": False, "hardware_qualified": False,
            "automatic_activation": False, "independent_media_verified": False,
            "review_required": True}


def load_manifest(path):
    path = clean_path(path)
    parent = directory_fd(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_MANIFEST:
                raise ValueError("manifest must be a bounded regular file")
            data = stream.read(MAX_MANIFEST + 1)
            if len(data) != before.st_size or fingerprint(before) != fingerprint(os.fstat(stream.fileno())):
                raise ValueError("manifest changed while reading")
    finally:
        os.close(parent)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate manifest JSON key")
            result[key] = value
        return result

    manifest = json.loads(data, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    if (not isinstance(manifest, dict) or manifest.get("schema") != 1
            or type(manifest.get("schema")) is not int
            or manifest.get("kind") != "tg5040-offline-backup-manifest"
            or manifest.get("scope") not in SCOPES or manifest.get("source_backup_match") is not True
            or manifest.get("hardware_qualified") is not False
            or manifest.get("automatic_activation") is not False
            or manifest.get("physical_restore_tested") is not False):
        raise ValueError("not a successful unqualified backup manifest")
    tree = manifest.get("source_tree")
    entries = tree.get("entries") if isinstance(tree, dict) else None
    if not isinstance(entries, list) or not 0 < len(entries) <= MAX_ENTRIES:
        raise ValueError("invalid manifest entry list")
    if manifest["scope"] == "internal-files":
        metadata = tree.get("root_metadata")
        if (not isinstance(metadata, dict) or set(metadata) != {"mode", "uid", "gid"}
                or any(type(metadata[key]) is not int or metadata[key] < 0 for key in metadata)
                or metadata["mode"] > 0o7777):
            raise ValueError("invalid internal root metadata")
    names, byte_count = set(), 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("invalid manifest entry")
        name = relative_name(entry.get("path"))
        if name in names:
            raise ValueError("duplicate manifest path")
        names.add(name)
        kind = entry.get("type")
        fields = {"path", "type"}
        if manifest["scope"] == "internal-files":
            fields.update(("mode", "uid", "gid"))
            if any(type(entry.get(key)) is not int or entry[key] < 0 for key in ("mode", "uid", "gid")):
                raise ValueError("invalid internal metadata")
            if entry["mode"] > 0o7777:
                raise ValueError("invalid internal mode")
        if kind == "file":
            fields.update(("size", "sha256"))
            if type(entry.get("size")) is not int or entry["size"] < 0:
                raise ValueError("invalid file size")
            byte_count += entry["size"]
            if not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
                raise ValueError("invalid file digest")
        elif kind == "symlink":
            fields.add("target")
            target = entry.get("target")
            if (not isinstance(target, str) or not target or len(os.fsencode(target)) > 4096
                    or any(ord(c) < 32 or ord(c) == 127 for c in target)):
                raise ValueError("invalid symlink target")
        elif kind != "directory":
            raise ValueError("invalid manifest entry type")
        if set(entry) != fields:
            raise ValueError("unexpected manifest entry fields")
    if (byte_count > MAX_BYTES or tree.get("bytes") != byte_count
            or manifest.get("inventory_sha256") != hashlib.sha256(encoded(entries)).hexdigest()):
        raise ValueError("manifest inventory checksum or byte count mismatch")
    return manifest, hashlib.sha256(data).hexdigest()


def verify(manifest_path, backup, restored=None):
    manifest, manifest_digest = load_manifest(manifest_path)
    reports = {}
    requested = (backup, restored) if restored is not None else (backup,)
    with anchored_roots(*requested) as roots:
        observed_identities = []
        for name, root in zip(("retained_backup", "restored_tree"), roots):
            observed = scan_tree(root, manifest["scope"])
            if observed["root_identity"] in observed_identities:
                raise ValueError("backup and restored observations alias one another")
            observed_identities.append(observed["root_identity"])
            delta = tree_differences(manifest["source_tree"], observed, manifest["scope"])
            reports[name] = {"matches_recorded_source": not delta, "differences": delta,
                             "root_identity": observed["root_identity"], "bytes": observed["bytes"]}
    return {"kind": "tg5040-offline-backup-readback", "schema": 1,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "manifest_sha256": manifest_digest, "scope": manifest["scope"], "trees": reports,
            "all_trees_match": all(row["matches_recorded_source"] for row in reports.values()),
            "physical_restore_tested": False, "hardware_qualified": False,
            "automatic_activation": False, "independent_media_verified": False, "review_required": True}


def write_report(path, report, roots):
    path = clean_path(path)
    # All output is explicit, exclusive and outside every inspected input tree.
    if any(path == root or root in path.parents for root in map(clean_path, roots)):
        raise ValueError("report must be outside inspected trees")
    raw = encoded(report)
    if len(raw) > MAX_MANIFEST:
        raise ValueError("report exceeds its byte budget")
    parent = directory_fd(path.parent)
    staged = ".recovery-preflight-" + secrets.token_hex(16) + ".tmp"
    owned = None

    def remove_owned(name):
        try:
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if owned == (info.st_dev, info.st_ino):
                os.unlink(name, dir_fd=parent)
        except FileNotFoundError:
            pass

    try:
        fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            info = os.fstat(stream.fileno())
            owned = (info.st_dev, info.st_ino)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # link() publishes complete fsynced bytes atomically and refuses an
        # existing target; unlike replace(), it cannot clobber an older receipt.
        os.link(staged, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        remove_owned(staged)
        os.fsync(parent)
    except BaseException:
        if owned is not None:
            remove_owned(staged)
            remove_owned(path.name)
        raise
    finally:
        os.close(parent)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    recording = commands.add_parser("record", help="compare a stopped source tree to a separately made backup")
    recording.add_argument("--source", type=Path, required=True)
    recording.add_argument("--backup", type=Path, required=True)
    recording.add_argument("--scope", choices=SCOPES, required=True)
    checking = commands.add_parser("verify", help="rehash retained backup and optional manually restored spare tree")
    checking.add_argument("--manifest", type=Path, required=True)
    checking.add_argument("--backup", type=Path, required=True)
    checking.add_argument("--restored", type=Path)
    for command in (recording, checking):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            report = record(args.source, args.backup, args.scope)
            roots, success = (args.source, args.backup), report["source_backup_match"]
        else:
            report = verify(args.manifest, args.backup, args.restored)
            roots = (args.backup,) + ((args.restored,) if args.restored is not None else ())
            success = report["all_trees_match"]
        write_report(args.output, report, roots)
        print(str(args.output))
        return 0 if success else 1
    except (OSError, ValueError, UnicodeError) as exc:
        print("recovery-preflight: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
