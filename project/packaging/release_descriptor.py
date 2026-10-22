# SPDX-License-Identifier: MIT
"""Resolve current preview selection and bind it to the source bytes being built."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import overlay


def source_inventory(entries):
    return [{"path": name.removeprefix("smartpro-original-source/"),
             "sha256": overlay.digest(data), "size": len(data)}
            for name, data in sorted(entries)]


def resolve(project, descriptor_path, entries, source_lock):
    project, descriptor_path = Path(project), Path(descriptor_path)
    raw = descriptor_path.read_bytes()
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
    overlay.require(descriptor.get("selected_original_payload") == [
        "psp_shell", "bridge", "profiles", "ppsspp/theme", "assets"],
        "release descriptor differs from the original payload builder scope")
    overlay.require(descriptor.get("qualification") == {
        "hardware_qualified": False, "runtime_verified": False, "source_use_verified": False},
        "preview descriptor cannot grant qualification")
    overlay.require(source_lock is not None, "current release requires the spruce source lock")
    lock = json.loads(Path(source_lock).read_bytes())
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
    try:
        descriptor_relative = descriptor_path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError as exc:
        raise overlay.OverlayError("release descriptor must be included in original project source") from exc
    overlay.require(any(item["path"] == descriptor_relative and item["sha256"] == overlay.digest(raw)
                        for item in inventory), "selected release descriptor missing from source inventory")
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
                return subprocess.check_output(["git", "-C", str(project), *arguments],
                                               stderr=subprocess.DEVNULL, text=True).strip()
            overlay.require(Path(git("rev-parse", "--show-toplevel")).resolve() == project.parent.resolve(),
                            "frontend must be the project's repository checkout")
            commit = git("rev-parse", "HEAD")
            overlay.require(overlay.BASELINE.fullmatch(commit), "invalid frontend Git revision")
            frontend = {"commit": commit, "working_tree_modified": bool(
                git("status", "--porcelain", "--untracked-files=all", "--", "."))}
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
