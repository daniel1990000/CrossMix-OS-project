#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prove selected pinned spruce source patches before compiling a candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(data)
    return hasher.hexdigest()


def git(source: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=source, check=True, capture_output=True).stdout


def changed(source: Path) -> dict:
    paths = set(git(source, "diff", "--name-only", "-z").split(b"\0"))
    paths.update(git(source, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0"))
    return {path.decode(): digest(source / path.decode()) if (source / path.decode()).is_file() else None
            for path in sorted(paths) if path}


def original_digest(source: Path, path: str) -> str | None:
    result = subprocess.run(["git", "show", "HEAD:" + path], cwd=source, capture_output=True)
    return hashlib.sha256(result.stdout).hexdigest() if result.returncode == 0 else None


def selection(script: str, inputs: dict) -> tuple[list[dict], list[str]]:
    common_start = script.index("# Apply common patches")
    pvr_start = script.index("# Apply PVR-specific patches", common_start)
    end = script.index("mkdir -p build && cd build", pvr_start)
    blocks = {"common": script[common_start:pvr_start], "pvr": script[pvr_start:end]}
    expected_skips = {"common": {"fullscreen.py", "skip-vulkan-probe.py"},
                      "pvr": {"revert-fullscreen.py", "debug-gl-init.py", "glfinish-before-swap.py"}}
    selected = []
    skipped = []
    for group, block in blocks.items():
        parsed = set()
        for match in re.findall(r'^\s*([a-zA-Z0-9_.|-]+)\)\s*echo "Skipping:', block, re.M):
            parsed.update(match.split("|"))
        if parsed != expected_skips[group]:
            raise ValueError("Pinned recipe patch selection changed for " + group)
        members = sorted((item for item in inputs["recipe_files"]
                          if item["path"].startswith("patches/" + group + "/") and item["path"].endswith(".py")),
                         key=lambda item: item["path"])
        if not members:
            raise ValueError("Pinned recipe patch inventory is empty for " + group)
        for item in members:
            if Path(item["path"]).name in parsed:
                skipped.append(item["path"])
            else:
                selected.append(item)
    return selected, skipped


def assemble(source: Path, recipe: Path, source_lock: dict, inputs: dict, output: Path,
             override_lock: dict | None = None, override_root: Path | None = None) -> dict:
    report_path = output / "recipe-assembly.json"
    expected_commit = source_lock["upstream"]["commit"]
    if git(source, "rev-parse", "HEAD").decode().strip() != expected_commit:
        raise ValueError("Candidate source commit differs from the upstream lock")
    recipe_files = {item["path"]: item["sha256"] for item in inputs["recipe_files"]}
    for name, expected in recipe_files.items():
        if digest(recipe / name) != expected:
            raise ValueError("Pinned recipe content differs: " + name)
    selected, skipped = selection((recipe / "build-pvr.sh").read_text(), inputs)
    input_identity = {"upstream_commit": expected_commit, "recipe_commit": inputs["recipe_commit"],
                      "project_patch_sha256": [item["sha256"] for item in source_lock["patches"]],
                      "selected": [{"path": item["path"], "sha256": item["sha256"]} for item in selected]}
    if override_lock:
        if (override_lock.get("upstream_commit") != expected_commit or
                override_lock.get("recipe_commit") != inputs["recipe_commit"] or override_root is None):
            raise ValueError("Post-recipe override prerequisite differs")
        if not override_lock.get("patches") or not override_lock.get("source_files") or not override_lock.get("patched_files"):
            raise ValueError("Post-recipe override inventory is incomplete")
        for item in override_lock["patches"]:
            path = override_root / item["path"]
            if path.is_symlink() or digest(path) != item["sha256"]:
                raise ValueError("Post-recipe override patch changed")
        input_identity["post_recipe_override"] = override_lock
    if report_path.exists():
        old = json.loads(report_path.read_text())
        if old.get("status") != "applied" or old.get("input_identity") != input_identity or old.get("final_source_files") != changed(source):
            raise ValueError("Existing recipe assembly is failed, stale or has changed source")
        return old
    for item in source_lock["patched_files"]:
        if digest(source / item["path"]) != item["sha256"]:
            raise ValueError("Project postimage differs before recipe assembly: " + item["path"])
    if changed(source) != {item["path"]: item["sha256"] for item in source_lock["patched_files"]}:
        raise ValueError("Candidate source has changes outside the locked project postimages")
    report = {"schema_version": 1, "status": "applying", "input_identity": input_identity,
              "python": sys.version.split()[0], "skipped_by_pinned_recipe": skipped, "scripts": []}
    try:
        with (output / "recipe-application.log").open("w") as log:
            for item in selected:
                path = recipe / item["path"]
                with path.open("rb"):
                    pass  # Readability is a prerequisite, not a wildcard-loop side effect.
                before = changed(source)
                result = subprocess.run([sys.executable, str(path)], cwd=source, capture_output=True, text=True)
                log.write(item["path"] + "\n" + result.stdout + result.stderr + "\n")
                log.flush()
                after = changed(source)
                changes = []
                for name in sorted(set(before) | set(after)):
                    old_hash = before[name] if name in before else original_digest(source, name)
                    new_hash = after[name] if name in after else original_digest(source, name)
                    if old_hash != new_hash:
                        changes.append({"path": name, "before_sha256": old_hash, "after_sha256": new_hash})
                record = {"path": item["path"], "sha256": item["sha256"], "exit_code": result.returncode,
                          "changed_files": changes}
                report["scripts"].append(record)
                if result.returncode or not changes:
                    raise ValueError("Pinned recipe script failed or changed no source: " + item["path"])
            if override_lock:
                for item in override_lock["source_files"]:
                    if digest(source / item["path"]) != item["sha256"]:
                        raise ValueError("Post-recipe override source preimage differs: " + item["path"])
                for item in override_lock["patches"]:
                    path = override_root / item["path"]
                    git(source, "apply", "--check", str(path))
                    git(source, "apply", str(path))
                    log.write("post-recipe override: " + item["path"] + "\n")
                for item in override_lock["patched_files"]:
                    if digest(source / item["path"]) != item["sha256"]:
                        raise ValueError("Post-recipe override source postimage differs: " + item["path"])
                report["post_recipe_overrides"] = override_lock["patches"]
        report["status"] = "applied"
        report["final_source_files"] = changed(source)
        (output / "combined-tracked-source.patch").write_bytes(git(source, "diff", "--binary"))
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("recipe", type=Path)
    parser.add_argument("source_lock", type=Path)
    parser.add_argument("build_inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--override-lock", type=Path)
    parser.add_argument("--override-root", type=Path)
    args = parser.parse_args()
    report = assemble(args.source, args.recipe, json.loads(args.source_lock.read_text()),
                      json.loads(args.build_inputs.read_text()), args.output,
                      json.loads(args.override_lock.read_text()) if args.override_lock else None,
                      args.override_root)
    print(json.dumps({"status": report["status"], "scripts_applied": len(report["scripts"]),
                      "final_source_file_count": len(report["final_source_files"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
