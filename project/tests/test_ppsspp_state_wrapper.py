# SPDX-License-Identifier: MIT
"""Actual pinned spruce wrapper with explicit inert platform-service fixtures."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
LOCK = PROJECT / "patches/ppsspp-state-session.lock.json"


class PPSSPPStateWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("SPRUCE_SOURCE_ROOT")
        if not source:
            raise unittest.SkipTest("Set SPRUCE_SOURCE_ROOT to the pinned spruce v4.5.4")
        lock = json.loads(LOCK.read_text())
        cls.temporary = tempfile.TemporaryDirectory(prefix="spruce-state-wrapper-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = Path(cls.temporary.name)
        for item in lock["source_files"]:
            data = (Path(source) / item["path"]).read_bytes()
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise AssertionError("Pinned wrapper source differs")
            target = cls.work / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        patch = PROJECT.parent / lock["patch"]["path"]
        if hashlib.sha256(patch.read_bytes()).hexdigest() != lock["patch"]["sha256"]:
            raise AssertionError("Wrapper patch differs")
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=cls.work, check=True, capture_output=True)
        subprocess.run(["git", "apply", str(patch)], cwd=cls.work, check=True, capture_output=True)
        for item in lock["patched_files"]:
            if hashlib.sha256((cls.work / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
                raise AssertionError("Patched wrapper differs")
        cls.source = (cls.work / lock["patched_files"][0]["path"]).read_text()

    def run_case(self, request=None, resume=None):
        with tempfile.TemporaryDirectory(prefix="ppsspp-source-wrapper-case-") as directory:
            root = Path(directory)
            engine = root / "fake engine"
            engine.write_text("#!/usr/bin/env python3\nimport json,os,sys\nopen(os.environ['FIXTURE_ARGV_OUTPUT'],'w').write(json.dumps(sys.argv[1:]))\n")
            engine.chmod(0o755)
            begin = self.source.index("run_ppsspp() {")
            end = self.source.index("\nconfigure_retroachievements()", begin)
            function = self.source[begin:end]
            # Exact wrapper body; the absolute audio setup is the one service
            # that cannot be replaced by a shell function in a host fixture.
            self.assertEqual(function.count('/mnt/SDCARD/spruce/scripts/asound-setup.sh "$HOME"'), 1)
            function = function.replace('/mnt/SDCARD/spruce/scripts/asound-setup.sh "$HOME"', ": # inert audio-service fixture")
            script = root / "harness.sh"
            script.write_text('''#!/bin/sh
set_up_default_configs_if_needed() { printf '%s\\n' setup >> "$FIXTURE_TRACE"; }
load_ppsspp_configs() { :; }
configure_retroachievements() { :; }
move_screenshots_if_present() { :; }
save_ppsspp_configs() { printf '%s\\n' copyback >> "$FIXTURE_TRACE"; }
mount() { :; }
umount() { :; }
log_message() { :; }
vk_display_preload() { :; }
emu_log_file() { printf '%s' "$FIXTURE_ENGINE_LOG"; }
''' + function + "\nrun_ppsspp\n")
            env = dict(os.environ)
            for key in ("TRIMUI_PROJECT_STATE_REQUEST", "TRIMUI_PROJECT_RESUME_STATE"):
                env.pop(key, None)
            env.update(EMU_DIR=str(root), PSP_BIN="fake engine", PLATFORM="Fixture", ROM_FILE="/card/ROM with ü.iso",
                       PSP_SS_DIR=str(root / "screens"), SS_DIR=str(root / "screens-out"), PSP_DIR=str(root / "configs"),
                       FIXTURE_ARGV_OUTPUT=str(root / "args.json"), FIXTURE_TRACE=str(root / "trace"), FIXTURE_ENGINE_LOG=str(root / "log"))
            if request is not None:
                env["TRIMUI_PROJECT_STATE_REQUEST"] = request
            if resume is not None:
                env["TRIMUI_PROJECT_RESUME_STATE"] = resume
            result = subprocess.run(["/bin/sh", str(script)], env=env, cwd=root, text=True, capture_output=True, timeout=10)
            output = json.loads((root / "args.json").read_text()) if (root / "args.json").exists() else None
            trace = (root / "trace").read_text() if (root / "trace").exists() else ""
            return result, output, trace

    def test_unarmed_wrapper_preserves_original_engine_arguments_and_copyback(self):
        result, arguments, trace = self.run_case()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(arguments, ["/card/ROM with ü.iso", "--fullscreen", "--pause-menu-exit"])
        self.assertEqual(trace, "setup\ncopyback\n")

    def test_explicit_capture_and_resume_are_single_quoted_arguments(self):
        request = "/tmp/private session/$(do-not-execute)/request"
        state = "/card/states/owner's state ü.ppst"
        result, arguments, trace = self.run_case(request, state)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(arguments[-2:], ["--project-state-session=" + request, "--state=" + state])
        self.assertEqual(trace, "setup\ncopyback\n")

    def test_invalid_or_unpaired_session_fails_before_device_setup(self):
        for request, resume in (("relative/request", None), (None, "/card/state"), ("/tmp/session/request", "relative.ppst")):
            with self.subTest(request=request, resume=resume):
                result, arguments, trace = self.run_case(request, resume)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(arguments)
                self.assertEqual(trace, "")


if __name__ == "__main__":
    unittest.main()
