#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Copy stopped trees into new private payloads and new expendable rehearsals.

Never overwrite, delete, mount, execute or flash. Reports are consistency
observations, not physical recovery, independent-media or activation authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

if __package__:
    from . import recovery_preflight as verifier
else:
    import recovery_preflight as verifier

MAX_RECORD = 64 * 1024
FALSE_FLAGS = {"physical_restore_tested": False, "hardware_qualified": False,
               "automatic_activation": False, "independent_media_verified": False}
PAYLOAD_NAMES = {"data", "INCOMPLETE.json", "manifest.json", "readback.json", "COMPLETE.json"}


def identity(info):
    return info.st_dev, info.st_ino


def same_root(path, fd):
    current = verifier.directory_fd(path)
    try:
        if identity(os.fstat(fd)) != identity(os.fstat(current)):
            raise ValueError("output root pathname changed")
    finally:
        os.close(current)


def new_directory(parent_fd, name):
    """Create/capture a private empty inode before any mutation through its fd.

    The parent must be trusted against same-owner replacement before the first
    stat: POSIX mkdir has no atomic create-and-open directory primitive. Checks
    below refuse a later pathname swap instead of adopting its opened inode.
    """
    verifier.relative_name(name)
    if "/" in name:
        raise ValueError("new directory requires one leaf name")
    os.mkdir(name, 0o700, dir_fd=parent_fd)
    created = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (not stat.S_ISDIR(created.st_mode) or created.st_uid != os.geteuid() or
            stat.S_IMODE(created.st_mode) != 0o700):
        raise ValueError("new directory capture is not the expected private owned inode")
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
    try:
        opened = os.fstat(fd)
        if verifier.fingerprint(created) != verifier.fingerprint(opened):
            raise ValueError("new directory was replaced before opening")
        if os.listdir(fd):
            raise ValueError("new directory is no longer empty")
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if verifier.fingerprint(opened) != verifier.fingerprint(named):
            raise ValueError("new directory pathname changed before first use")
        return fd
    except BaseException:
        os.close(fd)
        raise


def write_all(fd, raw):
    pending = memoryview(raw)
    while pending:
        count = os.write(fd, pending)
        if count <= 0:
            raise OSError("copy write made no progress")
        pending = pending[count:]


def publish(root_fd, name, value):
    """Exclusive, durable new record; partial files remain for review on error."""
    if name not in {"INCOMPLETE.json", "manifest.json", "readback.json", "rehearsal.json", "COMPLETE.json", "FAILED.json"}:
        raise ValueError("unknown fixed record name")
    raw = verifier.encoded(value)
    if len(raw) > verifier.MAX_MANIFEST:
        raise ValueError("record exceeds byte budget")
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=root_fd)
    try:
        write_all(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(root_fd)
    return hashlib.sha256(raw).hexdigest()


def reject_xattrs(fd):
    # Never silently flatten ACLs/capabilities or other extended metadata.
    if not callable(getattr(os, "listxattr", None)):
        raise ValueError("extended metadata inspection is unavailable")
    try:
        values = os.listxattr(fd)
    except OSError as exc:
        if exc.errno not in {errno.ENOTSUP, errno.EOPNOTSUPP}:
            raise
        values = []
    if values:
        raise ValueError("extended attributes require a separately reviewed archive/image procedure")


def open_directory(root_fd, relative, expected=None):
    fd = os.dup(root_fd)
    prefix = []
    try:
        for part in relative.split("/") if relative else ():
            verifier.relative_name(part)
            prefix.append(part)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=fd)
            os.close(fd)
            fd = child
            if expected is not None and identity(os.fstat(fd)) != expected["/".join(prefix)]:
                raise ValueError("copied directory pathname changed")
        return fd
    except BaseException:
        os.close(fd)
        raise


def metadata(fd, expected, scope):
    if scope == "internal-files":
        current = os.fstat(fd)
        if (current.st_uid, current.st_gid) != (expected["uid"], expected["gid"]):
            os.fchown(fd, expected["uid"], expected["gid"])
        os.fchmod(fd, expected["mode"])
        current = os.fstat(fd)
        if (stat.S_IMODE(current.st_mode), current.st_uid, current.st_gid) != (
                expected["mode"], expected["uid"], expected["gid"]):
            raise ValueError("internal metadata was not preserved")


def supported_tree(tree):
    if any(entry["type"] not in {"file", "directory"} for entry in tree["entries"]):
        raise ValueError("symlinks require a separately reviewed archive/image procedure")


def copy_tree(source, destination, scope, expected, *, max_entries, max_bytes,
              expected_source_identity=None, expected_destination_identity=None):
    """Copy from anchored descriptors, with per-file and whole-tree checks."""
    supported_tree(expected)
    source_fd = verifier.directory_fd(source)
    destination_fd = None
    try:
        destination_fd = verifier.directory_fd(destination)
        owned_dirs = {"": identity(os.fstat(destination_fd))}
        if expected_source_identity is not None and identity(os.fstat(source_fd)) != (
                expected_source_identity["device"], expected_source_identity["inode"]):
            raise ValueError("source root changed since the initial inventory")
        if expected_destination_identity is not None and identity(os.fstat(destination_fd)) != expected_destination_identity:
            raise ValueError("new destination root changed before copying")
        reject_xattrs(source_fd)
        for entry in sorted(expected["entries"], key=lambda row: (row["path"].count("/"), row["path"])):
            relative = verifier.relative_name(entry["path"])
            parent_name, _, leaf = relative.rpartition("/")
            parent_source = open_directory(source_fd, parent_name)
            parent_target = None
            try:
                parent_target = open_directory(destination_fd, parent_name, owned_dirs)
                before_name = os.stat(leaf, dir_fd=parent_source, follow_symlinks=False)
                if entry["type"] == "directory":
                    if not stat.S_ISDIR(before_name.st_mode):
                        raise ValueError("source directory changed type")
                    source_child = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                           dir_fd=parent_source)
                    try:
                        if verifier.fingerprint(before_name) != verifier.fingerprint(os.fstat(source_child)):
                            raise ValueError("source directory changed before copy")
                        reject_xattrs(source_child)
                    finally:
                        os.close(source_child)
                    child = new_directory(parent_target, leaf)
                    try:
                        owned_dirs[relative] = identity(os.fstat(child))
                        os.fsync(child)
                    finally:
                        os.close(child)
                    os.fsync(parent_target)
                    continue
                source_file = os.open(leaf, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                                      dir_fd=parent_source)
                try:
                    before = os.fstat(source_file)
                    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                            verifier.fingerprint(before_name) != verifier.fingerprint(before) or
                            before.st_size != entry["size"]):
                        raise ValueError("source file changed or has unsupported links")
                    reject_xattrs(source_file)
                    target_file = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                          0o600, dir_fd=parent_target)
                    try:
                        target_identity = identity(os.fstat(target_file))
                        digest, remaining = hashlib.sha256(), entry["size"]
                        while remaining:
                            block = os.read(source_file, min(1024 * 1024, remaining))
                            if not block:
                                raise ValueError("source file shortened during copy")
                            write_all(target_file, block)
                            digest.update(block)
                            remaining -= len(block)
                        if os.read(source_file, 1) or digest.hexdigest() != entry["sha256"]:
                            raise ValueError("source file changed during copy")
                        if (verifier.fingerprint(before) != verifier.fingerprint(os.fstat(source_file)) or
                                verifier.fingerprint(before) != verifier.fingerprint(os.stat(leaf, dir_fd=parent_source, follow_symlinks=False))):
                            raise ValueError("source file identity changed during copy")
                        metadata(target_file, entry, scope)
                        os.fsync(target_file)
                        if identity(os.stat(leaf, dir_fd=parent_target, follow_symlinks=False)) != target_identity:
                            raise ValueError("copied file pathname changed")
                    finally:
                        os.close(target_file)
                    os.fsync(parent_target)
                finally:
                    os.close(source_file)
            finally:
                os.close(parent_source)
                if parent_target is not None:
                    os.close(parent_target)
        # Directories stay traversable throughout copying, then receive exact
        # internal metadata bottom-up, including the selected source root.
        for entry in sorted((row for row in expected["entries"] if row["type"] == "directory"),
                            key=lambda row: (-row["path"].count("/"), row["path"]), reverse=False):
            fd = open_directory(destination_fd, entry["path"], owned_dirs)
            try:
                metadata(fd, entry, scope)
                os.fsync(fd)
            finally:
                os.close(fd)
        metadata(destination_fd, expected.get("root_metadata", {}), scope)
        os.fsync(destination_fd)
        same_root(source, source_fd)
        same_root(destination, destination_fd)
    finally:
        os.close(source_fd)
        if destination_fd is not None:
            os.close(destination_fd)
    source_after = verifier.scan_tree(source, scope, max_entries=max_entries, max_bytes=max_bytes)
    if verifier.tree_differences(expected, source_after, scope):
        raise ValueError("source contents or scoped metadata changed across copy")
    copied = verifier.scan_tree(destination, scope, max_entries=max_entries, max_bytes=max_bytes)
    if verifier.tree_differences(expected, copied, scope):
        raise ValueError("copied contents or scoped metadata failed readback")


def check_supported_metadata(root, expected, *, expected_root_identity=None, progress=None):
    """Recheck unsupported metadata that the content manifest cannot encode."""
    supported_tree(expected)
    root_fd = verifier.directory_fd(root)
    try:
        root_before = os.fstat(root_fd)
        if expected_root_identity is not None and identity(root_before) != expected_root_identity:
            raise ValueError("metadata inspection root changed since capture")
        reject_xattrs(root_fd)
        for entry in expected["entries"]:
            if progress is not None:
                progress("metadata", 0, 0)
            relative = verifier.relative_name(entry["path"])
            parent_name, _, leaf = relative.rpartition("/")
            parent = open_directory(root_fd, parent_name)
            try:
                before = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
                if entry["type"] == "directory":
                    flags |= os.O_DIRECTORY
                fd = os.open(leaf, flags, dir_fd=parent)
                try:
                    opened = os.fstat(fd)
                    if (verifier.fingerprint(before) != verifier.fingerprint(opened) or
                            (entry["type"] == "file" and (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1)) or
                            (entry["type"] == "directory" and not stat.S_ISDIR(opened.st_mode))):
                        raise ValueError("unsupported or changed metadata entry")
                    reject_xattrs(fd)
                    if (verifier.fingerprint(opened) != verifier.fingerprint(os.fstat(fd)) or
                            verifier.fingerprint(opened) != verifier.fingerprint(os.stat(leaf, dir_fd=parent, follow_symlinks=False))):
                        raise ValueError("metadata entry changed across final inspection")
                finally:
                    os.close(fd)
            finally:
                os.close(parent)
        reject_xattrs(root_fd)
        if verifier.fingerprint(root_before) != verifier.fingerprint(os.fstat(root_fd)):
            raise ValueError("root metadata changed across final inspection")
        same_root(root, root_fd)
    finally:
        os.close(root_fd)


def create_output(source, output):
    source, output = verifier.clean_path(source), verifier.clean_path(output)
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("new output must be separate and nonoverlapping")
    parent_fd = verifier.directory_fd(output.parent)
    try:
        source_fd = verifier.directory_fd(source)
        try:
            source_id = identity(os.fstat(source_fd))
            ancestor = os.dup(parent_fd)
            try:
                for _ in range(1024):
                    if identity(os.fstat(ancestor)) == source_id:
                        raise ValueError("output parent aliases the source tree")
                    above = os.open("..", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=ancestor)
                    if identity(os.fstat(above)) == identity(os.fstat(ancestor)):
                        os.close(above)
                        break
                    os.close(ancestor)
                    ancestor = above
                else:
                    raise ValueError("output ancestry exceeded its inspection budget")
            finally:
                os.close(ancestor)
        finally:
            os.close(source_fd)
        fd = new_directory(parent_fd, output.name)
        try:
            os.fsync(fd)
            os.fsync(parent_fd)
            same_root(output, fd)
            return output, fd
        except BaseException:
            os.close(fd)
            raise
    finally:
        os.close(parent_fd)


def failure(root_fd, action, scope, exc):
    try:
        publish(root_fd, "FAILED.json", {"schema": 1, "kind": "recovery-payload-failed", "action": action,
                                       "scope": scope, "reason": type(exc).__name__, **FALSE_FLAGS})
    except BaseException:
        # Never overwrite/delete anything to hide the original failure.
        pass


def _intent(action, scope):
    return {"schema": 1, "kind": "recovery-payload-intent", "action": action, "scope": scope,
            "state": "incomplete-until-successful-operation-and-fresh-completion-review",
            "started_at_utc": datetime.now(timezone.utc).isoformat(), **FALSE_FLAGS,
            "review_required": True}


def backup(source, output, scope, *, max_entries=verifier.MAX_ENTRIES, max_bytes=verifier.MAX_BYTES):
    source = verifier.clean_path(source)
    original = verifier.scan_tree(source, scope, max_entries=max_entries, max_bytes=max_bytes)
    supported_tree(original)
    output, output_fd = create_output(source, output)
    try:
        publish(output_fd, "INCOMPLETE.json", _intent("backup", scope))
        data_fd = new_directory(output_fd, "data")
        try:
            data_identity = identity(os.fstat(data_fd))
            os.fsync(data_fd)
        finally:
            os.close(data_fd)
        os.fsync(output_fd)
        data = output / "data"
        verifier.independent_roots(source, data)
        with verifier.anchored_roots(source):
            copy_tree(source, data, scope, original, max_entries=max_entries, max_bytes=max_bytes,
                      expected_source_identity=original["root_identity"],
                      expected_destination_identity=data_identity)
            same_root(output, output_fd)
            check_supported_metadata(source, original, expected_root_identity=tuple(original["root_identity"][name] for name in ("device", "inode")))
            check_supported_metadata(data, original, expected_root_identity=data_identity)
            manifest = verifier.record(source, data, scope)
            if not manifest["source_backup_match"]:
                raise ValueError("source and retained payload differ")
            manifest_sha = publish(output_fd, "manifest.json", manifest)
            same_root(output, output_fd)
            readback = verifier.verify(output / "manifest.json", data)
            if not readback["all_trees_match"]:
                raise ValueError("retained payload failed independent readback")
            check_supported_metadata(source, original, expected_root_identity=tuple(original["root_identity"][name] for name in ("device", "inode")))
            check_supported_metadata(data, original, expected_root_identity=data_identity)
            readback_sha = publish(output_fd, "readback.json", readback)
        same_root(output, output_fd)
        complete = {"schema": 1, "kind": "recovery-payload-complete", "action": "backup", "scope": scope,
                    "manifest_sha256": manifest_sha, "readback_sha256": readback_sha,
                    "inventory_sha256": manifest["inventory_sha256"], "bytes": original["bytes"],
                    "completed_at_utc": datetime.now(timezone.utc).isoformat(), **FALSE_FLAGS,
                    "review_required": True}
        publish(output_fd, "COMPLETE.json", complete)
        same_root(output, output_fd)
        return complete
    except BaseException as exc:
        failure(output_fd, "backup", scope, exc)
        raise
    finally:
        os.close(output_fd)


def read_record(root_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= MAX_RECORD:
            raise ValueError("payload record is not a bounded single regular file")
        raw = os.read(fd, MAX_RECORD + 1)
        if len(raw) != before.st_size or verifier.fingerprint(before) != verifier.fingerprint(os.fstat(fd)):
            raise ValueError("payload record changed during reading")
        if verifier.fingerprint(before) != verifier.fingerprint(os.stat(name, dir_fd=root_fd, follow_symlinks=False)):
            raise ValueError("payload record pathname changed")
    finally:
        os.close(fd)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate payload record key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite payload record")))
    except (RecursionError, UnicodeError) as error:
        raise ValueError("payload record exceeds JSON nesting or encoding limits") from error
    return value, hashlib.sha256(raw).hexdigest()


def inspect_payload(payload, *, progress=None):
    if progress is not None:
        progress("manifest", 0, 0)
    payload = verifier.clean_path(payload)
    root_fd = verifier.directory_fd(payload)
    try:
        root_info = os.fstat(root_fd)
        if stat.S_IMODE(root_info.st_mode) & 0o077:
            raise ValueError("retained payload container is not private")
        if set(os.listdir(root_fd)) != PAYLOAD_NAMES:
            raise ValueError("payload is incomplete, failed or has unreviewed extra entries")
        intent, _ = read_record(root_fd, "INCOMPLETE.json")
        complete, complete_sha = read_record(root_fd, "COMPLETE.json")
        readback, readback_sha = read_record(root_fd, "readback.json")
        if (not isinstance(complete, dict) or complete.get("schema") != 1 or
                complete.get("kind") != "recovery-payload-complete" or complete.get("action") != "backup" or
                complete.get("scope") not in verifier.SCOPES or
                any(complete.get(name) is not value for name, value in FALSE_FLAGS.items()) or
                not isinstance(intent, dict) or intent.get("action") != "backup" or intent.get("scope") != complete["scope"]):
            raise ValueError("invalid unqualified payload completion")
        manifest_info = os.stat("manifest.json", dir_fd=root_fd, follow_symlinks=False)
        if not stat.S_ISREG(manifest_info.st_mode) or manifest_info.st_nlink != 1:
            raise ValueError("payload manifest must be a single regular file")
        manifest, manifest_sha = verifier.load_manifest(payload / "manifest.json")
        supported_tree(manifest["source_tree"])
        if (complete.get("manifest_sha256") != manifest_sha or complete.get("readback_sha256") != readback_sha or
                complete.get("scope") != manifest["scope"] or complete.get("inventory_sha256") != manifest["inventory_sha256"] or
                complete.get("bytes") != manifest["source_tree"]["bytes"] or
                not isinstance(readback, dict) or readback.get("all_trees_match") is not True or
                readback.get("manifest_sha256") != manifest_sha):
            raise ValueError("payload completion does not bind its manifest/readback")
        same_root(payload, root_fd)
        check_supported_metadata(payload / "data", manifest["source_tree"], **({"progress": progress} if progress is not None else {}))
        fresh = verifier.verify(payload / "manifest.json", payload / "data", **({"progress": progress} if progress is not None else {}))
        if not fresh["all_trees_match"]:
            raise ValueError("retained payload no longer matches its manifest")
        check_supported_metadata(payload / "data", manifest["source_tree"], **({"progress": progress} if progress is not None else {}))
        same_root(payload, root_fd)
        return manifest, {"complete_sha256": complete_sha, "manifest_sha256": manifest_sha,
                          "readback_sha256": readback_sha}, fresh
    finally:
        os.close(root_fd)


def restore(payload, output, *, max_entries=verifier.MAX_ENTRIES, max_bytes=verifier.MAX_BYTES):
    payload = verifier.clean_path(payload)
    manifest, inputs, _ = inspect_payload(payload)
    scope = manifest["scope"]
    # Enforce requested limits before creating any rehearsal output.
    observed = verifier.scan_tree(payload / "data", scope, max_entries=max_entries, max_bytes=max_bytes)
    if verifier.tree_differences(manifest["source_tree"], observed, scope):
        raise ValueError("retained payload changed before restore")
    output, output_fd = create_output(payload, output)
    try:
        publish(output_fd, "INCOMPLETE.json", _intent("restore-rehearsal", scope))
        data_fd = new_directory(output_fd, "data")
        try:
            data_identity = identity(os.fstat(data_fd))
            os.fsync(data_fd)
        finally:
            os.close(data_fd)
        os.fsync(output_fd)
        data = output / "data"
        verifier.independent_roots(payload / "data", data)
        with verifier.anchored_roots(payload):
            copy_tree(payload / "data", data, scope, manifest["source_tree"],
                      max_entries=max_entries, max_bytes=max_bytes,
                      expected_source_identity=observed["root_identity"],
                      expected_destination_identity=data_identity)
            same_root(output, output_fd)
            after_manifest, after_inputs, _ = inspect_payload(payload)
            if inputs != after_inputs or after_manifest != manifest:
                raise ValueError("retained manifest/completion changed during rehearsal")
            rehearsal = verifier.verify(payload / "manifest.json", payload / "data", data)
            if not rehearsal["all_trees_match"]:
                raise ValueError("restored rehearsal failed fresh readback")
            check_supported_metadata(data, manifest["source_tree"], expected_root_identity=data_identity)
            rehearsal_sha = publish(output_fd, "rehearsal.json", rehearsal)
        same_root(output, output_fd)
        complete = {"schema": 1, "kind": "recovery-rehearsal-complete", "action": "restore-rehearsal", "scope": scope,
                    "inputs": inputs, "rehearsal_sha256": rehearsal_sha,
                    "bytes": manifest["source_tree"]["bytes"],
                    "completed_at_utc": datetime.now(timezone.utc).isoformat(), **FALSE_FLAGS,
                    "review_required": True}
        publish(output_fd, "COMPLETE.json", complete)
        same_root(output, output_fd)
        return complete
    except BaseException as exc:
        failure(output_fd, "restore-rehearsal", scope, exc)
        raise
    finally:
        os.close(output_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    copying = commands.add_parser("backup", help="copy a stopped tree to a new exclusive private payload")
    copying.add_argument("--source", type=Path, required=True)
    copying.add_argument("--scope", choices=verifier.SCOPES, required=True)
    restoring = commands.add_parser("restore", help="rehearse restoration into a NEW expendable directory")
    restoring.add_argument("--payload", type=Path, required=True)
    for command in (copying, restoring):
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--max-entries", type=int, default=verifier.MAX_ENTRIES)
        command.add_argument("--max-bytes", type=int, default=verifier.MAX_BYTES)
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            backup(args.source, args.output, args.scope, max_entries=args.max_entries, max_bytes=args.max_bytes)
        else:
            restore(args.payload, args.output, max_entries=args.max_entries, max_bytes=args.max_bytes)
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print("recovery payload refused; new partial output retained for review: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
