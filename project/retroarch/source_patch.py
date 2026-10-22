# SPDX-License-Identifier: MIT
"""Prepare the locked optional IGM extension in private development scratch."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def added_source(patch_text, name):
    marker = "diff --git a/" + name + " b/" + name + "\n"
    if patch_text.count(marker) != 1:
        raise ValueError("Pinned recipe added-file identity differs")
    section = patch_text.split(marker, 1)[1].split("diff --git ", 1)[0]
    if "--- /dev/null\n" not in section:
        raise ValueError("Recipe source is not an added file")
    return "".join(line[1:] for line in section.splitlines(keepends=True)
                   if line.startswith("+") and not line.startswith("+++"))


def prepare(recipe_root, output):
    recipe, output = Path(recipe_root).resolve(strict=True), Path(output).absolute()
    if output.exists() or output.is_symlink() or output == recipe or recipe in output.parents:
        raise ValueError("Choose new private output outside the recipe source")
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError("Output cannot traverse a symlink")
    lock = json.loads((HERE / "source-lock.json").read_text())
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=recipe, capture_output=True, text=True, check=True).stdout.strip()
    if commit != lock["recipe"]["commit"]:
        raise ValueError("Recipe commit differs from the source lock")
    for item in lock["inputs"]:
        path = recipe / item["path"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1048576 or digest(path.read_bytes()) != item["sha256"]:
            raise ValueError("Recipe input differs: " + item["path"])
    patch = HERE / lock["patch"]["path"]
    if digest(patch.read_bytes()) != lock["patch"]["sha256"]:
        raise ValueError("Optional IGM patch differs")
    sources = {"spruce_igm.c": added_source((recipe / "patches/common/0001-spruce-igm.patch").read_text(), "spruce_igm.c")}
    for name in ("spruce_igm_theme.h", "spruce_igm_theme.c"):
        sources[name] = (recipe / "common_src" / name).read_text()
    for item in lock["staged_source"]:
        if digest(sources[item["path"]].encode()) != item["sha256"]:
            raise ValueError("Staged IGM source differs")
    output.mkdir(parents=True)
    for name, source in sources.items():
        (output / name).write_text(source)
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=output, capture_output=True, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=output, capture_output=True, check=True)
    for item in lock["patched_source"]:
        if digest((output / item["path"]).read_bytes()) != item["sha256"]:
            raise ValueError("Patched IGM source differs")
    return {"schema": 1, "recipe_commit": commit, "patch_sha256": lock["patch"]["sha256"],
            "source_patch_applied": True, "full_engine_build": False, "target_executed": False,
            "device_qualified": False, "distribution_cleared": False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe-root', required=True)
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.recipe_root, arguments.output), indent=2))
