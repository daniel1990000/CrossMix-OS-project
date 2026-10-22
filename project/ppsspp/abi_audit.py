#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Inspect AArch64 ELF dependency names and symbol versions without executing it.

The sysroot is a build input. Its library inventory does not establish the paths,
libraries or driver behavior of an installed Smart Pro.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def readelf(path: Path, *arguments: str) -> str:
    return subprocess.run(["aarch64-linux-gnu-readelf", *arguments, str(path)],
                          check=True, capture_output=True, text=True).stdout


def versions(text: str, section: str) -> dict:
    active = False
    current = ""
    result = {}
    for line in text.splitlines():
        if line.startswith("Version "):
            active = line.startswith("Version " + section + " section")
        if not active:
            continue
        match = re.search(r"File:\s+(\S+)", line)
        if match:
            current = match.group(1)
        match = re.search(r"Name:\s+(\S+)", line)
        if match:
            result.setdefault(current, set()).add(match.group(1))
    return {name: sorted(values) for name, values in result.items()}


def resolve_inside(path: Path, root: Path) -> Path | None:
    """Interpret absolute SDK symlinks inside the sysroot, never on the host."""
    try:
        pending = list(path.relative_to(root).parts)
    except ValueError:
        return None
    resolved = root
    links = 0
    while pending:
        part = pending.pop(0)
        if part == "..":
            if resolved == root:
                return None
            resolved = resolved.parent
            continue
        candidate = resolved / part
        if candidate.is_symlink():
            links += 1
            if links > 40:
                return None
            target = os.readlink(str(candidate))
            if target.startswith("/"):
                resolved = root
            pending = list(Path(target.lstrip("/")).parts) + pending
        else:
            resolved = candidate
    return resolved if resolved.is_file() else None


def audit(binary: Path, sysroot: Path) -> dict:
    inventory = {}
    for directory, _, files in os.walk(str(sysroot), followlinks=False):
        for name in files:
            if ".so" in name:
                inventory.setdefault(name, []).append(Path(directory) / name)
    for paths in inventory.values():
        paths.sort(key=lambda value: (len(value.parts), str(value)))
    missing = []
    version_errors = []
    records = {}
    visited = set()
    queue = [(str(binary), binary)]
    while queue:
        label, path = queue.pop(0)
        if str(path) in visited:
            continue
        visited.add(str(path))
        text = readelf(path, "-h", "-d", "-V")
        if not re.search(r"Machine:\s+AArch64", text):
            raise ValueError("Non-AArch64 dependency: " + str(path))
        needed = re.findall(r"Shared library: \[([^]]+)\]", text)
        required = versions(text, "needs")
        record = {"path": str(path), "needed": needed, "required_versions": required, "resolved": {}}
        for name in sorted(set(needed) | set(required)):
            candidates = [(candidate, resolve_inside(candidate, sysroot)) for candidate in inventory.get(name, [])]
            candidates = [(candidate, resolved) for candidate, resolved in candidates if resolved is not None]
            if not candidates:
                missing.append({"requester": label, "library": name})
                continue
            candidate, resolved = candidates[0]
            offered = versions(readelf(resolved, "-V"), "definition").get("", [])
            absent = sorted(set(required.get(name, [])) - set(offered))
            if absent:
                version_errors.append({"requester": label, "library": name, "missing_versions": absent})
            record["resolved"][name] = {"inventory_path": str(candidate), "resolved_path": str(resolved),
                                         "all_inventory_candidates": [str(item[0]) for item in candidates],
                                         "ambiguous_basename": len(candidates) > 1,
                                         "selection": "shortest then lexical SDK path; actual loader order untested",
                                         "available_versions": offered}
            queue.append((name, resolved))
        records[label] = record
    program = readelf(binary, "-l")
    match = re.search(r"Requesting program interpreter:\s*([^]]+)\]", program)
    interpreter = match.group(1) if match else None
    interpreter_present = bool(interpreter and resolve_inside(sysroot / interpreter.lstrip("/"), sysroot))
    return {"schema_version": 1, "method": "readelf only; SDK basename inventory and symbol-version comparison",
            "target_executed": False, "device_compatibility_proved": False,
            "interpreter": interpreter, "interpreter_present_in_sysroot": interpreter_present,
            "sdk_dependency_inventory_pass": not missing and not version_errors and interpreter_present,
            "missing_libraries": missing, "missing_symbol_versions": version_errors, "objects": records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("sysroot", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.binary.resolve(), args.sysroot.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
