#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare locally supplied upstream revisions without fetching or updating pins.

This is an engineering review queue, not an update installer or qualification
decision. Git object identities include modes and submodule references. No source
from the proposed revision is imported, built or executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from dev.certify import source_specs
from tools.recovery_preflight import directory_fd

MAX_TREE = 16 * 1024 * 1024
MAX_ENTRIES = 100000
MAX_MATERIALIZED_BYTES = 512 * 1024 * 1024
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SCOPES = {
    "SPRUCE_SOURCE_ROOT": (
        "App/PyUI/", "spruce/scripts/", "App/-OTA/downloader.sh",
        "App/USBStorageMode/launch.sh", "RetroArch/igm/", ".tmp_update/updater",
        "trimui/app/", "LICENSE", ".gitmodules",
    ),
    "PPSSPP_SOURCE_ROOT": (
        "Core/", "Common/", "SDL/", "UI/", "assets/themes/", "LICENSE.TXT", ".gitmodules",
    ),
    "SPRUCE_RA_SOURCE_ROOT": (
        "patches/", "common_src/", "build.sh", "LICENSE", "COPYING", ".gitmodules",
    ),
    "PORTS_SOURCE_ROOT": ("ports/celeste/", "LICENSE", "COPYING", ".gitmodules"),
    "PORTMASTER_SOURCE_ROOT": (
        "PortMaster/pylibs/harbourmaster/", "PortMaster/device_info.txt",
        "PortMaster/control.txt", "PortMaster/funcs.txt", "LICENSE", ".gitmodules",
    ),
}


def _git(root, *args):
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
         "-C", str(root), *args],
        check=True, capture_output=True, timeout=30,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0",
             "GIT_NO_REPLACE_OBJECTS": "1"},
    )
    if len(result.stdout) > MAX_TREE:
        raise ValueError("Git metadata exceeds the review bound")
    return result.stdout


def tree(root, commit):
    """Read committed metadata only, including added files and gitlinks."""
    if not isinstance(commit, str) or not SHA1.fullmatch(commit):
        raise ValueError("Expected an exact SHA-1 commit, not a moving revision")
    raw = _git(root, "ls-tree", "-r", "-z", "--full-tree", commit)
    records = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        if len(records) >= MAX_ENTRIES:
            raise ValueError("Git tree exceeds the entry bound")
        metadata, name = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        name = name.decode("utf-8")
        if (not name or name.startswith("/") or any(x in ("", ".", "..") for x in name.split("/"))
                or len(name) > 2048 or name in records or not SHA1.fullmatch(object_id)):
            raise ValueError("Invalid or duplicate upstream path/object identity")
        if (mode, kind) not in {("100644", "blob"), ("100755", "blob"),
                                ("120000", "blob"), ("160000", "commit")}:
            raise ValueError("Unsupported upstream file mode")
        records[name] = {"mode": mode, "kind": kind, "git_object": object_id}
    return records


def in_scope(name, scopes):
    return any(name.startswith(scope) if scope.endswith("/") else name == scope for scope in scopes)


def _worktree_blob(root_fd, name, mode, budget):
    """Read a materialized blob without filters, symlink traversal or lazy fetch."""
    parts = name.split("/")
    parent = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if mode == "120000":
            if not stat.S_ISLNK(info.st_mode):
                raise ValueError("Materialized source file type differs")
            raw = os.fsencode(os.readlink(parts[-1], dir_fd=parent))
        else:
            if (not stat.S_ISREG(info.st_mode) or bool(info.st_mode & 0o111) != (mode == "100755") or
                    info.st_size > budget):
                raise ValueError("Materialized source file type, mode or size differs")
            descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                before = os.fstat(descriptor)
                if (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino):
                    raise ValueError("Materialized source file changed")
                data = bytearray()
                while len(data) <= info.st_size:
                    block = os.read(descriptor, min(65536, info.st_size + 1 - len(data)))
                    if not block:
                        break
                    data.extend(block)
                after = os.fstat(descriptor)
                if (len(data) != info.st_size or any(getattr(info, key) != getattr(after, key)
                        for key in ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns"))):
                    raise ValueError("Materialized source file changed")
                raw = bytes(data)
            finally:
                os.close(descriptor)
        anchored = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if any(getattr(info, key) != getattr(anchored, key)
               for key in ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")):
            raise ValueError("Materialized source file changed")
        return raw
    except FileNotFoundError:
        return None  # sparse checkout omission; required files are checked below
    finally:
        os.close(parent)


def verify_checkout(root, expected_commit, required_files, subtree=None):
    """Check raw bytes and index metadata without invoking worktree filters.

    `git diff` can execute clean filters or fsmonitor configured in a proposed
    checkout. This verifier needs neither diff nor arbitrary repository code.
    """
    root = Path(root).absolute()
    if Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()) != root:
        raise ValueError("Source root must be the Git checkout root")
    if _git(root, "rev-parse", "HEAD").decode().strip() != expected_commit:
        raise ValueError("Source commit differs from the exact pin")
    committed = tree(root, expected_commit)
    index, sparse = {}, set()
    for entry in _git(root, "ls-files", "--stage", "-t", "-z").split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        tag, mode, object_id, stage = metadata.decode("ascii").split()
        name = name.decode("utf-8")
        if stage != "0" or name in index:
            raise ValueError("Source checkout has unresolved or duplicate staged files")
        index[name] = (mode, object_id)
        if tag == "S":
            sparse.add(name)
    if index != {name: (item["mode"], item["git_object"]) for name, item in committed.items()}:
        raise ValueError("Source checkout has changed tracked index files")
    if _git(root, "ls-files", "--others", "--exclude-standard", "-z"):
        raise ValueError("Source checkout has untracked files")
    root_fd = directory_fd(root)
    checked, total, required_seen = 0, 0, set()
    try:
        identity = os.fstat(root_fd)
        for name, item in committed.items():
            if item["kind"] != "blob":
                continue  # submodule identity is compared; its code is not traversed
            raw = _worktree_blob(root_fd, name, item["mode"], MAX_MATERIALIZED_BYTES - total)
            if raw is None:
                if name not in sparse:
                    raise ValueError("Required tracked source is missing without a sparse index exclusion")
                continue
            observed = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            if observed != item["git_object"]:
                raise ValueError("Materialized source differs from Git HEAD (changed tracked bytes)")
            if name in required_files:
                if item["mode"] == "120000":
                    raise ValueError("Required source file must be regular")
                expected_hash = required_files[name]
                if expected_hash and hashlib.sha256(raw).hexdigest() != expected_hash:
                    raise ValueError("Required source file differs from its lock")
                required_seen.add(name)
            checked += 1
            total += len(raw)
        if required_seen != set(required_files):
            raise ValueError("Required source file is missing or not regular")
        if subtree:
            path, expected_tree = subtree
            if _git(root, "rev-parse", expected_commit + ":" + path).decode().strip() != expected_tree:
                raise ValueError("Pinned source subtree differs")
        current = directory_fd(root)
        try:
            after = os.fstat(current)
            if (identity.st_dev, identity.st_ino) != (after.st_dev, after.st_ino):
                raise ValueError("Source checkout root changed during review")
        finally:
            os.close(current)
    finally:
        os.close(root_fd)
    return {"materialized_files_checked": checked}


def review_areas(name):
    areas = {"source-contract", "host-regression"}
    lowered = name.casefold()
    if any(word in lowered for word in ("license", "licence", "copying", "notice", "copyright")):
        areas.add("rights-and-notices")
    if any(word in lowered for word in ("principal", "runtime", "boot", "updater", "launch", "device", "controller")):
        areas.add("device-lifecycle-and-recovery")
    if any(word in lowered for word in ("savestate", "save_state", "save", "config", "keymap", "control")):
        areas.add("save-config-and-controls")
    if name == ".gitmodules" or name.endswith(("CMakeLists.txt", "Makefile", "build.sh")):
        areas.add("dependencies-and-build")
    return sorted(areas)


def compare(baseline_root, candidate_root, expected_commit, scopes, *, required_files=None, subtree=None):
    """Verify clean inputs, compare metadata, then recheck both checkouts.

    Changed required input files are expected in a candidate; baseline files must
    satisfy their existing locks. Sparse exclusion is not interpreted as removal.
    """
    baseline_root, candidate_root = Path(baseline_root), Path(candidate_root)
    baseline = verify_checkout(baseline_root, expected_commit, required_files or {}, subtree)
    candidate_commit = _git(candidate_root, "rev-parse", "HEAD").decode("ascii").strip()
    candidate = verify_checkout(candidate_root, candidate_commit, {})
    before, after = tree(baseline_root, expected_commit), tree(candidate_root, candidate_commit)
    changes = []
    unchanged = excluded = 0
    for name in sorted(set(before) | set(after)):
        if before.get(name) == after.get(name):
            unchanged += int(in_scope(name, scopes))
            continue
        if not in_scope(name, scopes):
            excluded += 1
            continue
        changes.append({"path": name,
                        "change": "added" if name not in before else "removed" if name not in after else "modified",
                        "before": before.get(name), "after": after.get(name),
                        "review_areas": review_areas(name)})
    verify_checkout(baseline_root, expected_commit, required_files or {}, subtree)
    verify_checkout(candidate_root, candidate_commit, {})
    return {"schema": 1, "kind": "local-upstream-drift-review", "baseline_commit": expected_commit,
            "candidate_commit": candidate_commit, "baseline_materialized_files": baseline["materialized_files_checked"],
            "candidate_materialized_files": candidate["materialized_files_checked"],
            "scopes": list(scopes), "changes": changes, "changed_in_scope": len(changes),
            "unchanged_in_scope": unchanged, "changed_outside_scope": excluded,
            "review_required": bool(changes), "scope_expansion_review_required": excluded > 0,
            "pins_updated": False, "candidate_executed": False, "device_qualified": False,
            "distribution_cleared": False,
            "limitations": ["Metadata comparison cannot establish behavioral compatibility.",
                            "New transitive dependencies outside these scopes need a separate scope review.",
                            "A no-change result does not qualify an untested device or grant source-use rights."]}


def publish(output, report, roots):
    output = Path(output).absolute()
    # resolve(strict=True) on the parent prevents silent directory creation and
    # makes the no-write-inside-source rule apply through ancestor symlinks.
    parent = output.parent.resolve(strict=True)
    output = parent / output.name
    for root in roots:
        root = Path(root).resolve(strict=True)
        if output == root or root in output.parents:
            raise ValueError("Review output must stay outside both source checkouts")
    raw = (json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()
    directory = directory_fd(parent)
    try:
        descriptor = os.open(output.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)
        check = directory_fd(parent)
        try:
            current = os.fstat(check)
            original = os.fstat(directory)
            leaf = os.stat(output.name, dir_fd=check, follow_symlinks=False)
            if ((original.st_dev, original.st_ino) != (current.st_dev, current.st_ino) or
                    (leaf.st_dev, leaf.st_ino) != identity):
                raise ValueError("Review output changed during publication")
        finally:
            os.close(check)
    finally:
        # No portable unlink-if-inode-matches primitive exists. Retain uncertain
        # output on failure: a check followed by unlink could delete a concurrent
        # replacement. An exception never returns a successful receipt.
        os.close(directory)
    return {"report_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(SCOPES), required=True)
    parser.add_argument("--baseline-root", required=True)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        variable, lock, commit, files, subtree = next(item for item in source_specs() if item[0] == args.source)
        report = compare(args.baseline_root, args.candidate_root, commit, SCOPES[variable],
                         required_files=files, subtree=subtree)
        report.update({"source": variable, "lock": str(lock.relative_to(PROJECT.parent)),
                       "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest()})
        receipt = publish(args.output, report, (args.baseline_root, args.candidate_root))
        print(json.dumps({**receipt, "changed_in_scope": report["changed_in_scope"],
                          "changed_outside_scope": report["changed_outside_scope"],
                          "pins_updated": False, "device_qualified": False}))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("drift: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
