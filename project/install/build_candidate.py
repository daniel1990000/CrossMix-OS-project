#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compose the private SD-relative integration and its restoration preimages.

Run on the Linux development workstation, not on the handheld or Windows.
No card is written and no device/profile configuration is enabled.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import unicodedata

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from integration import release

PERMISSION_PATH = PROJECT / "evidence/completion-20261023/owner-permission.json"
PERMISSION_SHA256 = "e3830eb1a104eab163afff99e12dff472762447c7a314be126875ce841900b40"
BASE_NAME = "spruceV4.5.4.7z"
BASE_SIZE = 1652634074
BASE_SHA256 = "4623f1cd824ac1d01e7663d11ca40a8d3ad874c5f071e692f4392957d2159cfd"
BASE_URL = "https://github.com/spruceUI/spruceOS/releases/download/v4.5.4/" + BASE_NAME


def regular_input(path):
    path = Path(path).absolute()
    release.overlay.ensure_no_links(path.parent)
    release.require(stat.S_ISREG(path.lstat().st_mode), "input must be a non-link regular file")
    return path


def sha256_file(path):
    path = regular_input(path)
    before = path.lstat()
    release.require(stat.S_ISREG(before.st_mode), "input must be a regular file")
    result = hashlib.sha256()
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    after = path.lstat()
    release.require(all(getattr(before, key) == getattr(after, key) for key in
                        ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")),
                    "input changed while hashing")
    return result.hexdigest()


def retained_source_review():
    """Use the already-reviewed owner record, never arbitrary card JSON."""
    release.require(sha256_file(PERMISSION_PATH) == PERMISSION_SHA256,
                    "retained private source-use decision changed; review its scope")
    return release.SourceUseReview(
        source_commit=release.overlay.SPRUCE_COMMIT,
        evidence_reference="owner-confirmed-private-source-use:sha256:" + PERMISSION_SHA256)


def check_base_archive(path):
    path = regular_input(path)
    release.require(path.stat().st_size == BASE_SIZE, "pinned base archive size mismatch")
    release.require(sha256_file(path) == BASE_SHA256, "pinned base archive SHA256 mismatch")
    return {"name": BASE_NAME, "bytes": BASE_SIZE, "sha256": BASE_SHA256,
            "url": BASE_URL, "bytes_verified": True, "extracted": False, "archive_payload_executed": False}


def require_disabled_selectors(tree):
    """Reject an activated payload; inspect syntax without importing it."""
    for relative in ("app/bridge/qualified_runtime.py", "app/bridge/experimental_runtime.py"):
        path = tree / release.PAYLOAD_ROOT / relative
        root = ast.parse(path.read_bytes(), filename=relative)
        matches = [item for item in root.body if isinstance(item, ast.FunctionDef)
                   and item.name == "configuration"]
        release.require(len(matches) == 1, "fixed runtime selector is missing or ambiguous")
        function = matches[0]
        body = list(function.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            body.pop(0)
        release.require(not function.decorator_list and len(body) == 1 and
                        isinstance(body[0], ast.Return) and
                        isinstance(body[0].value, ast.Constant) and body[0].value.value is None,
                        "offline preparation requires the shipped unavailable runtime selector")


def deployment_files(candidate, source_root, manifest):
    changed = {item["path"]: item for item in manifest["changes"]}
    tree = candidate / "tree"
    result = []
    for path in sorted(tree.rglob("*")):
        release.require(not path.is_symlink(), "candidate contains a symlink")
        if path.is_dir():
            continue
        release.require(path.is_file(), "candidate contains a special file")
        name = path.relative_to(tree).as_posix()
        release.overlay.relative_path(name)
        operation = changed.get(name)
        if operation is not None:
            original = source_root / name
            mode = stat.S_IMODE(original.stat().st_mode)
            release.require(sha256_file(original) == operation["before_sha256"], "source changed before plan")
            before = operation["before_sha256"]
            after = operation["after_sha256"]
        else:
            release.require(name.startswith(release.PAYLOAD_ROOT + "/"), "unreviewed new source path")
            mode = 0o644
            before = None
            after = sha256_file(path)
        release.require(sha256_file(path) == after, "candidate changed before plan")
        result.append({"card_relative_path": name, "operation": "replace-exact-preimage" if before else "add-only-if-absent",
                       "before_sha256": before, "after_sha256": after,
                       "bytes": path.stat().st_size, "intended_posix_mode": format(mode, "04o")})
    return result


def tree_inventory(root):
    """Inventory the newly extracted private tree, never user data."""
    result = []
    total = 0
    seen = set()
    for number, path in enumerate(sorted(root.rglob("*"))):
        release.require(number < 250000, "base exceeds preparation entry budget")
        release.require(not path.is_symlink(), "base contains unsupported symlink: " + str(path.relative_to(root)))
        name = path.relative_to(root).as_posix()
        release.require(name.casefold() not in seen, "case-colliding full-base path: " + name)
        seen.add(name.casefold())
        # The hash-pinned full distribution includes public CA .pem bundles.
        # Original-overlay secret-name restrictions must not classify those
        # untouched upstream files as project payload. Keep structural checks.
        parts = name.split("/")
        reserved = {"con", "prn", "aux", "nul"} | {"com" + str(value) for value in range(1, 10)} | {"lpt" + str(value) for value in range(1, 10)}
        release.require(0 < len(name.encode("utf-8")) <= 4096 and
                        not PurePosixPath(name).is_absolute() and
                        all(part and part not in {".", ".."} and not part.endswith((" ", ".")) for part in parts) and
                        all(part.split(".", 1)[0].casefold() not in reserved for part in parts) and
                        not any(character in name for character in ("\\", "\x00", ":", "<", ">", '"', "|", "?", "*")) and
                        not any(ord(character) < 32 or ord(character) == 127 for character in name) and
                        unicodedata.normalize("NFC", name) == name,
                        "unsafe full-base path: " + name)
        if path.is_dir():
            continue
        release.require(path.is_file(), "base contains a special file")
        size = path.stat().st_size
        total += size
        release.require(total <= 20 * 1024**3, "base exceeds preparation byte budget")
        result.append({"path": name, "bytes": size, "sha256": sha256_file(path),
                       "mode": format(stat.S_IMODE(path.stat().st_mode), "04o")})
    return result


def materialize_base(staging, base_archive, extractor, candidate, files):
    """Extract pinned bytes and compose only in a fresh workstation directory."""
    extractor = regular_input(extractor)
    release.require(os.access(extractor, os.X_OK), "trusted 7-Zip extractor must be executable")
    prepared = staging / "prepared-card"
    prepared.mkdir(mode=0o700)
    extraction = subprocess.run([str(extractor), "x", "-y", "-o" + str(prepared), str(base_archive)],
                                capture_output=True, timeout=900, check=False)
    release.require(extraction.returncode == 0, "pinned base extraction failed (code " + str(extraction.returncode) + ")")
    before = tree_inventory(prepared)
    original = {item["path"]: item for item in before}
    # Recheck every changed source before making any private base modification.
    for item in files:
        path = prepared / item["card_relative_path"]
        if item["before_sha256"] is not None:
            observed = original.get(item["card_relative_path"])
            release.require(observed is not None and observed["sha256"] == item["before_sha256"],
                            "full base differs from exact patch preimage: " + item["card_relative_path"])
        else:
            release.require(not path.exists(), "full base conflicts with new integration file")
    for item in files:
        name = item["card_relative_path"]
        path = prepared / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (candidate / "tree" / name).read_bytes()
        release.require(hashlib.sha256(raw).hexdigest() == item["after_sha256"], "candidate changed during base composition")
        mode = int(original[name]["mode"], 8) if name in original else 0o644
        with path.open("wb" if name in original else "xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        path.chmod(mode)
    after = tree_inventory(prepared)
    resulting = {item["path"]: item for item in after}
    expected_changes = {item["card_relative_path"]: item for item in files}
    release.require(set(resulting) == set(original) | set(expected_changes), "unexpected full-base file additions/removals")
    for name, item in original.items():
        if name not in expected_changes:
            release.require(item == resulting[name], "unselected base file changed: " + name)
    for name, item in expected_changes.items():
        release.require(resulting[name]["sha256"] == item["after_sha256"], "composed payload readback mismatch")
    require_disabled_selectors(prepared)
    before_bytes = json.dumps(before, indent=2, sort_keys=True).encode() + b"\n"
    after_bytes = json.dumps(after, indent=2, sort_keys=True).encode() + b"\n"
    release._write(staging, "base-files-before.json", before_bytes)
    release._write(staging, "prepared-card-files.json", after_bytes)
    return {"directory": "prepared-card", "base_files": len(before), "result_files": len(after),
            "unselected_base_files_unchanged": True,
            "base_inventory_sha256": hashlib.sha256(before_bytes).hexdigest(),
            "prepared_inventory_sha256": hashlib.sha256(after_bytes).hexdigest(),
            "extractor_sha256": sha256_file(extractor), "activated": False,
            "native_engines_unchanged": True, "boot_tested": False}


def build(source_root, overlay_archive, public_key, output, *, base_archive=None, extractor=None):
    source_root = release.overlay.ensure_no_links(Path(source_root))
    overlay_archive = regular_input(overlay_archive)
    public_key = regular_input(public_key)
    output = release._output(output, source_root)
    release.require(not str(source_root).startswith("/mnt/SDCARD") and
                    not str(output).startswith("/mnt/SDCARD"), "use offline workstation paths, never the device card")
    review = retained_source_review()
    release.require(extractor is None or base_archive is not None, "full base composition requires the pinned archive")
    base = check_base_archive(base_archive) if base_archive else {
        "name": BASE_NAME, "bytes": BASE_SIZE, "sha256": BASE_SHA256,
        "url": BASE_URL, "bytes_verified": False, "extracted": False, "archive_payload_executed": False}
    inputs = {"overlay_sha256": sha256_file(overlay_archive),
              "public_key_sha256": sha256_file(public_key)}
    with tempfile.TemporaryDirectory(prefix=".smartpro-install-preparation-", dir=output.parent) as temporary:
        staging = Path(temporary) / "content"
        staging.mkdir(mode=0o700)
        candidate = staging / "candidate"
        release.assemble_private_candidate(source_root, candidate, source_review=review,
                                          bridge_mode="process-exit", overlay_archive=overlay_archive,
                                          public_key=public_key, include_state_session=False)
        manifest = release.verify_candidate(candidate, public_key=public_key)
        require_disabled_selectors(candidate / "tree")
        restored = release.restore_private_candidate(candidate, staging / "rollback", public_key=public_key)
        release.verify_candidate(staging / "rollback", public_key=public_key)
        for item in restored["changes"]:
            release.require(item["before_sha256"] == item["after_sha256"], "restoration did not recover exact preimage")
        files = deployment_files(candidate, source_root, manifest)
        full_base = materialize_base(staging, base_archive, extractor, candidate, files) if extractor else None
        if extractor:
            check_base_archive(base_archive)
            base["extracted"] = True
        release.require(sha256_file(overlay_archive) == inputs["overlay_sha256"] and
                        sha256_file(public_key) == inputs["public_key_sha256"], "overlay or key changed during preparation")
        release.require(release.verify_candidate(candidate, public_key=public_key) == manifest,
                        "candidate changed during restoration rehearsal")
        plan = {
            "schema": 1, "kind": "private-offline-integration-preparation",
            "target": "original TrimUI Smart Pro TG5040", "base": base,
            "source_commit": release.overlay.SPRUCE_COMMIT,
            "source_review_reference": review.evidence_reference,
            "candidate_manifest_sha256": sha256_file(candidate / "candidate.json"),
            "rollback_manifest_sha256": sha256_file(staging / "rollback/candidate.json"),
            "inputs": inputs, "files": files,
            "full_base_composition": full_base,
            "source_contracts_verified": True, "signed_overlay_verified": True,
            "source_preimages_restored_on_host": True,
            "physical_restore_tested": False, "device_activation": False,
            "runtime_configuration_available": False, "copy_to_card_authorized_by_this_plan": False,
            "native_engine_replaced": False, "roms_or_saves_migrated": False,
            "full_bootable_image": False, "public_distribution_cleared": False,
            "required_before_card_application": [
                "Owner card and internal-file preservation with independent recovery access",
                "Actual TG5040 firmware, source/runtime, display/input and process observations",
                "Separately reviewed fixed experimental runtime and bounded view-only case",
                "Review exact card preimages, destination conflicts and rollback procedure"],
        }
        raw = json.dumps(plan, indent=2, sort_keys=True).encode() + b"\n"
        release._write(staging, "deploy-plan.json", raw)
        release._write(staging, "verification.pub", public_key.read_bytes())
        release._write(staging, "READ-FIRST.txt", (
            "PRIVATE OFFLINE INSTALL PREPARATION - NOT A BOOTABLE CARD IMAGE\n\n"
            "candidate/tree contains exact-source patches and the verified custom frontend.\n"
            "rollback/tree retains exact original source preimages for those patches.\n"
            "When requested, prepared-card is a full private base-plus-integration file tree.\n"
            "Neither directory is a complete OS. Do not copy these onto your current card.\n"
            "Both runtime selectors remain unavailable. Device activation has not occurred.\n"
            "deploy-plan.json binds the proposed SD-relative files and required preimages.\n"
            "Without prepared-card, prepare the independently pinned base separately.\n"
            "No games, saves, firmware, internal startup files or engines were modified.\n"
            "Host source restoration is not physical-card or internal-firmware restoration.\n"
            "Keep this derivative private; public distribution is not cleared here.\n"
        ).encode())
        release.require(not output.exists(), "output appeared during build")
        os.rename(staging, output)
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-archive", type=Path)
    parser.add_argument("--extractor", type=Path, help="trusted Linux 7zz executable; also compose a private full base tree")
    args = parser.parse_args(argv)
    try:
        result = build(args.source_root, args.overlay, args.public_key, args.output,
                       base_archive=args.base_archive, extractor=args.extractor)
        print(json.dumps({"output": str(args.output), "prepared_files": len(result["files"]),
                          "device_activation": False, "full_bootable_image": False}, indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("Preparation stopped: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
