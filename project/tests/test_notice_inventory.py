# SPDX-License-Identifier: MIT
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import notice_inventory as notices


class NoticeInventoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="notice-inventory-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def zip(self, entries, name="source.zip"):
        path = self.root / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for key, value in entries:
                archive.writestr(key, value)
        return path

    def tar(self, entries, name="source.tar.gz"):
        path = self.root / name
        with tarfile.open(path, "w:gz") as archive:
            for key, content, kind in entries:
                member = tarfile.TarInfo(key)
                if kind == "file":
                    member.size = len(content)
                    archive.addfile(member, io.BytesIO(content))
                elif kind == "link":
                    member.type, member.linkname = tarfile.SYMTYPE, content.decode()
                    archive.addfile(member)
                else:
                    member.type = tarfile.FIFOTYPE
                    archive.addfile(member)
        return path

    def test_zip_notice_hashes_and_code_headers_remain_discovery_only(self):
        path = self.zip([("src/LICENSE", b"Permission is hereby granted\n"),
                         ("src/NOTICE.cpp", b"// Copyright (c) 2026 example\n"),
                         ("src/font/OFL.txt", b"font terms\n"),
                         ("src/build/LICENSE", b"")])
        report = notices.inventory(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertTrue(report["expected_archive_hash_matched"])
        self.assertEqual(report["regular_files"], 4)
        self.assertEqual(len(report["named_notice_candidates"]), 3)
        self.assertEqual(report["header_signal_file_counts"]["copyright"], 1)
        self.assertFalse(report["distribution_cleared"])
        self.assertFalse(report["source_use_verified"])
        self.assertFalse(report["compiled_membership_established"])
        row = next(x for x in report["named_notice_candidates"] if x["path"] == "src/build/LICENSE")
        self.assertTrue(row["empty"])

    def test_tar_and_zip_have_same_complete_file_inventory(self):
        entries = [("src/LICENSE", b"notice"), ("src/a.py", b"# SPDX-License-Identifier: MIT\n")]
        first = notices.inventory(self.zip(entries))
        second = notices.inventory(self.tar([(name, content, "file") for name, content in reversed(entries)]))
        self.assertEqual(first["file_inventory_sha256"], second["file_inventory_sha256"])
        self.assertNotEqual(first["archive_sha256"], second["archive_sha256"])

    def test_link_metadata_is_recorded_without_following_target(self):
        path = self.tar([("source-link", b"/private/missing/target", "link")])
        report = notices.inventory(path)
        self.assertEqual(report["unfollowed_links"], 1)
        self.assertEqual(report["regular_files"], 0)
        self.assertNotIn("private", json.dumps(report))

    def test_absolute_traversal_and_duplicate_normalized_paths_are_refused(self):
        for bad in ("/absolute/LICENSE", "../LICENSE", "src/../LICENSE", "src\\LICENSE"):
            with self.subTest(name=bad), self.assertRaises(notices.InventoryError):
                notices.inventory(self.zip([(bad, b"x")], name="bad.zip"))
        path = self.tar([("./source/LICENSE", b"one", "file"), ("source/LICENSE", b"two", "file")])
        with self.assertRaises(notices.InventoryError):
            notices.inventory(path)

    def test_wrong_expected_hash_is_rejected_before_notice_interpretation(self):
        path = self.zip([("LICENSE", b"hello")])
        with self.assertRaises(notices.InventoryError):
            notices.inventory(path, expected_sha256="0" * 64)
        with self.assertRaises(notices.InventoryError):
            notices.inventory(path, expected_sha256="latest")

    def test_special_files_and_symlink_input_archives_are_refused(self):
        path = self.tar([("fifo", b"", "special")])
        with self.assertRaises(notices.InventoryError):
            notices.inventory(path)
        regular = self.zip([("LICENSE", b"x")])
        link = self.root / "link.zip"
        link.symlink_to(regular)
        with self.assertRaises(OSError):
            notices.inventory(link)

    def test_zip_symlink_is_not_treated_as_source_notice(self):
        path = self.root / "links.zip"
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("LICENSE")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "/private/notice")
        report = notices.inventory(path)
        self.assertEqual(report["unfollowed_links"], 1)
        self.assertFalse(report["named_notice_candidates"])

    def test_member_count_size_total_and_compressed_budgets_are_enforced(self):
        path = self.zip([("a", b"aaa"), ("b", b"bbb")])
        for field, limit in (("MAX_MEMBERS", 1), ("MAX_MEMBER", 2), ("MAX_TOTAL", 5), ("MAX_ARCHIVE", 1)):
            with self.subTest(field=field), patch.object(notices, field, limit), self.assertRaises(notices.InventoryError):
                notices.inventory(path)

    def test_archive_mutation_fails_before_a_report_is_returned(self):
        path = self.zip([("LICENSE", b"x")])
        with patch.object(notices, "_fingerprint", side_effect=["before", "after"]), self.assertRaises(notices.InventoryError):
            notices.inventory(path)

    def test_non_notice_inline_terms_are_counted_without_full_scope_claim(self):
        path = self.zip([("include/special.h", b"// GNU GENERAL PUBLIC LICENSE\n"),
                         ("image.dat", b"\0\1nothing\2"),
                         ("unusual-terms", b"All rights reserved\n")])
        report = notices.inventory(path)
        self.assertEqual(report["header_signal_file_counts"]["gnu-license-reference"], 1)
        self.assertEqual(report["header_signal_file_counts"]["all-rights-reserved"], 1)
        self.assertFalse(report["named_notice_candidates"])
        self.assertTrue(report["limits"])

    def test_generated_javascript_suffix_notices_are_discovered(self):
        path = self.zip([("assets/main.123.js.LICENSE.txt", b"third-party terms"),
                         ("assets/unlicensed-file.dat", b"data")])
        report = notices.inventory(path)
        self.assertEqual([row["path"] for row in report["named_notice_candidates"]],
                         ["assets/main.123.js.LICENSE.txt"])

    def test_member_corruption_or_short_content_is_not_inventory_success(self):
        with self.assertRaises(notices.InventoryError):
            notices._file_record(io.BytesIO(b"short"), "LICENSE", 8, remaining=100)
        with self.assertRaises(notices.InventoryError):
            notices._file_record(io.BytesIO(b"longer"), "LICENSE", 3, remaining=100)


if __name__ == "__main__":
    unittest.main()
