# SPDX-License-Identifier: MIT
"""Actual pinned debugger stats collector under ASan/UBSan, not a device test."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_native_menu_patch import block, checked

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


class GPUStatsPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.environ.get("PPSSPP_SOURCE_ROOT")
        if not configured:
            raise unittest.SkipTest("Set PPSSPP_SOURCE_ROOT to pinned v1.20.3")
        cls.temp = tempfile.TemporaryDirectory(prefix="ppsspp-gpu-stats-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        lock = json.loads((ROOT / "gpu-stats.lock.json").read_text())
        item = lock["source_files"][0]
        original = Path(configured) / item["path"]
        if hashlib.sha256(original.read_bytes()).hexdigest() != item["sha256"]:
            raise AssertionError("GPU stats source preimage differs")
        target = cls.work / item["path"]
        target.parent.mkdir(parents=True)
        shutil.copy2(original, target)
        old = target.read_text()
        patch = ROOT / lock["patch"]["path"]
        if hashlib.sha256(patch.read_bytes()).hexdigest() != lock["patch"]["sha256"]:
            raise AssertionError("GPU stats patch digest differs")
        checked(["git", "apply", "--check", str(patch)], cwd=cls.work)
        checked(["git", "apply", str(patch)], cwd=cls.work)
        if hashlib.sha256(target.read_bytes()).hexdigest() != lock["patched_files"][0]["sha256"]:
            raise AssertionError("GPU stats source postimage differs")
        cls.binaries = {}
        for name, source in (("original", old), ("fixed", target.read_text())):
            code = (HERE / "gpu_stats_acceptance.cpp.in").read_text()
            code = code.replace("/*@@COLLECTED_STATS@@*/", block(source, "struct CollectedStats", semicolon=True))
            code = code.replace("/*@@FLIP_LISTENER@@*/", block(source, "void WebSocketGPUStatsState::FlipListener()"))
            cpp, binary = cls.work / (name + ".cpp"), cls.work / name
            cpp.write_text(code)
            checked(["g++", "-std=c++17", "-O1", "-g", "-fno-omit-frame-pointer",
                     "-fsanitize=address,undefined", str(cpp), "-o", str(binary)], cwd=cls.work)
            cls.binaries[name] = binary

    def execute(self, name, count):
        return subprocess.run([str(self.binaries[name]), str(count)], capture_output=True,
                              text=True, timeout=20,
                              env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1"})

    def test_original_nonempty_history_reproduces_heap_overflow(self):
        result = self.execute("original", 4)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("heap-buffer-overflow", result.stderr)

    def test_fixed_empty_partial_and_full_histories_copy_exact_float_values(self):
        for count in (0, 1, 4, 600):
            with self.subTest(count=count):
                result = self.execute("fixed", count)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS count=" + str(count), result.stdout)


if __name__ == "__main__":
    unittest.main()
