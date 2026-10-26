#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a private exact-source review kit or a separately authorized candidate.

This tool has no live installation, device activation or publication command.
Inspected source stays untouched. Signed original overlays retain the existing
overlay verifier; upstream source changes retain their separate licence scope.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("smartpro_integration_overlay", PROJECT / "packaging/overlay.py")
overlay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(overlay)

MAX_SOURCE = 512 * 1024
MAX_PATCH = 512 * 1024
MAX_RECORDS = 64
MODULE_ROOT = "/mnt/SDCARD/App/PSPMode/integration/app"
PAYLOAD_ROOT = "App/PSPMode/integration"
# Only these installed original helpers may participate in this boundary.
# A signed archive is not permission to import arbitrary maintenance tools.
SIGNED_TOOL_MODULES = frozenset({
    "app/tools/__init__.py", "app/tools/backup_catalog.py",
    "app/tools/recovery_payload.py", "app/tools/recovery_preflight.py",
})
LICENCES = {
    "LICENSE": "7d82903f223c62b411247115f1b577c44e2e6bc2",
    "App/PyUI/LICENSE.md": "3e98034103df4771210012e478d792b2a361d856",
    "App/PyUI/main-ui/LICENSE.md": "9c91591999e6049bb99dc191ffebc0608e28fa85",
}
BLOCKERS = (
    ("SOURCE_USE", "Retain actual author-notification delivery or applicable permission and review its scope."),
    ("RUNTIME_OWNERSHIP", "Qualify the actual source caller, child ownership, display/input release and correlated principal return."),
    ("INSTALLED_INVENTORY", "Capture original TG5040 firmware, loader/libraries, input and complete config-writer identities."),
    ("SAVE_LOAD", "Prove exact engine/game/state identity, successful save/load and clean foreground return on the target."),
    ("RECOVERY", "Prove original-card and internal startup/scene restoration plus FAT/exFAT interruption recovery."),
    ("POWER_USB", "Measure suspend/wake, poweroff/save completion and staged clean-unmount USB behavior."),
    ("DISTRIBUTION", "Resolve exact source, recipe, SDK/runtime and per-port redistribution terms before publishing a device build."),
)


class IntegrationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise IntegrationError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class SourceTree:
    """Open fixed relative source names without following ancestor symlinks."""
    def __init__(self, root):
        self.root = overlay.ensure_no_links(Path(root))
        require(self.root.is_dir(), "source root must be an existing directory")
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        os.close(self.fd)

    def read(self, relative, limit=MAX_SOURCE, *, allow_empty=False):
        overlay.relative_path(relative)
        parts = relative.split("/")
        parent = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                os.close(parent)
                parent = child
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                require(stat.S_ISREG(before.st_mode) and (0 if allow_empty else 1) <= before.st_size <= limit,
                        "source must be a bounded nonempty regular file: " + relative)
                data = stream.read(before.st_size + 1)
                after = os.fstat(stream.fileno())
                fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
                require(len(data) == before.st_size and all(getattr(before, name) == getattr(after, name) for name in fields),
                        "source changed during read: " + relative)
                return data
        finally:
            os.close(parent)


def _locked_patches():
    manifest = overlay.read_json(PROJECT / "patches/manifest.json")
    require(manifest.get("commit") == overlay.SPRUCE_COMMIT and manifest.get("release") == "v4.5.4",
            "patch manifest does not select the pinned source")
    records = manifest.get("patches")
    require(isinstance(records, list) and len(records) == 4, "exactly four locked reliability patches are required")
    result = []
    with SourceTree(PROJECT / "patches") as patches:
        for item in records:
            require(set(item) == {"patch", "path", "base_sha256", "patched_sha256"}, "unexpected patch manifest fields")
            overlay.relative_path(item["patch"])
            overlay.relative_path(item["path"])
            require("/" not in item["patch"], "patch must be an immediate locked patch file")
            require(all(overlay.SHA256.fullmatch(item[name]) for name in ("base_sha256", "patched_sha256")),
                    "patch source fingerprints must be SHA256")
            raw = patches.read(item["patch"], MAX_PATCH)
            _patch_paths(raw, {item["path"]})
            result.append(dict(item, patch_sha256=digest(raw), data=raw))
    require(len({item["path"] for item in result}) == 4, "reliability patch targets must be distinct")
    return result


def _selected_patches(include_state_session=False):
    require(type(include_state_session) is bool, "state-session selection must be explicit")
    records = _locked_patches()
    if not include_state_session:
        return records
    lock = overlay.read_json(PROJECT / "patches/ppsspp-state-session.lock.json")
    require(lock.get("schema_version") == 1 and lock.get("source_commit") == overlay.SPRUCE_COMMIT,
            "state-session launch lock does not select the pinned spruce source")
    before, after, patch = lock.get("source_files"), lock.get("patched_files"), lock.get("patch", {})
    require(isinstance(before, list) and isinstance(after, list) and len(before) == len(after) == 1 and
            before[0]["path"] == after[0]["path"] and
            before[0]["path"] == "spruce/scripts/emu/lib/ppsspp_functions.sh",
            "state-session wrapper scope differs from the reviewed source")
    require(patch.get("path") == "project/patches/0005-ppsspp-private-state-session.patch",
            "state-session patch path differs from the reviewed source")
    with SourceTree(PROJECT / "patches") as patches:
        raw = patches.read("0005-ppsspp-private-state-session.patch", MAX_PATCH)
    require(digest(raw) == patch.get("sha256"), "state-session launch patch hash mismatch")
    _patch_paths(raw, {before[0]["path"]})
    records.append({"patch": "0005-ppsspp-private-state-session.patch", "path": before[0]["path"],
                    "base_sha256": before[0]["sha256"], "patched_sha256": after[0]["sha256"],
                    "patch_sha256": digest(raw), "data": raw})
    return records


def _patch_paths(raw, expected=None):
    text = raw.decode("utf-8")
    old, new = [], []
    for line in text.splitlines():
        if line.startswith("--- "):
            require(line.startswith("--- a/"), "patch removes or renames an unsupported source")
            old.append(overlay.relative_path(line[6:]))
        if line.startswith("+++ "):
            require(line.startswith("+++ b/"), "patch adds or renames an unsupported source")
            new.append(overlay.relative_path(line[6:]))
        require(not line.startswith(("GIT binary patch", "Binary files ", "rename from ", "rename to ",
                                     "copy from ", "copy to ", "new file mode ", "deleted file mode ")),
                "only bounded text modifications to existing source are accepted")
    require(old and old == new and len(set(old)) == len(old), "patch must modify distinct existing source paths")
    if expected is not None:
        require(set(old) == expected, "patch targets differ from the reviewed source scope")
    return old


def _source_contracts():
    from bridge.pyui_entry import MAIN_MENU_PATH, MAIN_MENU_BLOB
    from bridge.source_integration import SOURCE_BLOBS
    try:
        from bridge.principal_integration import SOURCE_BLOBS as PROCESS_BLOBS
    except ModuleNotFoundError as error:
        if error.name != "bridge.principal_integration":
            raise
        PROCESS_BLOBS = {}
    blobs = {**LICENCES, **SOURCE_BLOBS, **PROCESS_BLOBS, MAIN_MENU_PATH: MAIN_MENU_BLOB}
    return blobs


def source_inventory(source_root, *, include_state_session=False):
    """Read-only exact preimages, including licences; no derivative is produced."""
    patches, blobs = _selected_patches(include_state_session), _source_contracts()
    paths = sorted(set(blobs) | {item["path"] for item in patches})
    entries = []
    with SourceTree(source_root) as source:
        for name in paths:
            raw = source.read(name)
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
            if name in blobs:
                require(blob == blobs[name], "pinned source blob mismatch: " + name)
            matches = [item for item in patches if item["path"] == name]
            if matches:
                require(digest(raw) == matches[0]["base_sha256"], "pinned reliability source mismatch: " + name)
            entries.append({"path": name, "size": len(raw), "sha256": digest(raw), "git_blob": blob})
    return entries


def _manifest(kind, inventory, patch_records, *, source_review=None, include_state_session=False):
    return {
        "schema": 1, "kind": kind, "base_commit": overlay.SPRUCE_COMMIT,
        "target": "original TG5040 SmartPro", "source_inventory": inventory,
        "patches": patch_records, "source_review_reference": source_review,
        "include_state_session": include_state_session,
        "device_activation": False, "hardware_qualified": False, "runtime_verified": False,
        "distribution_cleared": False, "production_authenticity_claim": False,
        "source_review_is_physical_qualification": False,
        "rootfs_or_boot_modified": False, "installed_emulator_modified": False,
        "saves_or_roms_included": False, "external_blockers": [dict(code=code, requirement=description) for code, description in BLOCKERS],
    }


def _write(root, relative, data):
    overlay.relative_path(relative)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o600)


def _record(root, manifest):
    manifest["artifact_files"] = _artifact_inventory(root)
    raw = overlay.canonical(overlay.record_with_checksum(manifest)) + b"\n"
    _write(root, "candidate.json", raw)


def _artifact_inventory(root):
    result = []
    with SourceTree(root) as tree:
        for count, path in enumerate(sorted(root.rglob("*"))):
            require(count < 1024, "private artifact contains too many entries")
            require(not path.is_symlink(), "private artifact contains a symlink")
            if path.is_dir():
                continue
            name = path.relative_to(root).as_posix()
            if name == "candidate.json":
                continue
            require(len(result) < 256, "private artifact contains too many files")
            raw = tree.read(name, overlay.MAX_ARCHIVE if name == "original-overlay.tar" else overlay.MAX_FILE,
                            allow_empty=True)
            result.append({"path": name, "sha256": digest(raw), "size": len(raw)})
    return result


def _output(output, source_root):
    output = overlay.ensure_no_links(Path(output))
    source = Path(source_root).resolve(strict=True)
    require(not output.exists(), "choose a new output directory")
    require(output != source and not output.is_relative_to(source) and not source.is_relative_to(output),
            "output must be separate from the inspected source")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _copy_overlay(destination, archive, public_key, *, expand=False):
    require(bool(archive) == bool(public_key), "supply both original overlay archive and external verification key")
    if archive is None:
        return None
    public = overlay.load_key(public_key, 32)
    with overlay.VerifiedArchive(archive, public) as verified:
        verified.handle.seek(0)
        length = os.fstat(verified.handle.fileno()).st_size
        raw = verified.handle.read(length + 1)
        require(len(raw) == length, "verified overlay changed during retention")
        # Recheck the same bytes, not a later path lookup, before retaining them.
        with tempfile.TemporaryDirectory(prefix="overlay-retention-") as temporary:
            path = Path(temporary) / "overlay.tar"
            path.write_bytes(raw)
            with overlay.VerifiedArchive(path, public) as retained:
                require(retained.manifest_bytes == verified.manifest_bytes and retained.signature == verified.signature,
                        "verified overlay changed before retention")
                if expand:
                    target = destination / "tree" / PAYLOAD_ROOT
                    target.mkdir(parents=True)
                    retained.extract_to(target)
        _write(destination, "original-overlay.tar", raw)
        return {"release_id": verified.manifest["release_id"], "sha256": digest(raw),
                "key_id": digest(public), "signature_inventory_verified": True,
                "module_root": MODULE_ROOT if expand else None,
                "payload_expanded_in_private_tree": expand,
                "grants_source_or_hardware_qualification": False}


def prepare_review_kit(source_root, output, *, overlay_archive=None, public_key=None, include_state_session=False):
    """Retain existing patches and exact source observations without applying them."""
    output = _output(output, source_root)
    inventory = source_inventory(source_root, include_state_session=include_state_session)
    patches = _selected_patches(include_state_session)
    with tempfile.TemporaryDirectory(prefix=".integration-review-", dir=output.parent) as temporary:
        staging = Path(temporary) / "content"
        staging.mkdir(mode=0o700)
        records = []
        for item in patches:
            _write(staging, "patches/" + item["patch"], item["data"])
            records.append({key: value for key, value in item.items() if key != "data"})
        with SourceTree(source_root) as source:
            for index, name in enumerate(LICENCES):
                _write(staging, "notices/" + str(index) + "-" + Path(name).name, source.read(name))
        manifest = _manifest("private-source-review-kit", inventory, records, include_state_session=include_state_session)
        manifest["source_derived"] = False
        manifest["source_use_reviewed"] = False
        manifest["original_overlay"] = _copy_overlay(staging, overlay_archive, public_key)
        require(source_inventory(source_root, include_state_session=include_state_session) == inventory,
                "source changed before review-kit publication")
        _record(staging, manifest)
        require(not output.exists(), "output appeared during preparation; refusing replacement")
        os.rename(staging, output)
    return manifest


@dataclass(frozen=True)
class SourceUseReview:
    """Trusted in-memory source-use decision; no file or JSON deserializer exists.

    The reference must identify retained real delivery/permission and scope review.
    Constructing this type does not perform notification or resolve legal terms.
    Host tests use explicit fixture references and establish no actual clearance.
    """
    source_commit: str
    evidence_reference: str
    scope: str = "private-source-candidate"


def _review(review):
    require(type(review) is SourceUseReview and review.source_commit == overlay.SPRUCE_COMMIT and
            review.scope == "private-source-candidate" and isinstance(review.evidence_reference, str) and
            8 <= len(review.evidence_reference) <= 256 and
            all(32 <= ord(char) < 127 for char in review.evidence_reference),
            "a trusted in-memory source-use scope review is required before producing a derivative")


def _bridge_patch(source_root, staging, mode):
    if mode == "none":
        return [], None
    if mode == "process-exit":
        from bridge.principal_integration import stage_process_exit_integration
        record = stage_process_exit_integration(source_root, staging, source_use_verified=True,
                                               module_root=MODULE_ROOT)
    elif mode == "retained-tasks":
        from bridge.pyui_entry import stage_main_menu_hook
        from bridge.source_integration import stage_lifecycle_hook
        record = {"main_menu": stage_main_menu_hook(source_root, staging / "menu", source_use_verified=True),
                  "lifecycle": stage_lifecycle_hook(source_root, staging / "lifecycle", source_use_verified=True)}
    else:
        raise IntegrationError("choose exactly one bridge mode: process-exit, retained-tasks or none")
    patches = sorted(staging.rglob("*.patch"))
    require(patches, "bridge integration produced no review patch")
    return patches, record


def _installation(changes, bridge_mode):
    return {"scope": "reviewed SD-relative source and original-module paths only",
            "targets": [dict(item, card_relative_path=item["path"]) for item in changes],
            "original_module_root": MODULE_ROOT if bridge_mode == "process-exit" else None,
            "requires_offline_restorable_card": True,
            "requires_independent_qualified_runtime": True,
            "changes_installed_engine_or_internal_boot": False,
            "automatic_apply_available": False}


def _recovery():
    return {"method": "new-output restoration of exact backup preimages",
            "touches_user_saves": False, "restores_rootfs_or_boot": False,
            "whole_card_or_internal_restore_proved": False}


def assemble_private_candidate(source_root, output, *, source_review=None, bridge_mode="process-exit",
                               overlay_archive=None, public_key=None, include_state_session=False):
    """Apply reviewed changes to a new private scoped tree; no installed path changes."""
    _review(source_review)
    require(bridge_mode != "process-exit" or (overlay_archive is not None and public_key is not None),
            "process-exit source integration requires a verified original overlay containing its fixed runtime modules")
    output = _output(output, source_root)
    inventory = source_inventory(source_root, include_state_session=include_state_session)
    locked = _selected_patches(include_state_session)
    with tempfile.TemporaryDirectory(prefix=".integration-assembly-", dir=output.parent) as temporary:
        temporary = Path(temporary)
        staging, bridge = temporary / "content", temporary / "bridge"
        staging.mkdir(mode=0o700)
        bridge_patches, bridge_record = _bridge_patch(source_root, bridge, bridge_mode)
        patch_inputs = [(item["patch"], item["data"]) for item in locked]
        patch_inputs += [("bridge-" + str(i) + "-" + path.name, path.read_bytes()) for i, path in enumerate(bridge_patches)]
        allowed = {item["path"] for item in inventory} - set(LICENCES)
        modified = set()
        for name, raw in patch_inputs:
            require(len(raw) <= MAX_PATCH, "integration patch exceeds its budget")
            targets = _patch_paths(raw)
            require(set(targets) <= allowed, "bridge patch targets are outside the pinned inspected source inventory")
            modified.update(targets)
        require(len(modified) <= MAX_RECORDS, "candidate modifies too many sources")
        with SourceTree(source_root) as source:
            for name in sorted(modified):
                raw = source.read(name)
                expected = next(item for item in inventory if item["path"] == name)
                require(digest(raw) == expected["sha256"], "source changed after inventory: " + name)
                _write(staging, "tree/" + name, raw)
                _write(staging, "backup/" + name, raw)
            for index, name in enumerate(LICENCES):
                _write(staging, "notices/" + str(index) + "-" + Path(name).name, source.read(name))
        records = []
        for name, raw in patch_inputs:
            patch = temporary / ("apply-" + str(len(records)) + ".patch")
            patch.write_bytes(raw)
            for flags in (("--check",), ()):
                subprocess.run(["git", "-c", "core.autocrlf=false", "apply", *flags, str(patch)],
                               cwd=staging / "tree", check=True, capture_output=True, timeout=15)
            known = next((item for item in locked if item["patch"] == name), None)
            if known:
                with SourceTree(staging / "tree") as source:
                    require(digest(source.read(known["path"])) == known["patched_sha256"],
                            "patched source differs from the locked result: " + known["path"])
            _write(staging, "patches/" + name, raw)
            records.append({"patch": name, "patch_sha256": digest(raw), "paths": _patch_paths(raw)})
        changes = []
        with SourceTree(staging / "tree") as source:
            for name in sorted(modified):
                raw = source.read(name)
                patched = digest(raw)
                known = next((item for item in locked if item["path"] == name), None)
                if known and not any(name in _patch_paths(path.read_bytes()) for path in bridge_patches):
                    require(patched == known["patched_sha256"], "patched source differs from the locked result: " + name)
                if name.endswith(".py"):
                    compile(raw, name, "exec")
                elif name.endswith(".sh"):
                    subprocess.run(["sh", "-n", str(staging / "tree" / name)], check=True, capture_output=True, timeout=15)
                before = next(item["sha256"] for item in inventory if item["path"] == name)
                require(patched != before, "integration patch made no source change")
                changes.append({"path": name, "before_sha256": before, "after_sha256": patched})
        # Refresh every inspected input after external patch/syntax commands.
        require(source_inventory(source_root, include_state_session=include_state_session) == inventory,
                "source changed before candidate publication")
        manifest = _manifest("private-scoped-source-candidate", inventory, records,
                             source_review=source_review.evidence_reference, include_state_session=include_state_session)
        original_overlay = _copy_overlay(staging, overlay_archive, public_key, expand=bridge_mode == "process-exit")
        if bridge_mode == "process-exit":
            modules = bridge_record.get("required_project_modules")
            require(isinstance(modules, list) and modules, "bridge integration must identify its fixed original module requirements")
            for module in modules:
                overlay.relative_path(module)
                require(module.startswith("app/bridge/") or module.startswith("app/psp_shell/") or
                        module in SIGNED_TOOL_MODULES,
                        "bridge module requirement is outside the signed original app scope")
                require((staging / "tree" / PAYLOAD_ROOT / module).is_file(),
                        "signed original overlay is stale or lacks a required process-integration module: " + module)
        manifest.update(source_derived=True, source_use_reviewed=True, bridge_mode=bridge_mode,
                        bridge_review=bridge_record, changes=changes,
                        original_overlay=original_overlay,
                        installation=_installation(changes, bridge_mode), recovery=_recovery())
        _record(staging, manifest)
        require(not output.exists(), "output appeared during assembly; refusing replacement")
        os.rename(staging, output)
    return manifest


def verify_candidate(candidate, *, public_key=None):
    """Verify one retained private artifact; checksums are not publisher authority."""
    root = overlay.ensure_no_links(Path(candidate))
    with SourceTree(root) as tree:
        manifest = overlay.decode(tree.read("candidate.json", overlay.MAX_MANIFEST))
    require(isinstance(manifest, dict), "private manifest must be an object")
    checksum = manifest.pop("checksum", None)
    require(checksum == digest(overlay.canonical(manifest)), "private manifest checksum rejected")
    require(manifest.get("schema") == 1 and manifest.get("base_commit") == overlay.SPRUCE_COMMIT,
            "unsupported private candidate manifest")
    require(manifest.get("kind") in {"private-source-review-kit", "private-scoped-source-candidate", "private-source-restoration"},
            "unsupported private artifact kind")
    for field in ("device_activation", "hardware_qualified", "runtime_verified", "distribution_cleared",
                  "production_authenticity_claim", "rootfs_or_boot_modified", "installed_emulator_modified",
                  "saves_or_roms_included", "source_review_is_physical_qualification"):
        require(manifest.get(field) is False, "private artifact cannot mint qualification: " + field)
    require(manifest.get("artifact_files") == _artifact_inventory(root), "private artifact inventory changed")
    require(manifest.get("external_blockers") == [dict(code=code, requirement=description) for code, description in BLOCKERS],
            "private artifact cannot remove external qualification requirements")
    patches = manifest.get("patches")
    require(isinstance(patches, list) and 0 < len(patches) <= MAX_RECORDS, "invalid retained patch inventory")
    require(all(isinstance(item, dict) and {"patch", "patch_sha256"} <= set(item) for item in patches),
            "retained patch records require names and hashes")
    inventory = manifest.get("source_inventory")
    require(isinstance(inventory, list) and 0 < len(inventory) <= MAX_RECORDS and
            all(isinstance(item, dict) and {"path", "sha256", "git_blob", "size"} == set(item) for item in inventory),
            "invalid source preimage inventory")
    require(type(manifest.get("include_state_session")) is bool, "state-session source scope must be explicit")
    contracts, reliability = _source_contracts(), _selected_patches(manifest["include_state_session"])
    allowed = set(contracts) | {item["path"] for item in reliability}
    seen_sources = set()
    for item in inventory:
        name = overlay.relative_path(item["path"])
        require(name in allowed and name not in seen_sources, "source inventory is outside the locked integration scope")
        require(isinstance(item["sha256"], str) and overlay.SHA256.fullmatch(item["sha256"]) and
                type(item["size"]) is int and 0 < item["size"] <= MAX_SOURCE,
                "invalid source preimage fingerprint")
        seen_sources.add(name)
        if name in contracts:
            require(item["git_blob"] == contracts[name], "source inventory preimage differs from the pinned blob")
        known = next((patch for patch in reliability if patch["path"] == name), None)
        if known:
            require(item["sha256"] == known["base_sha256"], "source inventory preimage differs from locked reliability source")
    require(seen_sources == allowed, "source inventory omits a locked integration preimage")
    source_records = {item["path"]: item for item in inventory}
    expected_files = {"patches/" + overlay.relative_path(item["patch"]) for item in patches}
    expected_files |= {"notices/" + str(index) + "-" + Path(name).name for index, name in enumerate(LICENCES)}
    with SourceTree(root) as tree:
        for index, name in enumerate(LICENCES):
            raw = tree.read("notices/" + str(index) + "-" + Path(name).name)
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
            require(blob == LICENCES[name], "retained upstream licence differs from the pinned source")
        seen_patches, patch_targets = set(), set()
        for item in patches:
            require(item["patch"] not in seen_patches, "duplicate retained patch")
            seen_patches.add(item["patch"])
            raw = tree.read("patches/" + overlay.relative_path(item["patch"]), MAX_PATCH)
            require(digest(raw) == item["patch_sha256"], "retained patch hash mismatch")
            known = next((record for record in reliability if record["patch"] == item["patch"]), None)
            if known:
                require(raw == known["data"], "retained reliability patch differs from the locked patch")
            targets = set(_patch_paths(raw))
            require(targets <= allowed - set(LICENCES), "retained patch changes an unreviewed source")
            patch_targets.update(targets)
        require({item["patch"] for item in reliability} <= seen_patches,
                "private artifact omits a locked reliability patch")
        changes = manifest.get("changes", [])
        require(isinstance(changes, list) and len(changes) <= MAX_RECORDS, "invalid candidate changes")
        seen = set()
        for item in changes:
            require(isinstance(item, dict) and set(item) == {"path", "before_sha256", "after_sha256"},
                    "invalid candidate source change record")
            name = overlay.relative_path(item["path"])
            require(name not in seen and name in seen_sources and name not in LICENCES,
                    "candidate path is duplicate or outside observed source scope")
            seen.add(name)
            expected_files.update(("tree/" + name, "backup/" + name))
            before = tree.read("backup/" + name)
            after = tree.read("tree/" + name)
            observed = source_records[name]
            blob = hashlib.sha1(b"blob " + str(len(before)).encode("ascii") + b"\0" + before).hexdigest()
            require(digest(before) == observed["sha256"] and len(before) == observed["size"] and
                    blob == observed["git_blob"] and
                    (name not in contracts or blob == contracts[name]),
                    "restoration backup differs from the pinned source preimage: " + name)
            require(digest(before) == item["before_sha256"] and digest(after) == item["after_sha256"],
                    "candidate source or backup changed: " + name)
            if manifest["kind"] == "private-source-restoration":
                require(after == before, "restored source differs from its pinned backup preimage")
        if manifest["kind"] == "private-source-review-kit":
            require(not changes and manifest.get("source_derived") is False and
                    manifest.get("source_use_reviewed") is False and manifest.get("source_review_reference") is None and
                    seen_patches == {item["patch"] for item in reliability},
                    "a source review kit cannot include unapproved derivation or source-use qualification")
        else:
            require(seen == patch_targets, "candidate omits a retained patch's complete source scope")
            require(manifest.get("bridge_mode") in {"process-exit", "retained-tasks", "none"},
                    "private source candidate must select one reviewed bridge mode")
            require(len(patches) == len(reliability) + {"process-exit": 1, "retained-tasks": 2, "none": 0}[manifest["bridge_mode"]],
                    "candidate cannot combine alternative bridge integrations")
            require(manifest.get("installation") == _installation(changes, manifest["bridge_mode"]),
                    "private artifact cannot change its fixed installation scope or preconditions")
            require(manifest.get("recovery") == _recovery(), "private artifact cannot claim unproved recovery")
        original = manifest.get("original_overlay")
        if original is not None:
            require(public_key is not None, "original overlay verification needs the external trusted public key")
            raw = tree.read("original-overlay.tar", overlay.MAX_ARCHIVE)
            require(digest(raw) == original["sha256"], "retained original overlay hash mismatch")
            require(digest(overlay.load_key(public_key, 32)) == original["key_id"], "original overlay trust key differs")
            with overlay.VerifiedArchive(root / "original-overlay.tar", overlay.load_key(public_key, 32)):
                require(original.get("payload_expanded_in_private_tree") in (True, False), "original payload scope is missing")
            expected_files.add("original-overlay.tar")
            if original["payload_expanded_in_private_tree"]:
                with overlay.VerifiedArchive(root / "original-overlay.tar", overlay.load_key(public_key, 32)) as archive:
                    expected_files.update("tree/" + PAYLOAD_ROOT + "/" + item["path"] for item in archive.manifest["files"])
                    expected_files.update(("tree/" + PAYLOAD_ROOT + "/manifest.json", "tree/" + PAYLOAD_ROOT + "/manifest.sig"))
                    for item in archive.manifest["files"]:
                        expanded = tree.read("tree/" + PAYLOAD_ROOT + "/" + item["path"], overlay.MAX_FILE,
                                             allow_empty=True)
                        require(len(expanded) == item["size"] and digest(expanded) == item["sha256"],
                                "expanded original module differs from its signed payload: " + item["path"])
                    require(tree.read("tree/" + PAYLOAD_ROOT + "/manifest.json", overlay.MAX_MANIFEST) == archive.manifest_bytes and
                            tree.read("tree/" + PAYLOAD_ROOT + "/manifest.sig", 64) == archive.signature,
                            "expanded original manifest or signature differs from its verified archive")
    require(expected_files == {item["path"] for item in manifest["artifact_files"]},
            "private artifact contains a file outside the reviewed integration scope")
    return manifest


def restore_private_candidate(candidate, output, *, public_key=None):
    """Create a separate restored tree; refuse external edits and preserve inputs."""
    manifest = verify_candidate(candidate, public_key=public_key)
    require(manifest["kind"] == "private-scoped-source-candidate", "only an assembled candidate has restoration preimages")
    output = _output(output, candidate)
    changes = []
    with tempfile.TemporaryDirectory(prefix=".integration-restore-", dir=output.parent) as temporary:
        staging = Path(temporary) / "content"
        staging.mkdir(mode=0o700)
        with SourceTree(candidate) as source:
            for item in manifest["patches"]:
                name = "patches/" + item["patch"]
                _write(staging, name, source.read(name, MAX_PATCH))
            for item in manifest["changes"]:
                raw = source.read("backup/" + item["path"])
                _write(staging, "tree/" + item["path"], raw)
                _write(staging, "backup/" + item["path"], raw)
                changes.append(dict(item, after_sha256=item["before_sha256"]))
            for index, name in enumerate(LICENCES):
                relative = "notices/" + str(index) + "-" + Path(name).name
                _write(staging, relative, source.read(relative))
            if manifest.get("original_overlay"):
                raw = source.read("original-overlay.tar", overlay.MAX_ARCHIVE)
                original = Path(temporary) / "original.tar"
                original.write_bytes(raw)
                retained = _copy_overlay(staging, original, public_key,
                                         expand=manifest["original_overlay"].get("payload_expanded_in_private_tree") is True)
                require(retained == manifest["original_overlay"], "retained original overlay changed during restoration")
        restored = dict(manifest, kind="private-source-restoration", changes=changes,
                        installation=dict(manifest["installation"],
                                          targets=[dict(item, card_relative_path=item["path"]) for item in changes]),
                        restored_from=digest(overlay.canonical(manifest)))
        _record(staging, restored)
        require(verify_candidate(candidate, public_key=public_key) == manifest, "candidate changed before restoration publication")
        require(not output.exists(), "restoration output appeared; refusing replacement")
        os.rename(staging, output)
    return restored


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("prepare", help="retain review kit without deriving source")
    plan.add_argument("--source-root", required=True, type=Path)
    plan.add_argument("--output", required=True, type=Path)
    plan.add_argument("--overlay", type=Path)
    plan.add_argument("--public-key", type=Path)
    plan.add_argument("--include-state-session", action="store_true", help="retain the separate locked optional PSP argv patch")
    verify = sub.add_parser("verify")
    verify.add_argument("candidate", type=Path)
    verify.add_argument("--public-key", type=Path)
    restore = sub.add_parser("restore-private")
    restore.add_argument("candidate", type=Path)
    restore.add_argument("--output", required=True, type=Path)
    restore.add_argument("--public-key", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            result = prepare_review_kit(args.source_root, args.output, overlay_archive=args.overlay, public_key=args.public_key,
                                        include_state_session=args.include_state_session)
        elif args.action == "verify":
            result = verify_candidate(args.candidate, public_key=args.public_key)
        else:
            result = restore_private_candidate(args.candidate, args.output, public_key=args.public_key)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("integration: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
