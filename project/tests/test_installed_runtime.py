# SPDX-License-Identifier: MIT
"""Host fixtures and real host ELF inspection; no inspected target executes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import installed_runtime as probe

EXE = "/mnt/SDCARD/Emu/PSP/PPSSPPSDL_TrimUI"
LOADER = "/lib/ld-linux-aarch64.so.1"


def elf_record(name, *, needed=(), required=None, defined=(), soname=None):
    return {"path": name, "sha256": "a" * 64, "size": 128,
            "machine": "AArch64", "elf64": True,
            "interpreter": LOADER if name == EXE else None,
            "needed": list(needed), "soname": soname,
            "required_versions": required or {}, "defined_versions": list(defined),
            "file_identity": {"device": "1:2", "inode": 123}}


class InstalledRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="installed-runtime-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root, self.card = self.base / "root", self.base / "card"
        self.root.mkdir()
        self.card.mkdir()
        self.tree = probe.InstalledTree(self.root, self.card)

    def put(self, name, data=b"fixture"):
        path = self.tree.host(list(Path(name).parts[1:]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def process(self):
        self.put("/proc/123/stat", ("123 (engine (worker)) S " + " ".join(["0"] * 18) + " 999 0\n").encode())
        (self.root / "proc/123/exe").symlink_to(EXE)
        self.put("/proc/123/cmdline", b"PRIVATE-ROM --token SECRET")
        self.put("/proc/123/environ", b"SECRET=private")
        maps = ("1000-2000 r-xp 0000 01:02 123 " + EXE + "\n"
                "2000-3000 r-xp 0000 01:02 124 " + LOADER + "\n"
                "3000-4000 r-xp 0000 01:02 125 /lib/libc.so.6\n"
                "4000-5000 r--p 0000 01:02 126 /mnt/SDCARD/Roms/PSP/PRIVATE-ROM.iso\n")
        self.put("/proc/123/maps", maps.encode())
        return maps

    def test_absolute_and_cross_mount_symlinks_use_installed_tree(self):
        target = self.put("/usr/lib/libfixture.so.1")
        (self.root / "lib").symlink_to("/usr/lib")
        (target.parent / "libfixture.so").symlink_to("libfixture.so.1")
        self.assertEqual(self.tree.resolve("/lib/libfixture.so"), target)
        card_file = self.put(EXE)
        (self.root / "engine").symlink_to(EXE)
        self.assertEqual(self.tree.resolve("/engine"), card_file)
        (self.card / "host-root").symlink_to("/usr/lib/libfixture.so.1")
        self.assertEqual(self.tree.resolve("/mnt/SDCARD/host-root"), target)

    def test_loops_escape_and_host_fallback_are_refused(self):
        (self.root / "escape").symlink_to("../../outside")
        (self.root / "loop").symlink_to("/loop")
        for value in ("/escape", "/loop", "/bin/sh", "relative", "/bad\nname"):
            with self.subTest(value=value), self.assertRaises((ValueError, OSError)):
                self.tree.resolve(value)

    def test_directory_swaps_cannot_read_host_elf_or_metadata(self):
        for name, data in ((EXE, Path(shutil.which("true")).read_bytes()),
                           ("/proc/123/maps", b"outside private metadata")):
            with self.subTest(name=name):
                path = self.put(name, b"\x7fELF" + b"x" * 64 if name == EXE else b"inside")
                outside = self.base / ("outside-elf" if name == EXE else "outside-metadata")
                outside.mkdir()
                (outside / path.name).write_bytes(data)
                resolve = self.tree.resolve
                def swapped(value):
                    result = resolve(value)
                    if value == name:
                        path.parent.rename(path.parent.with_name(path.parent.name + "-old"))
                        path.parent.symlink_to(outside)
                    return result
                with patch.object(self.tree, "resolve", side_effect=swapped), \
                     patch.object(probe, "readelf_text") as inspect:
                    with self.assertRaises(OSError):
                        if name == EXE:
                            probe.inspect_elf(self.tree, name)
                        else:
                            self.tree.text(name)
                    inspect.assert_not_called()

    def test_real_host_elf_is_hashed_and_rejected_as_device_evidence(self):
        path = self.put(EXE, Path(shutil.which("true")).read_bytes())
        original = path.read_bytes()
        record = probe.inspect_elf(self.tree, EXE)
        self.assertEqual(record["sha256"], hashlib.sha256(original).hexdigest())
        self.assertTrue(record["interpreter"].startswith("/"))
        self.assertIn("libc.so.6", record["needed"])
        report = probe.collect(self.root, self.card, EXE)
        self.assertFalse(report["target_executed"])
        self.assertFalse(report["physical_qualification"])
        self.assertFalse(report["resume_qualified"])
        self.assertTrue(any("unavailable" in row["reason"] for row in report["errors"]))
        self.assertEqual(path.read_bytes(), original)

    def test_nonregular_and_oversize_inputs_refused_before_readelf(self):
        path = self.put(EXE)
        path.unlink()
        os.mkfifo(path)
        with patch.object(probe, "readelf_text") as run:
            with self.assertRaises(ValueError):
                probe.inspect_elf(self.tree, EXE)
            run.assert_not_called()
        path.unlink()
        with path.open("wb") as stream:
            stream.truncate(probe.MAX_ELF + 1)
        with self.assertRaises(ValueError):
            probe.inspect_elf(self.tree, EXE)

    def test_readelf_failure_and_timeout_never_produce_a_record(self):
        self.put(EXE, b"\x7fELF" + b"x" * 64)
        with patch.object(probe, "readelf_text", side_effect=subprocess.TimeoutExpired("readelf", 15)):
            report = probe.collect(self.root, self.card, EXE)
        self.assertEqual(report["objects"], [])
        self.assertTrue(report["errors"])

    def test_growing_elf_is_bounded_before_readelf(self):
        path = self.put(EXE, b"\x7fELF" + b"x" * 64)
        digest = hashlib.sha256()
        class GrowingHash:
            def update(self, block):
                digest.update(block)
                with path.open("ab") as stream:
                    stream.write(b"growing" * 64)
        with patch.object(probe.hashlib, "sha256", return_value=GrowingHash()), \
             patch.object(probe, "readelf_text") as inspect:
            with self.assertRaisesRegex(ValueError, "grew"):
                probe.inspect_elf(self.tree, EXE)
            inspect.assert_not_called()

    def test_readelf_output_and_runtime_are_bounded_while_running(self):
        fixture = self.put(EXE, b"\x7fELF" + b"x" * 64)
        script = self.base / "fixture-readelf"
        with fixture.open("rb") as stream:
            for descriptor in (1, 2):
                script.write_text("#!" + sys.executable + "\nimport os\nos.write(" + str(descriptor) + ", b'x' * 4096)\n")
                script.chmod(0o700)
                with patch.object(probe, "MAX_TEXT", 1024), self.assertRaisesRegex(ValueError, "output budget"):
                    probe.readelf_text(stream.fileno(), str(script))
            script.write_text("#!" + sys.executable + "\nimport time\ntime.sleep(30)\n")
            with self.assertRaises(subprocess.TimeoutExpired):
                probe.readelf_text(stream.fileno(), str(script), timeout=0.05)

    def test_version_definitions_and_requirements_are_separate(self):
        data = """Version definition section '.gnu.version_d' contains 1 entries:
  0x0010: Rev: 1 Flags: none Index: 2 Cnt: 1 Name: LIB_2.0
Version needs section '.gnu.version_r' contains 1 entries:
  0x0000: Version: 1 File: libc.so.6 Cnt: 1
  0x0010: Name: GLIBC_2.17 Flags: none Version: 2
"""
        self.assertEqual(probe.symbol_versions(data, "definition"), {"": ["LIB_2.0"]})
        self.assertEqual(probe.symbol_versions(data, "needs"), {"libc.so.6": ["GLIBC_2.17"]})

    def test_process_collection_omits_roms_arguments_and_environment(self):
        self.process()
        records = {EXE: elf_record(EXE, needed=["libc.so.6"], required={"libc.so.6": ["GLIBC_2.17"]}),
                   LOADER: elf_record(LOADER),
                   "/lib/libc.so.6": elf_record("/lib/libc.so.6", defined=["GLIBC_2.17"])}
        with patch.object(probe, "inspect_elf", side_effect=lambda tree, name, command: records[name].copy()):
            report = probe.collect(self.root, self.card, EXE, pid=123)
        self.assertTrue(report["process_stable"])
        self.assertEqual(report["process_identity"]["starttime_ticks"], 999)
        self.assertEqual(report["omitted_nonlibrary_mappings"], 1)
        self.assertEqual(report["dependency_checks"][0]["status"], "present_in_supplied_objects")
        self.assertFalse(report["live_root"])
        self.assertTrue(all(row["mapped_inode_matches"] is None for row in report["objects"]))
        text = json.dumps(report)
        self.assertNotIn("PRIVATE-ROM", text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("1000-2000", text)

    def test_wrong_process_and_pid_reuse_do_not_satisfy_identity(self):
        maps = self.process()
        (self.root / "proc/123/exe").unlink()
        (self.root / "proc/123/exe").symlink_to("/bin/unrelated")
        with patch.object(probe, "inspect_elf", side_effect=lambda tree, name, command: elf_record(name)):
            with self.assertRaisesRegex(ValueError, "PID does not identify"):
                probe.collect(self.root, self.card, EXE, pid=123)
        first = {"pid": 123, "starttime_ticks": 1, "executable": EXE, "maps_sha256": "a" * 64}
        after = dict(first, starttime_ticks=2)
        with patch.object(probe, "process_snapshot", side_effect=[(first, maps), (after, maps)]), \
             patch.object(probe, "inspect_elf", side_effect=lambda tree, name, command: elf_record(name)):
            report = probe.collect(self.root, self.card, EXE, pid=123)
        self.assertFalse(report["process_stable"])
        self.assertTrue(any("process identity" in row["reason"] for row in report["errors"]))

    def test_ambiguous_libraries_and_missing_symbols_remain_visible(self):
        def inspect(tree, name, command):
            if name == EXE:
                return elf_record(name, needed=["libc.so.6", "libmissing.so"],
                                  required={"libc.so.6": ["GLIBC_2.28"]})
            return elf_record(name, defined=["GLIBC_2.17"])
        with patch.object(probe, "inspect_elf", side_effect=inspect):
            report = probe.collect(self.root, self.card, EXE, ["/lib/libc.so.6"])
            ambiguous = probe.collect(self.root, self.card, EXE, ["/lib/libc.so.6", "/usr/lib/libc.so.6"])
        self.assertEqual(report["dependency_checks"][0]["missing_versions"], ["GLIBC_2.28"])
        self.assertEqual(report["dependency_checks"][1]["status"], "missing")
        self.assertEqual(ambiguous["dependency_checks"][0]["status"], "ambiguous")
        self.assertEqual(len(ambiguous["dependency_checks"][0]["candidates"]), 2)

    def test_mappings_are_bounded_and_replaced_inodes_rejected(self):
        self.assertRaises(ValueError, probe.mapped_objects,
                          "100-200 r-xp 000 01:02 0 /lib/libc.so.6", EXE, LOADER)
        data = "\n".join("100-200 r-xp 000 01:02 %d /lib/lib%d.so" % (i + 1, i)
                         for i in range(probe.MAX_OBJECTS + 1))
        self.assertRaises(ValueError, probe.mapped_objects, data, EXE, LOADER)
        self.put("/proc/123/maps", b"x" * (probe.MAX_TEXT + 1))
        self.assertRaises(ValueError, self.tree.text, "/proc/123/maps")
        for pid in (0, -1, True, 2 ** 32):
            self.assertRaises(ValueError, probe.process_snapshot, self.tree, pid)
        self.assertRaisesRegex(ValueError, "deleted", probe.mapped_objects,
                               "100-200 r-xp 000 01:02 123 /lib/libc.so.6 (deleted)", EXE, LOADER)

    def test_output_is_explicit_and_existing_output_is_preserved(self):
        output = self.base / "report.json"
        cmd = [sys.executable, str(PROJECT / "tools/installed_runtime.py"),
               "--root", str(self.root), "--sd-root", str(self.card)]
        self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        result = subprocess.run(cmd + ["--output", str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        before = output.read_bytes()
        self.assertNotEqual(subprocess.run(cmd + ["--output", str(output)], capture_output=True).returncode, 0)
        self.assertEqual(output.read_bytes(), before)
        self.assertTrue(json.loads(before)["errors"])


if __name__ == "__main__":
    unittest.main()
