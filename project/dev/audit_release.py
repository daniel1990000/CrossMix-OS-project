#!/usr/bin/env python3
"""Reproduce the downloaded-base/source correspondence check; never run payloads.

Install host-only py7zr==0.22.0 to inspect the release. The output proves only
the named files and complete archive digest, not the physical-device behavior.
SPDX-License-Identifier: MIT
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

EXPECTED = "4623f1cd824ac1d01e7663d11ca40a8d3ad874c5f071e692f4392957d2159cfd"
COMMIT = "d45ff8dfe5756147522b04ae5863d17a90e88b54"
BINARY = "Emu/PSP/PPSSPPSDL_TrimUI"
BINARY_BLOB = "509ffbd9ba3874c05ae3b470d77cab5299d85c4e"
FILES = ("App/PyUI/main-ui/menus/main_menu.py", "App/PyUI/main-ui/devices/miyoo_trim_common.py",
         "spruce/scripts/helperFunctions.sh", "App/-OTA/downloader.sh", "App/PyUI/py-ui-config.json",
         "spruce/scripts/principal.sh", "spruce/scripts/platform/SmartPro.cfg",
         "App/PyUI/main-ui/LICENSE.md", "App/PyUI/LICENSE.md", "LICENSE")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit(archive, source_root):
    import py7zr
    actual = sha256(archive)
    if actual != EXPECTED:
        raise ValueError("The full spruce archive does not match the selected release digest")
    result = []
    with tempfile.TemporaryDirectory(prefix="spruce-source-audit-") as temporary:
        root = Path(temporary)
        with py7zr.SevenZipFile(archive) as source:
            names = set(source.getnames())
            if not set((*FILES, BINARY)) <= names:
                raise ValueError("The selected release lacks required integration files")
            source.extract(path=root, targets=[*FILES, BINARY])
        for relative in FILES:
            target = root / relative
            target.resolve(strict=True).relative_to(root)
            if target.is_symlink() or not target.is_file():
                raise ValueError("A selected integration file is not regular")
            archive_digest, source_digest = sha256(target), sha256(Path(source_root) / relative)
            result.append({"path": relative, "archive_sha256": archive_digest,
                           "source_sha256": source_digest, "matches": archive_digest == source_digest})
        binary = (root / BINARY).read_bytes()
        git_blob = hashlib.sha1(b"blob " + str(len(binary)).encode("ascii") + b"\0" + binary).hexdigest()
        bundled = {"path": BINARY, "size": len(binary), "sha256": hashlib.sha256(binary).hexdigest(),
                   "git_blob": git_blob, "matches_locked_git_blob": git_blob == BINARY_BLOB,
                   "embedded_version_hint": "v1.20.3" if b"v1.20.3\0" in binary else None,
                   "exact_compiled_source_correspondence_verified": False,
                   "independent_native_menu_extension_present": False}
    return {"schema": 1, "evidence": "downloaded-release-archive-and-pinned-source", "release": "v4.5.4",
            "expected_sha256": EXPECTED, "actual_sha256": actual, "source_commit": COMMIT,
            "selected_files": result, "bundled_ppsspp": bundled,
            "all_release_file_correspondence_verified": False, "device_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = audit(args.archive, args.source_root)
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if (all(item["matches"] for item in report["selected_files"]) and
                 report["bundled_ppsspp"]["matches_locked_git_blob"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
