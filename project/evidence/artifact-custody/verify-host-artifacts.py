#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Recheck a retained CI ZIP against independently recorded identities.

No archive member is installed or executed. The supplied artifact digest must
come from the prior receipt/provider, not be learned from the downloaded copy.
The development public key verifies integrity, not production authorization.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import zipfile

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "packaging"))
import overlay


def zip_entries(data):
    overlay.require(len(data) <= 32 * 1024**2, "ZIP exceeds custody verification budget")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries, total = {}, 0
        overlay.require(len(archive.infolist()) <= 4096, "too many ZIP entries")
        for item in archive.infolist():
            overlay.relative_path(item.filename)
            overlay.require(item.filename.casefold() not in {x.casefold() for x in entries},
                            "duplicate ZIP path")
            overlay.require(stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG),
                            "ZIP member is not a regular file")
            total += item.file_size
            overlay.require(not item.is_dir() and not item.flag_bits & 1 and
                            item.file_size <= 16 * 1024**2 and total <= 64 * 1024**2,
                            "ZIP member exceeds budget or is encrypted/directory")
            entries[item.filename] = archive.read(item)
        return entries


def verify(path, expected_sha256, expected_frontend, expected_inventory):
    path = Path(path)
    overlay.require(path.is_file() and not path.is_symlink(), "regular artifact file required")
    overlay.require(path.stat().st_size <= 32 * 1024**2, "artifact exceeds budget")
    data = path.read_bytes()
    overlay.require(overlay.digest(data) == expected_sha256, "outer artifact hash differs")
    entries = zip_entries(data)
    inner = {}
    for line in entries["development/SHA256SUMS"].decode("ascii").splitlines():
        expected, name = line.split("  ", 1)
        overlay.relative_path(name)
        overlay.require("/" not in name and name not in inner and overlay.SHA256.fullmatch(expected),
                        "invalid inner checksum entry")
        overlay.require(overlay.digest(entries["development/" + name]) == expected,
                        "inner checksum differs: " + name)
        inner[name] = expected
    overlay.require(len(inner) == 8 and {"development/" + x for x in inner} | {
        "development/SHA256SUMS", "certification.json", "host-preview.json", "library.png"
    } == set(entries), "CI artifact inventory differs")
    certification = overlay.decode(entries["certification.json"])
    totals = certification["totals"]
    overlay.require(certification["successful"] is True and totals["passed"] == totals["tests_run"] > 0
                    and all(totals[k] == 0 for k in ("failures", "errors", "skipped",
                                                    "expected_failures", "unexpected_successes")),
                    "artifact does not retain a complete passing host certification")
    report = overlay.decode(entries["development/build-report.json"])
    source = overlay.decode(entries["development/release-source.json"])
    frontend = {"commit": expected_frontend, "working_tree_modified": False}
    selection = report["release_selection"]
    overlay.require(source["frontend"] == selection["frontend"] == frontend,
                    "frontend identity differs")
    inventory = source["source_inventory"]
    overlay.require(overlay.digest(overlay.canonical(inventory)) == source["source_inventory_sha256"]
                    == selection["source_inventory_sha256"] == expected_inventory,
                    "source inventory differs")
    release = report["release_id"]
    exported = zip_entries(entries["development/" + release + "-original-source.zip"])
    actual = [{"path": name.removeprefix("smartpro-original-source/"), "sha256": overlay.digest(raw),
               "size": len(raw)} for name, raw in sorted(exported.items())
              if name != "smartpro-original-source/metadata/release-source.json"]
    overlay.require(actual == inventory and overlay.decode(
        exported["smartpro-original-source/metadata/release-source.json"]) == source,
        "exported source bytes differ from retained source inventory")
    descriptor = selection["descriptor"]
    overlay.require(descriptor["selected_native_binaries"] == descriptor["selected_upstream_patches"] == []
                    and report["device_activation_qualified"] is False
                    and report["production_authenticity_claim"] is False
                    and report["device_gates"] == descriptor["qualification"] == {
                        "hardware_qualified": False, "runtime_verified": False, "source_use_verified": False},
                    "artifact exceeds original-only host scope")
    with tempfile.TemporaryDirectory(prefix="trimui-custody-verification-") as directory:
        package = Path(directory) / "preview.tar"
        package.write_bytes(entries["development/" + release + ".tar"])
        public = entries["development/development-verification.pub"]
        with overlay.VerifiedArchive(package, public) as verified:
            overlay.require(len(verified.manifest["files"]) == report["payload_files"],
                            "signed payload count differs")
            signed = overlay.decode(verified.archive.extractfile(
                verified.members["payload/metadata/development-release.json"]).read())
            overlay.require(signed["release_selection"] == selection
                            and signed["device_activation_qualified"] is False,
                            "signed source/qualification metadata differs")
    return {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "artifact_sha256": expected_sha256,
            "artifact_size_bytes": len(data), "frontend": frontend, "totals": totals,
            "inner_artifact_sha256": inner, "source_inventory_files": len(inventory),
            "source_inventory_sha256": expected_inventory, "payload_files": report["payload_files"],
            "signature_and_payload_inventory_verified": True, "source_export_bytes_verified": True,
            "hardware_qualified": False, "production_authenticity_claim": False,
            "private_native_artifact_custody_verified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--frontend", required=True)
    parser.add_argument("--source-inventory", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.archive, args.sha256, args.frontend, args.source_inventory), indent=2))
