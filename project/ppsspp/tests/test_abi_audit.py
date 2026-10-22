# SPDX-License-Identifier: MIT
"""No target binary is executed by these ELF audit helper tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("ppsspp_abi_audit", Path(__file__).resolve().parents[1] / "abi_audit.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class ElfAuditTests(unittest.TestCase):
    def test_symbol_definitions_and_requirements_are_kept_separate(self):
        text = """Version definition section '.gnu.version_d' contains 1 entries:
  0x0010: Rev: 1  Flags: none  Index: 2  Cnt: 1  Name: LIB_2.0
Version needs section '.gnu.version_r' contains 1 entries:
  0x0000: Version: 1  File: libc.so.6  Cnt: 2
  0x0010: Name: GLIBC_2.17  Flags: none  Version: 2
  0x0020: Name: GLIBC_2.25  Flags: none  Version: 3
"""
        self.assertEqual(audit.versions(text, "definition"), {"": ["LIB_2.0"]})
        self.assertEqual(audit.versions(text, "needs"), {"libc.so.6": ["GLIBC_2.17", "GLIBC_2.25"]})

    def test_absolute_and_parent_directory_symlinks_stay_in_sysroot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "usr/lib/libfixture.so.1"
            library.parent.mkdir(parents=True)
            library.write_bytes(b"Fixture, never executed")
            (root / "lib").symlink_to("/usr/lib")
            (root / "usr/lib/libfixture.so").symlink_to("libfixture.so.1")
            self.assertEqual(audit.resolve_inside(root / "lib/libfixture.so", root), library)
            (root / "usr/lib/escape.so").symlink_to("../../../outside")
            self.assertIsNone(audit.resolve_inside(root / "usr/lib/escape.so", root))
            (root / "usr/lib/loop.so").symlink_to("loop.so")
            self.assertIsNone(audit.resolve_inside(root / "usr/lib/loop.so", root))


if __name__ == "__main__":
    unittest.main()
