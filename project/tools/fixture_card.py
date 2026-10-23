#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create an explicitly marked, empty host sandbox; never a real device card."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).absolute().parents[1] / "packaging"))
from overlay import FIXTURE_MARKER, SPRUCE_COMMIT, PYUI_TREE, digest


def create_fixture(card):
    card = Path(card).absolute()
    if card == Path("/mnt/SDCARD") or "SDCARD" in card.parts:
        raise ValueError("refusing a device SD path")
    if card.is_symlink() or (card.exists() and any(card.iterdir())):
        raise ValueError("fixture path must be an empty directory or new path")
    for parent in card.parents:
        if parent.is_symlink():
            raise ValueError("fixture path cannot contain symlinks")
    card.mkdir(parents=True, exist_ok=True)
    (card / ".spruce-host-fixture").write_bytes(FIXTURE_MARKER)
    (card / "base").mkdir()
    contract = b"spruceOS 4.5.4 host fixture only; not device evidence\n"
    (card / "base/runtime.txt").write_bytes(contract)
    profile = {"schema": 1, "id": "spruce454-tg5040-host-fixture", "model": "trimui-smart-pro",
               "architecture": "aarch64", "execution_environment": "host-fixture",
               "firmware_versions": ["fixture-1.1.1"], "base_commit": SPRUCE_COMMIT, "pyui_git_tree": PYUI_TREE,
               "hardware_qualified": False, "runtime_verified": False, "source_use_verified": False,
               "baseline_files": {"base/runtime.txt": digest(contract)}}
    inventory = {"schema": 1, "kind": "host-fixture-inventory", "profile_id": profile["id"],
                 "device": {"model": "trimui-smart-pro", "architecture": "aarch64", "firmware": "fixture-1.1.1",
                            "base_commit": SPRUCE_COMMIT, "pyui_git_tree": PYUI_TREE},
                 "note": "Synthetic target values for host tests; not observations from any device."}
    for name, value in (("fixture-profile.json", profile), ("fixture-inventory.json", inventory)):
        (card / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"card": str(card), "profile": str(card / "fixture-profile.json"),
            "inventory": str(card / "fixture-inventory.json")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(create_fixture(args.card), indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print("fixture: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
