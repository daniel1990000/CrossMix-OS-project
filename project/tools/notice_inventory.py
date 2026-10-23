#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Inventory exact archive bytes and notice candidates without extracting code.

Notice-name/header matches identify material for human review. They never infer
permission, compiled membership, source-use completion or distribution clearance.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile
import zipfile

MAX_ARCHIVE = 1024 ** 3
MAX_MEMBERS = 100_000
MAX_MEMBER = 128 * 1024 ** 2
MAX_TOTAL = 4 * 1024 ** 3
HEADER_BYTES = 8192
NOTICE_NAME = re.compile(r"(?:^|[._-])(?:licen[cs]e|copying|copyright|notice|ofl|authors)(?:[._-]|$)", re.I)
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hpp", ".py", ".sh"}
SIGNALS = {
    "spdx": re.compile(rb"SPDX-License-Identifier\s*:", re.I),
    "copyright": re.compile(rb"copyright\s*(?:\(c\)|[0-9])", re.I),
    "permission-grant": re.compile(rb"permission is hereby granted", re.I),
    "gnu-license-reference": re.compile(rb"GNU (?:LESSER |LIBRARY |GENERAL )*(?:PUBLIC LICENSE|GPL)", re.I),
    "public-domain-reference": re.compile(rb"public domain|creativecommons.org/publicdomain/zero", re.I),
    "all-rights-reserved": re.compile(rb"all rights reserved", re.I),
}


class InventoryError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InventoryError(message)


def canonical_name(value):
    require(isinstance(value, str) and value and len(value.encode()) <= 4096 and
            not value.startswith("/") and "\\" not in value and
            not any(ord(c) < 32 or ord(c) == 127 for c in value), "unsafe archive member name")
    # Tar writers sometimes use ./ or a final slash for directories.
    name = value.removeprefix("./").rstrip("/")
    if name in ("", "."):
        return "."
    require(name == str(PurePosixPath(name)) and ".." not in PurePosixPath(name).parts,
            "unsafe archive member name")
    return name


def _fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode)


def _archive_fd(path):
    path = Path(path).absolute()
    require(".." not in path.parts, "parent traversal is unavailable")
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        leaf = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
    finally:
        os.close(fd)
    try:
        info = os.fstat(leaf)
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= MAX_ARCHIVE,
                "bounded regular archive required")
        return leaf, info
    except BaseException:
        os.close(leaf)
        raise


def _file_record(stream, name, expected_size, *, remaining):
    require(type(expected_size) is int and 0 <= expected_size <= MAX_MEMBER and expected_size <= remaining,
            "uncompressed archive member exceeds budget")
    digest, head, size = hashlib.sha256(), bytearray(), 0
    while True:
        block = stream.read(min(65536, expected_size + 1 - size))
        if not block:
            break
        size += len(block)
        require(size <= expected_size, "archive member size changed")
        digest.update(block)
        if len(head) < HEADER_BYTES:
            head.extend(block[:HEADER_BYTES - len(head)])
    require(size == expected_size, "short archive member")
    row = {"path": name, "size_bytes": size, "sha256": digest.hexdigest()}
    base = PurePosixPath(name).name
    named = bool(NOTICE_NAME.search(base)) and PurePosixPath(name).suffix.lower() not in SOURCE_SUFFIXES
    signals = [key for key, pattern in SIGNALS.items() if pattern.search(head)]
    return row, named, signals


def inventory(path, *, expected_sha256=None):
    """Hash archive plus complete regular-file inventory; never follow links."""
    if expected_sha256 is not None:
        require(isinstance(expected_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha256),
                "exact expected SHA-256 required")
    fd, before = _archive_fd(path)
    rows, notices, signal_counts, seen, total = [], [], Counter(), set(), 0
    try:
        with os.fdopen(os.dup(fd), "rb") as raw:
            digest = hashlib.sha256()
            observed_bytes = 0
            for block in iter(lambda: raw.read(1024 * 1024), b""):
                observed_bytes += len(block)
                require(observed_bytes <= before.st_size, "archive grew during hashing")
                digest.update(block)
            require(observed_bytes == before.st_size, "archive shrank during hashing")
            archive_hash = digest.hexdigest()
        require(expected_sha256 is None or archive_hash == expected_sha256, "archive digest differs")

        def add(name, size, kind, source=None, link=None):
            nonlocal total
            name = canonical_name(name)
            require(name not in seen, "duplicate normalized archive member")
            require(len(seen) < MAX_MEMBERS, "archive member count exceeds budget")
            seen.add(name)
            if kind == "file":
                row, named, signals = _file_record(source, name, size, remaining=MAX_TOTAL - total)
                total += row["size_bytes"]
                rows.append(row)
                for signal in signals:
                    signal_counts[signal] += 1
                if named:
                    notices.append({**row, "header_signals": signals, "empty": size == 0,
                                    "classification": "named-notice-candidate"})
            elif kind == "link":
                # Link text is metadata; it is never resolved or extracted.
                require(isinstance(link, str) and len(link.encode()) <= 4096, "invalid link metadata")
                rows.append({"path": name, "kind": "unfollowed-link",
                             "link_text_sha256": hashlib.sha256(link.encode()).hexdigest()})
            elif kind != "directory":
                raise InventoryError("archive contains a special file")

        with os.fdopen(os.dup(fd), "rb") as raw:
            raw.seek(0)
            if zipfile.is_zipfile(raw):
                raw.seek(0)
                with zipfile.ZipFile(raw) as archive:
                    for member in archive.infolist():
                        require(not member.flag_bits & 1, "encrypted archive unsupported")
                        mode = member.external_attr >> 16
                        if member.is_dir():
                            add(member.filename, 0, "directory")
                        elif stat.S_ISLNK(mode):
                            require(member.file_size <= 4096, "link metadata exceeds budget")
                            with archive.open(member) as stream:
                                link = stream.read(4097).decode("utf-8")
                            add(member.filename, 0, "link", link=link)
                        else:
                            require(not stat.S_IFMT(mode) or stat.S_ISREG(mode), "archive special file unsupported")
                            with archive.open(member) as stream:
                                add(member.filename, member.file_size, "file", source=stream)
            else:
                raw.seek(0)
                with tarfile.open(fileobj=raw, mode="r|*") as archive:
                    for member in archive:
                        if member.isfile():
                            with archive.extractfile(member) as stream:
                                add(member.name, member.size, "file", source=stream)
                        elif member.isdir():
                            add(member.name, 0, "directory")
                        elif member.issym() or member.islnk():
                            add(member.name, 0, "link", link=member.linkname)
                        else:
                            add(member.name, 0, "special")
        require(_fingerprint(before) == _fingerprint(os.fstat(fd)), "archive changed during inventory")
    finally:
        os.close(fd)
    rows.sort(key=lambda row: row["path"])
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return {"schema": 1, "kind": "archive-notice-candidate-inventory", "archive_sha256": archive_hash,
            "archive_size_bytes": before.st_size, "expected_archive_hash_matched": expected_sha256 is not None,
            "members_seen": len(seen), "regular_files": sum("sha256" in row for row in rows),
            "unfollowed_links": sum(row.get("kind") == "unfollowed-link" for row in rows),
            "regular_file_bytes": total, "file_inventory_sha256": hashlib.sha256(encoded).hexdigest(),
            "named_notice_candidates": sorted(notices, key=lambda row: row["path"]),
            "header_signal_file_counts": dict(sorted(signal_counts.items())),
            "header_scan_limit_bytes": HEADER_BYTES, "distribution_cleared": False,
            "source_use_verified": False, "compiled_membership_established": False,
            "limits": ["Notice names and header signals are discovery aids, not licence decisions.",
                       "Inline terms outside the scanned prefix and differently named notices can remain undiscovered.",
                       "An archive inventory does not establish binary link membership or corresponding-source completeness."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inventory(args.archive, expected_sha256=args.expected_sha256), sort_keys=True, indent=2))
        return 0
    except (InventoryError, OSError, ValueError, tarfile.TarError, zipfile.BadZipFile):
        print("notice inventory failed: invalid, changed or unavailable archive", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
