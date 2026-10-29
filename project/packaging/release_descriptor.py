# SPDX-License-Identifier: MIT
"""Resolve current preview selection and bind it to the source bytes being built."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import overlay

SOURCE_FOLDERS = {"psp_shell", "bridge", "integration", "profiles", "assets", "packaging", "tools", "tests", "docs", "dev", "ppsspp", "retropass", "vendor"}
SOURCE_ROOT_FILES = {"LICENSE", "README.md", "pyproject.toml", "requirements-dev.txt"}
SOURCE_EXTENSIONS = {".py", ".md", ".txt", ".json", ".toml", ".sh", ".ttf", ".png", ".svg", ".wav", ".ini"}
PAYLOAD_TOOLS = ("__init__.py", "recovery_payload.py", "recovery_preflight.py", "backup_catalog.py")
ORIGINAL_PAYLOAD = ["psp_shell", "bridge", "profiles", "ppsspp/theme", "assets",
                    *("tools/" + name for name in PAYLOAD_TOOLS)]


def original_source_scope(relative):
    relative = Path(relative)
    if not relative.parts:
        return False
    if relative.parts[0] not in SOURCE_FOLDERS and relative.as_posix() not in SOURCE_ROOT_FILES:
        return False
    if relative.parts[0] == "vendor":
        return len(relative.parts) > 2 and relative.parts[1] == "retropass" and not any(
            part in {"..", ".git", "__pycache__"} for part in relative.parts)
    if (relative.parts[0] == "ppsspp" and relative.as_posix() != "ppsspp/performance-source-lock.json"
            and (len(relative.parts) < 2 or relative.parts[1] != "theme")):
        return False
    return (not any(part in {"__pycache__", ".git", ".venv", "state", "transactions", "previews", "migrations", "fixtures"}
                    for part in relative.parts) and relative.name != "author-notification-draft.txt")


def original_source_file(relative):
    relative = Path(relative)
    return original_source_scope(relative) and (relative.parts[0] == "vendor" or relative.suffix.lower() in SOURCE_EXTENSIONS or
           relative.as_posix() in SOURCE_ROOT_FILES or relative.name == "LICENSE")


def source_inventory(entries):
    return [{"path": name.removeprefix("smartpro-original-source/"),
             "sha256": overlay.digest(data), "size": len(data)}
            for name, data in sorted(entries)]


def matches_committed_inventory(project, entries, source_lock, git, commit):
    """Compare captured bytes with one commit even when index flags hide edits."""
    repository = project.parent.resolve()
    try:
        lock_relative = Path(source_lock).resolve().relative_to(repository).as_posix()
    except ValueError:
        return False
    committed = {}
    for entry in git("ls-tree", "-rz", "--full-tree", commit, "--",
                     project.name, lock_relative).split("\0"):
        if not entry:
            continue
        metadata, name = entry.split("\t", 1)
        _, kind, object_id = metadata.split()
        if kind == "blob":
            committed[name] = object_id
    expected = {name for name in committed if name.startswith(project.name + "/") and
                original_source_file(name[len(project.name) + 1:])} | {lock_relative}
    consumed = set()
    for name, data in entries:
        relative = name.removeprefix("smartpro-original-source/")
        source = (lock_relative if relative == "metadata/spruce-source-lock.json" else
                  project.name + "/" + relative)
        consumed.add(source)
        object_id = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
        if committed.get(source) != object_id:
            return False
    return consumed == expected


def resolve(project, descriptor_path, entries, source_lock):
    project, descriptor_path = Path(project), Path(descriptor_path)
    captured = dict(entries)
    overlay.require(len(captured) == len(entries), "duplicate captured source path")
    try:
        descriptor_relative = descriptor_path.absolute().relative_to(project.absolute()).as_posix()
    except ValueError as exc:
        raise overlay.OverlayError("release descriptor must be included in original project source") from exc
    raw = captured.get("smartpro-original-source/" + descriptor_relative)
    overlay.require(raw is not None, "selected release descriptor missing from source inventory")
    descriptor = json.loads(raw)
    overlay.require(isinstance(descriptor, dict), "release descriptor must be an object")
    overlay.require(descriptor.get("schema") == 1, "unsupported release descriptor")
    overlay.identifier(descriptor.get("release_id"), "descriptor release id")
    overlay.require(descriptor.get("delivery") in {"original-only-host-preview", "retropass-host-preview"},
                    "development builder requires a supported host delivery")
    selected_third_party = descriptor.get("selected_third_party_payload", [])
    overlay.require(selected_third_party == (["retropass"] if descriptor["delivery"] == "retropass-host-preview" else []),
                    "descriptor third-party scope differs from supported RetroPass port")
    if selected_third_party:
        validate_retropass_vendor(project, captured)
    else:
        overlay.require(not any(name.startswith(("smartpro-original-source/retropass/",
                                                  "smartpro-original-source/vendor/retropass/")) for name in captured),
                        "legacy original-only descriptor cannot include RetroPass source")
    overlay.require(descriptor.get("frontend", {}).get("selection") == "repository-head-or-source-export",
                    "unsupported frontend revision selection")
    overlay.require(descriptor.get("base", {}).get("source_commit") == overlay.SPRUCE_COMMIT and
                    descriptor["base"].get("pyui_git_tree") == overlay.PYUI_TREE,
                    "release descriptor differs from the pinned spruce/PyUI baseline")
    overlay.require(type(descriptor.get("source_date_epoch")) is int,
                    "descriptor timestamp missing")
    overlay.require(descriptor.get("selected_upstream_patches") == [] and
                    descriptor.get("selected_native_binaries") == [],
                    "host preview cannot select upstream patches or native binaries")
    overlay.require(descriptor.get("selected_original_payload") == ORIGINAL_PAYLOAD,
        "release descriptor differs from the original payload builder scope")
    overlay.require(descriptor.get("qualification") == {
        "hardware_qualified": False, "runtime_verified": False, "source_use_verified": False},
        "preview descriptor cannot grant qualification")
    overlay.require(source_lock is not None, "current release requires the spruce source lock")
    lock_raw = captured.get("smartpro-original-source/metadata/spruce-source-lock.json")
    overlay.require(lock_raw is not None, "consumed source lock missing from source inventory")
    lock = json.loads(lock_raw)
    overlay.require(lock.get("base", {}).get("source_commit") == descriptor["base"]["source_commit"] and
                    lock["base"].get("pyui_git_tree") == descriptor["base"]["pyui_git_tree"],
                    "release descriptor/source lock mismatch")
    for candidate in descriptor.get("optional_native_references", []):
        overlay.require(candidate.get("selected") is False and candidate.get("device_qualified") is False,
                        "native reference cannot activate a preview feature")
        overlay.require(isinstance(candidate.get("sha256"), str) and
                        overlay.SHA256.fullmatch(candidate["sha256"]), "invalid native reference digest")
        overlay.require(isinstance(candidate.get("source_commit"), str) and
                        overlay.BASELINE.fullmatch(candidate["source_commit"]), "invalid native source revision")
    inventory = source_inventory(entries)
    digest = overlay.digest(overlay.canonical(inventory))
    descriptor_sha = overlay.digest(raw)
    exported = project / "metadata/release-source.json"
    # A source export retains the original Git identity; do not invent a revision
    # or attribute modified exported bytes to that original revision.
    if exported.is_file():
        snapshot = json.loads(exported.read_bytes())
        overlay.require(snapshot.get("schema") == 1 and
                        snapshot.get("descriptor_sha256") == descriptor_sha and
                        snapshot.get("source_inventory") == inventory and
                        snapshot.get("source_inventory_sha256") == digest,
                        "source export changed since its recorded release identity")
        frontend = snapshot["frontend"]
    else:
        try:
            def git(*arguments):
                return subprocess.check_output(["git", "-c", "core.fsmonitor=false", "-C", str(project),
                                                *arguments], stderr=subprocess.DEVNULL, text=True,
                                               env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"}).rstrip("\n")
            overlay.require(Path(git("rev-parse", "--show-toplevel")).resolve() == project.parent.resolve(),
                            "frontend must be the project's repository checkout")
            commit = git("rev-parse", "HEAD")
            overlay.require(overlay.BASELINE.fullmatch(commit), "invalid frontend Git revision")
            modified = bool(git("status", "--porcelain", "--untracked-files=all", "--", "."))
            frontend = {"commit": commit, "working_tree_modified": modified or not
                        matches_committed_inventory(project, entries, source_lock, git, commit)}
        except subprocess.SubprocessError as exc:
            raise overlay.OverlayError("frontend Git identity unavailable; use a verified original-source export") from exc
        snapshot = {"schema": 1, "descriptor_sha256": descriptor_sha, "frontend": frontend,
                    "source_inventory": inventory, "source_inventory_sha256": digest}
    overlay.require(isinstance(frontend, dict) and isinstance(frontend.get("commit"), str) and
                    overlay.BASELINE.fullmatch(frontend["commit"]) and
                    type(frontend.get("working_tree_modified")) is bool, "invalid frontend source identity")
    metadata = {"descriptor": descriptor, "descriptor_sha256": descriptor_sha,
                "frontend": frontend, "source_inventory_sha256": digest}
    return metadata, snapshot


def validate_retropass_vendor(project, captured=None):
    """Require the whole pinned, unmodified tree; reject omitted or extra blobs."""
    if captured is None:
        prefix = "smartpro-original-source/"
        captured = {}
        for path in (project / "vendor/retropass").rglob("*"):
            overlay.require(not path.is_symlink(), "RetroPass source symlinks are excluded")
            if path.is_file():
                captured[prefix + path.relative_to(project).as_posix()] = path.read_bytes()
        lock_raw = (project / "retropass/source-lock.json").read_bytes()
    else:
        lock_raw = captured.get("smartpro-original-source/retropass/source-lock.json")
    overlay.require(lock_raw is not None, "RetroPass source lock missing")
    lock = json.loads(lock_raw)
    overlay.require(lock.get("schema") == 1 and lock.get("commit") == "65fa22fadc3c88bf8353d093c6fa9b3fa3d92f83" and
                    lock.get("repository") == "https://github.com/retropassdev/RetroPass" and
                    lock.get("license") == "GPL-2.0-only", "RetroPass source identity differs")
    rows = lock.get("files")
    overlay.require(isinstance(rows, list) and len(rows) == lock.get("file_count") == 177 and
                    hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest() ==
                    lock.get("inventory_sha256") == "6b6940d09c4f1589d84c2a8d9079fd0c40c3a048b241026686218f8bf68173ae", "RetroPass inventory differs")
    expected = {}
    for row in rows:
        path = overlay.relative_path(row.get("path"))
        key = "smartpro-original-source/vendor/retropass/" + path
        overlay.require(key not in expected, "duplicate RetroPass source path")
        data = captured.get(key)
        overlay.require(data is not None and len(data) == row.get("size") and
                        overlay.digest(data) == row.get("sha256"), "RetroPass source bytes differ: " + path)
        expected[key] = data
    actual = {name for name in captured if name.startswith("smartpro-original-source/vendor/retropass/")}
    overlay.require(actual == set(expected), "RetroPass tree has missing or extra files")
    return lock
