# SPDX-License-Identifier: MIT
"""Exercise isolation and input rejection with real disposable Git checkouts."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("ppsspp_build_candidate", Path(__file__).resolve().parents[1] / "build_candidate.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(["git", "-c", "user.name=Candidate fixture", "-c", "user.email=fixture@example.invalid", *arguments],
                          cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CandidateInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ppsspp-build-inputs-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.here = self.root / "project-repo/project/ppsspp"
        self.here.mkdir(parents=True)
        self.source = self.root / "upstream"
        self.recipe = self.root / "recipe"
        self.sdk = self.root / "sdk"
        self.module = self.root / "module-origin"
        for directory in (self.source, self.recipe, self.module, self.sdk):
            directory.mkdir()
        for directory in (self.source, self.recipe, self.module):
            git(directory, "init", "--quiet")
        (self.module / "notice.txt").write_text("Submodule notice fixture\n")
        git(self.module, "add", ".")
        git(self.module, "commit", "-qm", "Submodule fixture")
        git(self.source, "-c", "protocol.file.allow=always", "submodule", "add", str(self.module), "ext/module")
        original = b"before\n"
        changed = b"after\n"
        (self.source / "source.txt").write_bytes(original)
        git(self.source, "add", ".")
        git(self.source, "commit", "-qm", "Upstream fixture")
        (self.recipe / "Dockerfile.pvr").write_text("FROM ubuntu:20.04\nRUN apt-get update && apt-get install -y cmake\n# Extract Linaro\nRUN printf 'fixture' > /tmp/pvr-toolchain.cmake\nCOPY build-pvr.sh /build-pvr.sh\n")
        (self.recipe / "build-pvr.sh").write_text('#!/bin/bash\n# Apply common patches\n# fixture patches\nmkdir -p build && cd build\ncmake .. -DCMAKE_C_FLAGS="-O2" -DCMAKE_CXX_FLAGS="-O2" -DCMAKE_EXE_LINKER_FLAGS="-static-libstdc++"\nmake -j$(nproc) PPSSPPSDL\n')
        git(self.recipe, "add", ".")
        git(self.recipe, "commit", "-qm", "Recipe fixture")
        project_patch = b"--- a/source.txt\n+++ b/source.txt\n@@ -1 +1 @@\n-before\n+after\n"
        (self.here / "patches").mkdir()
        (self.here / "patches/extension.patch").write_bytes(project_patch)
        self.sdk_names = ["aarch64-linux-gnu-7.5.0-linaro.tgz", "SDK_usr_tg5040_a133p.tgz"]
        for name in self.sdk_names:
            (self.sdk / name).write_bytes(b"SDK fixture")
        self.lock = {
            "upstream": {"commit": git(self.source, "rev-parse", "HEAD")},
            "source_files": [{"path": "source.txt", "sha256": sha(original)}],
            "patches": [{"path": "patches/extension.patch", "sha256": sha(project_patch)}],
            "patched_files": [{"path": "source.txt", "sha256": sha(changed)}],
        }
        self.inputs = {
            "recipe_commit": git(self.recipe, "rev-parse", "HEAD"),
            "base_image": "ubuntu:20.04@sha256:" + "a" * 64,
            "recipe_files": [{"path": name, "sha256": builder.digest(self.recipe / name)} for name in ("Dockerfile.pvr", "build-pvr.sh")],
            "sdk_assets": [{"name": name, "size": 11, "sha256": builder.digest(self.sdk / name)} for name in self.sdk_names],
        }
        (self.here / "source-lock.json").write_text(json.dumps(self.lock))
        (self.here / "build-inputs.lock.json").write_text(json.dumps(self.inputs))
        for name in ("build_candidate.py", "abi_audit.py", "apply_recipe.py", "sdk_search.py", "ffmpeg_build.py", "build-candidate.md"):
            (self.here / name).write_text("# Source-retention fixture\n")
        self.here_patch = patch.object(builder, "HERE", self.here)
        self.here_patch.start()
        self.addCleanup(self.here_patch.stop)

    def prepare(self, work: Path):
        return builder.prepare(self.source, self.recipe, self.sdk, work, self.lock, self.inputs, 2)

    def test_candidate_is_separate_and_retains_pinned_submodule_notices(self):
        work = self.root / "candidate"
        report = self.prepare(work)
        self.assertEqual((self.source / "source.txt").read_text(), "before\n")
        self.assertEqual((work / "source/source.txt").read_text(), "after\n")
        self.assertEqual((work / "source/ext/module/notice.txt").read_text(), "Submodule notice fixture\n")
        self.assertFalse(report["full_engine_cross_build"])
        self.assertFalse(report["device_tested"])
        self.assertIn("make -j2 PPSSPPSDL", (work / "build-candidate.sh").read_text())
        self.assertIn("--mount=type=secret,id=proxy_ca", (work / "context/Dockerfile").read_text())
        generated = (work / "context/Dockerfile").read_text()
        self.assertEqual(generated.count("\nRUN "), 1)
        self.assertNotIn("\nCOPY ", generated)
        self.assertIn("--mount=type=bind,source=SDK_usr_tg5040_a133p.tgz", generated)
        self.assertIn("rm -rf /opt/aarch64-linux-gnu-7.5.0-linaro /opt/smartpro-sdk", generated)
        self.assertEqual(git(self.source, "status", "--porcelain"), "")
        (work / "toolchain-packages.txt").write_text("Compiler version fixture\n")
        metadata = builder.source_bundle(work)
        with tarfile.open(work / metadata["name"]) as archive:
            names = set(archive.getnames())
        self.assertTrue({"ppsspp/source.txt", "ppsspp/ext/module/notice.txt", "build/build_candidate.py",
                         "build/rebuild-source.sh", "build/patches/extension.patch", "build/source-lock.json",
                         "build/recipe/Dockerfile", "build/recipe/build-pvr.sh", "build/toolchain-packages.txt"} <= names)
        self.assertFalse(any(".git" in Path(name).parts for name in names))
        self.assertFalse(any(Path(name).name in self.sdk_names for name in names))

    def test_changed_sdk_or_source_refuses_before_creating_output(self):
        (self.sdk / self.sdk_names[0]).write_bytes(b"bad")
        work = self.root / "candidate"
        with self.assertRaisesRegex(ValueError, "Input hash differs"):
            self.prepare(work)
        self.assertFalse(work.exists())
        (self.sdk / self.sdk_names[0]).write_bytes(b"SDK fixture")
        (self.source / "source.txt").write_text("externally changed\n")
        with self.assertRaisesRegex(ValueError, "not pristine"):
            self.prepare(work)
        self.assertFalse(work.exists())

    def test_submodule_untracked_files_are_rejected_even_if_parent_hides_them(self):
        git(self.source, "config", "submodule.ext/module.ignore", "all")
        (self.source / "ext/module/untracked-owner-data").write_text("keep private\n")
        work = self.root / "candidate"
        with self.assertRaisesRegex(ValueError, "Submodule working trees"):
            self.prepare(work)
        self.assertFalse(work.exists())

    def test_work_inside_an_input_or_project_and_existing_work_are_refused(self):
        for root in (self.source, self.recipe, self.sdk, self.here.parents[1]):
            with self.assertRaisesRegex(ValueError, "outside all inputs"):
                self.prepare(root / "candidate")
        work = self.root / "existing"
        work.mkdir()
        (work / "owner-file").write_text("keep")
        with self.assertRaisesRegex(ValueError, "must be new"):
            self.prepare(work)
        self.assertEqual((work / "owner-file").read_text(), "keep")

    def test_actual_target_definitions_are_required_for_every_extension_translation_unit(self):
        work = self.root / "flags-fixture"
        target = work / "source/build/CMakeFiles/Core.dir"
        target.mkdir(parents=True)
        (target.parent.parent / "git-version.cpp").write_text('const char *PPSSPP_GIT_VERSION = "fixture";\n')
        (target / "build.make").write_text("\n".join(unit + ".o: source" for unit in
                    ("Core/KeyMap.cpp", "UI/NativeApp.cpp", "UI/GameSettingsScreen.cpp")))
        (target / "flags.make").write_text("CXX_DEFINES = -DSDL -DRELEASE=1\nCXX_FLAGS = -O2 -std=c++17\n")
        report = builder.retain_build_configuration(work)
        self.assertEqual(len(report["translation_units"]), 3)
        self.assertTrue(all(item["sdl_defined"] for item in report["translation_units"].values()))
        (target / "flags.make").write_text("CXX_DEFINES = -DRELEASE=1\n")
        with self.assertRaisesRegex(ValueError, "SDL definition is absent"):
            builder.retain_build_configuration(work)

    def test_strict_search_is_opt_in_and_keeps_gcc9_runtime_before_old_sysroot(self):
        baseline = self.root / "baseline"
        self.prepare(baseline)
        self.assertNotIn("-nostdinc", (baseline / "rebuild-source.sh").read_text())
        strict = self.root / "strict"
        report = builder.prepare(self.source, self.recipe, self.sdk, strict, self.lock, self.inputs, 2, True)
        self.assertTrue(report["strict_sdk_search"])
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        captured = self.root / "calls.jsonl"
        for name in ("cmake", "make"):
            command = fakebin / name
            command.write_text(f'#!{sys.executable}\nimport json,os,sys\nwith open(os.environ["PPSSPP_FIXTURE_ARGV"], "a") as stream: stream.write(json.dumps(sys.argv)+"\\n")\n')
            command.chmod(0o755)
        environment = dict(os.environ, PATH=str(fakebin) + os.pathsep + os.environ.get("PATH", ""),
                           PPSSPP_FIXTURE_ARGV=str(captured))
        subprocess.run(["/bin/bash", str(strict / "rebuild-source.sh")], cwd=strict / "source",
                       env=environment, check=True, capture_output=True, text=True)
        cmake, make = [json.loads(line) for line in captured.read_text().splitlines()]
        self.assertEqual(Path(cmake[0]).name, "cmake")
        self.assertEqual(cmake[1], "..")
        # Each quoted -D value survives the generated shell as exactly one argument.
        self.assertEqual(len(cmake), 5)
        options = dict(argument[2:].split("=", 1) for argument in cmake[2:])
        c_flags = shlex.split(options["CMAKE_C_FLAGS"])
        cxx_flags = shlex.split(options["CMAKE_CXX_FLAGS"])
        link_flags = shlex.split(options["CMAKE_EXE_LINKER_FLAGS"])
        self.assertEqual(c_flags[:2], ["-O2", "-nostdinc"])
        self.assertEqual(cxx_flags[:2], ["-O2", "-nostdinc"])
        self.assertEqual(c_flags[-1], "-I/opt/sysroot/usr/include")
        self.assertEqual(cxx_flags[-1], "-I/opt/sysroot/usr/include")
        self.assertIn("-I/usr/aarch64-linux-gnu/include/c++/9", cxx_flags)
        self.assertNotIn("-I/usr/aarch64-linux-gnu/include", cxx_flags)
        self.assertEqual(link_flags, ["-static-libstdc++", "-L/usr/lib/gcc-cross/aarch64-linux-gnu/9",
                                     "-L/opt/sysroot/lib", "-L/opt/sysroot/usr/lib"])
        self.assertEqual(make[1:], ["-j2", "PPSSPPSDL"])
        self.assertEqual(git(self.source, "status", "--porcelain"), "")

    def test_search_correction_refuses_repeat_and_missing_or_duplicate_compiler_options(self):
        module = builder.sdk_search_module()
        original = (self.recipe / "build-pvr.sh").read_text()
        corrected = module.adapt_script(original)
        with self.assertRaisesRegex(ValueError, "already present"):
            module.adapt_script(corrected)
        for changed in (original.replace("CMAKE_CXX_FLAGS", "OTHER_FLAGS"), original + '\n-DCMAKE_C_FLAGS="-O3"'):
            with self.assertRaisesRegex(ValueError, "changed or duplicated"):
                module.adapt_script(changed)

    def test_rebuilt_ffmpeg_source_retention_omits_old_archives_and_private_environment_log(self):
        work = self.root / "ffmpeg-retention"
        self.prepare(work)
        ffmpeg = work / "source/ffmpeg"
        ffmpeg.mkdir()
        archive = ffmpeg / "unused.a"
        archive.write_bytes(b"old prebuilt input")
        (ffmpeg / "LICENSE").write_text("notice fixture")
        (ffmpeg / "source.c").write_text("source fixture")
        metadata = work / "ffmpeg-build-inputs"
        metadata.mkdir()
        (metadata / "manifest.json").write_text('{"status":"complete"}')
        build = work / "ffmpeg-build"
        build.mkdir()
        (build / "config.log").write_text("private environment fixture")
        result = builder.source_bundle(work)
        with tarfile.open(work / result["name"]) as retained:
            names = set(retained.getnames())
            omitted = json.load(retained.extractfile("build/omitted-ffmpeg-prebuilt-archives.json"))
        self.assertNotIn("ppsspp/ffmpeg/unused.a", names)
        self.assertIn("ppsspp/ffmpeg/source.c", names)
        self.assertIn("ppsspp/ffmpeg/LICENSE", names)
        self.assertEqual(omitted["files"]["ppsspp/ffmpeg/unused.a"]["sha256"], sha(b"old prebuilt input"))
        self.assertFalse(any(Path(name).name == "config.log" for name in names))
        self.assertEqual(archive.read_bytes(), b"old prebuilt input")


if __name__ == "__main__":
    unittest.main()
