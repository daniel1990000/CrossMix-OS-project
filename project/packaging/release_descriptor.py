# SPDX-License-Identifier: MIT
"""Resolve current preview selection and bind it to the source bytes being built."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import overlay

SOURCE_FOLDERS = {"psp_shell", "bridge", "integration", "profiles", "assets", "packaging", "tools", "tests", "docs", "dev", "ppsspp"}
SOURCE_ROOT_FILES = {"LICENSE", "README.md", "pyproject.toml", "requirements-dev.txt"}
SOURCE_ORIGINAL_C_FILES = {"dev/host_virtual_controller.c"}
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
    if (relative.parts[0] == "ppsspp" and relative.as_posix() != "ppsspp/performance-source-lock.json"
            and (len(relative.parts) < 2 or relative.parts[1] != "theme")):
        return False
    return (not any(part in {"__pycache__", ".git", ".venv", "state", "transactions", "previews", "migrations", "fixtures"}
                    for part in relative.parts) and relative.name != "author-notification-draft.txt")


def original_source_file(relative):
    relative = Path(relative)
    return original_source_scope(relative) and (relative.suffix.lower() in SOURCE_EXTENSIONS or
           relative.as_posix() in SOURCE_ROOT_FILES or relative.as_posix() in SOURCE_ORIGINAL_C_FILES or
           relative.name == "LICENSE")


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
    overlay.require(descriptor.get("delivery") == "original-only-host-preview",
                    "development builder requires original-only host delivery")
    overlay.require(descriptor.get("frontend", {}).get("selection") == "repository-head-or-source-export",
                    "unsupported frontend revision selection")
    overlay.require(descriptor.get("base", {}).get("source_commit") == overlay.SPRUCE_COMMIT and
                    descriptor["base"].get("pyui_git_tree") == overlay.PYUI_TREE,
                    "release descriptor differs from the pinned spruce/PyUI baseline")
    overlay.require(type(descriptor.get("source_date_epoch")) is int,
                    "descriptor timestamp missing")
    overlay.require(descriptor.get("selected_upstream_patches") == [] and
                    descriptor.get("selected_native_binaries") == [],
                    "original-only preview cannot select upstream patches or native binaries")
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
