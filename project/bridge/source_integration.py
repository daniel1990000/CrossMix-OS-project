"""Inspect exact pinned lifecycle sources; optionally stage a review-only seam.

The audit is read-only. Producing an upstream source derivative requires the
explicit source-use gate. No function applies a patch, registers a caller,
starts services or enables a device/profile gate.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path

from psp_shell.runtime import ContractError, SPRUCE_COMMIT


PYUI = "App/PyUI/main-ui/"
MAINUI = PYUI + "mainui.py"
DEVICE_COMMON = PYUI + "devices/device_common.py"
SOURCE_BLOBS = {
    MAINUI: "358d6a6885f69725c6db6d1ccbd6e0dbb8c192e7",
    DEVICE_COMMON: "2a557b1637370ae8da2d78551ffd7a96e9c118d6",
    PYUI + "devices/trimui/trim_ui_smart_pro.py": "deadf503c2f73188d47b18d790d57821169ce101",
    PYUI + "controller/key_watcher.py": "b1003dfa4b576f185a2310c5ac85ca753f2e499b",
    PYUI + "controller/key_watcher_controller.py": "57066c5026bc07b84f755389bf3aed7264b364a5",
    PYUI + "devices/utils/file_watcher.py": "1073ae55b4032e6db7cdebd8a0c0e663c3b94685",
    PYUI + "utils/throttle.py": "18ef83d2601877f1fbeb98e99d30f7040cd24b19",
    PYUI + "menus/games/utils/cheevos_cache_manager.py": "605ed8ef84df0ffd8d7da9866cdcdfc1f48d1a77",
    PYUI + "audio/sdl2_audio_player.py": "12b526326c197db36d0e495608f901e7b5313d22",
    "spruce/scripts/principal.sh": "cfee3badaed8606121635d9ebbfb3dfc2d5dc25e",
}

UNACCOUNTED_OWNERS = (
    "SmartPro constructor startup/config/key watchers",
    "controller polling thread and input descriptors",
    "nested startup audio-route refresh and Bluetooth workers",
    "timezone file watcher and throttle background refreshes",
    "Cheevos cache startup child and optional library/network workers",
    "SDL audio worker and source display/input release",
    "principal staged command, surviving descendants and display/input ownership",
)


def _source_bytes(root: Path, path: str) -> bytes:
    source = root / path
    if (any(item.is_symlink() for item in (source, *source.parents) if item != root and root in item.parents) or
            not source.is_file() or source.stat().st_size > 262144):
        raise ContractError("SOURCE_MISMATCH", "Lifecycle inspection requires bounded regular pinned sources")
    raw = source.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if blob != SOURCE_BLOBS[path]:
        raise ContractError("SOURCE_MISMATCH", "A lifecycle source differs from pinned spruce v4.5.4")
    return raw


def audit_source_lifecycle(source_root: str | Path) -> dict:
    root = Path(source_root).resolve(strict=True)
    sources = []
    for path, blob in SOURCE_BLOBS.items():
        raw = _source_bytes(root, path)
        sources.append({"path": path, "git_blob": blob, "sha256": hashlib.sha256(raw).hexdigest()})
    return {"schema": 1, "evidence": "untouched-pinned-source-inspection", "base_commit": SPRUCE_COMMIT,
            "sources": sources, "unaccounted_owners": list(UNACCOUNTED_OWNERS),
            "source_caller_installed": False, "principal_return_authority_qualified": False,
            "hardware_qualified": False}


def _replace_once(text: str, marker: str, replacement: str) -> str:
    if text.count(marker) != 1:
        raise ContractError("SOURCE_MISMATCH", "The unique pinned lifecycle seam is missing")
    return text.replace(marker, replacement, 1)


def stage_lifecycle_hook(source_root: str | Path, staging_dir: str | Path, *,
                         source_use_verified: bool = False) -> dict:
    """Stage the actual startup caller and cooperative audio source seam.

    Compose with pyui_entry.stage_main_menu_hook, which preserves the original
    game-selection/GameSwitcher/box-art prelude. This separate patch leaves
    MainMenu and principal untouched; all unknown owners still need qualification.
    """
    if source_use_verified is not True:
        raise ContractError("SOURCE_USE_UNVERIFIED", "Resolve source-use obligations before producing a PyUI lifecycle patch")
    root = Path(source_root).resolve(strict=True)
    audit = audit_source_lifecycle(root)
    staging = Path(staging_dir).absolute()
    try:
        staging.resolve().relative_to(root)
    except ValueError:
        pass
    else:
        raise ContractError("UNSAFE_STAGING", "Lifecycle staging must be outside the untouched source tree")
    if any(item.is_symlink() for item in (staging, *staging.parents)):
        raise ContractError("UNSAFE_STAGING", "Lifecycle staging cannot use symlink directories")
    patch_parts, transformed = [], []
    for path in (MAINUI, DEVICE_COMMON):
        raw = _source_bytes(root, path)
        text = raw.decode("utf-8")
        newline = "\r\n" if "\r\n" in text else "\n"
        if path == MAINUI:
            marker = "def start_background_threads():" + newline
            addition = "\n".join((
                "    try:",
                "        from bridge.lifecycle import begin_source_tasks",
                "    except (ImportError, SyntaxError):",
                "        begin_source_tasks = None",
                "    if begin_source_tasks is not None:",
                "        project_tasks = begin_source_tasks(Device.get_device(), background_startup)",
                "        if project_tasks is not None:",
                "            return project_tasks",
                "",
            )).replace("\n", newline)
            changed = _replace_once(text, marker, marker + addition + newline)
            marker = "    start_background_threads()" + newline
            changed = _replace_once(changed, marker, newline.join((
                "    project_tasks = start_background_threads()",
                "    if project_tasks is not None:",
                "        from bridge.lifecycle import bind_source_session",
                "        bind_source_session(main_menu, project_tasks)",
                "",
            )))
        else:
            changed = _replace_once(text, "    def watch_audio_route(self):", "    def watch_audio_route(self, stop_event=None):")
            marker = "        while True:" + newline + "            time.sleep(1)" + newline
            changed = _replace_once(changed, marker, newline.join((
                "        while stop_event is None or not stop_event.is_set():",
                "            if stop_event is None:",
                "                time.sleep(1)",
                "            elif stop_event.wait(1):",
                "                break",
                "",
            )))
        compile(changed, path, "exec")
        patch_parts.extend(difflib.unified_diff(text.splitlines(keepends=True), changed.splitlines(keepends=True),
                                               fromfile="a/" + path, tofile="b/" + path))
        transformed.append({"path": path, "base_sha256": hashlib.sha256(raw).hexdigest(),
                            "patched_sha256": hashlib.sha256(changed.encode("utf-8")).hexdigest()})
    staging.mkdir(parents=True, exist_ok=True)
    target = staging / "0002-pyui-retained-startup.patch"
    metadata = staging / "lifecycle-hook.json"
    if target.is_symlink() or metadata.is_symlink():
        raise ContractError("UNSAFE_STAGING", "Lifecycle artifacts cannot replace symlinks")
    target.write_bytes("".join(patch_parts).encode("utf-8"))
    record = {**audit, "patch_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
              "transformed": transformed, "source_use_verified": True,
              "requires_trusted_in_memory_registration": True,
              "requires_separate_main_menu_hook": True, "modifies_rootfs_or_boot": False,
              "hardware_execution_enabled": False}
    metadata.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record
