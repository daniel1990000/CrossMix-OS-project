"""Original Smart Pro presentation and integration helpers.

Hardware qualification and source-use obligations are recorded separately.
"""

import json
from pathlib import Path
import re
import sys


def _metadata(path):
    """Read display metadata only; these fields never grant device admission."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, RecursionError):
        return None


def build_info():
    """Describe this installed package or source descriptor without probing Git."""
    module = Path(__file__).resolve()
    info = {"version": "unknown-development", "release_id": None,
            "source_kind": "unavailable", "frontend_commit": None,
            "working_tree_modified": None, "source_inventory_sha256": None,
            "delivery": None}
    installed = _metadata(module.parents[2] / "metadata/development-release.json")
    descriptor = _metadata(module.parents[1] / "packaging/current-release.json")
    if descriptor is not None:
        candidate, release, source_kind = descriptor, descriptor.get("release_id"), "source-checkout"
    elif installed is not None:
        selected = installed.get("release_selection")
        selected = selected if isinstance(selected, dict) else {}
        candidate = selected.get("descriptor")
        candidate = candidate if isinstance(candidate, dict) else {}
        release = installed.get("release_id")
        if candidate.get("release_id") != release:
            return info
        source_kind = "installed-package"
        frontend = selected.get("frontend")
        frontend = frontend if isinstance(frontend, dict) else {}
        commit = frontend.get("commit")
        inventory = selected.get("source_inventory_sha256")
        if isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit):
            info["frontend_commit"] = commit
        if type(frontend.get("working_tree_modified")) is bool:
            info["working_tree_modified"] = frontend["working_tree_modified"]
        if isinstance(inventory, str) and re.fullmatch(r"[0-9a-f]{64}", inventory):
            info["source_inventory_sha256"] = inventory
    else:
        candidate = _metadata(Path(sys.prefix) / "share/psp_shell/metadata/current-release.json")
        if candidate is None:
            return info
        release, source_kind = candidate.get("release_id"), "installed-package"
    if (candidate.get("schema") != 1 or candidate.get("delivery") != "original-only-host-preview" or
            not isinstance(release, str) or
            re.fullmatch(r"smartpro-psp-[A-Za-z0-9][A-Za-z0-9._-]{0,95}", release) is None):
        return {**info, "frontend_commit": None, "working_tree_modified": None,
                "source_inventory_sha256": None}
    info.update(version=release.removeprefix("smartpro-psp-"), release_id=release,
                source_kind=source_kind, delivery=candidate["delivery"])
    return info


__version__ = build_info()["version"]
