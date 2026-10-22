"""Private full-engine preparation and cross-build boundary acceptance."""
from __future__ import annotations

import difflib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parents[1] / "retroarch"
SPEC = importlib.util.spec_from_file_location("retroarch_build_candidate", HERE / "build_candidate.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

RECIPE = '''export CFLAGS="$CFLAGS -O3 -flto=auto -D_GNU_SOURCE"
export CXXFLAGS="$CXXFLAGS -O3 -flto=auto -D_GNU_SOURCE"
export LDFLAGS="$LDFLAGS -Wl,--gc-sections -flto=auto"
./configure --host=aarch64-linux-gnu \\
    --enable-vulkan --enable-egl --enable-opengles --enable-opengles3 --enable-sdl2

make HAVE_STATIC_VIDEO_FILTERS=1 HAVE_STATIC_AUDIO_FILTERS=1 -j$(nproc)
'''


def git(directory, *args):
    return subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit(directory):
    git(directory, "init", "-q")
    git(directory, "add", ".")
    git(directory, "-c", "user.email=fixture@invalid", "-c", "user.name=Fixture", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
    return git(directory, "rev-parse", "HEAD")


def diff(name, before, after):
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile="a/" + name, tofile="b/" + name))


class RetroArchBuildTests(unittest.TestCase):
    def test_real_locked_inputs_and_compiler_search_are_explicit(self):
        lock = builder.load_lock()
        self.assertEqual(lock["upstream"]["commit"], "69a4f0ea1e8aaf442ae4858f2e7f2b31a1776576")
        self.assertEqual(len([row for row in lock["recipe"]["files"] if row["path"].startswith("patches/common/")]), 4)
        args, env = builder.compiler_environment(RECIPE)
        self.assertIn("--disable-vulkan", args)
        self.assertNotIn("--enable-vulkan", args)
        self.assertIn("--enable-opengles3", args)
        self.assertIn("-nostdinc -I/usr/lib/gcc-cross/aarch64-linux-gnu/9/include -isystem /opt/sysroot/usr/include", env["CFLAGS"])
        self.assertTrue(env["CXXFLAGS"].index("/usr/aarch64-linux-gnu/include/c++/9") < env["CXXFLAGS"].index("/opt/sysroot/usr/include"))
        self.assertEqual(env["PKG_CONFIG_LIBDIR"], "/opt/sysroot/usr/lib/pkgconfig:/opt/sysroot/usr/share/pkgconfig")
        self.assertEqual(env["PKG_CONF_PATH"], "/usr/bin/pkg-config")
        self.assertNotIn("/usr/lib/aarch64-linux-gnu", env["LDFLAGS"])

    def test_recipe_parser_refuses_dynamic_or_duplicate_commands(self):
        for text in (RECIPE.replace("--enable-egl", "$(touch /tmp/bad)"),
                     RECIPE.replace("--enable-egl", "--enable-egl;true"),
                     RECIPE + "\n./configure --enable-vulkan\n\n",
                     RECIPE.replace('-O3 -flto=auto', '-O3 $(env)', 1),
                     RECIPE.replace("--enable-vulkan", "--disable-vulkan")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                builder.recipe_options(text)

    def test_pristine_checkout_guard_rejects_dirty_untracked_and_ignored_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "engine.c").write_text("source\n")
            (root / ".gitignore").write_text("*.o\n")
            identity = commit(root)
            builder.verify_checkout(root, identity)
            for name in ("engine.c", "extra.c", "ignored.o"):
                (root / name).write_text("changed\n")
                with self.assertRaisesRegex(ValueError, "pristine"):
                    builder.verify_checkout(root, identity)
                if name == "engine.c":
                    git(root, "checkout", "--", name)
                else:
                    (root / name).unlink()
            with self.assertRaisesRegex(ValueError, "commit differs"):
                builder.verify_checkout(root, "0" * 40)

    def test_full_checkout_guard_rejects_sparse_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("keep", "omit"):
                (root / name).mkdir()
                (root / name / "source.c").write_text("fixture\n")
            identity = commit(root)
            git(root, "sparse-checkout", "set", "keep")
            with self.assertRaisesRegex(ValueError, "Full checkout"):
                builder.verify_checkout(root, identity)

    def test_locked_file_rejects_hash_drift_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "input"
            path.write_text("one")
            item = {"path": "input", "sha256": builder.sha(path)}
            builder.verify_file(root, item)
            path.write_text("two")
            with self.assertRaisesRegex(ValueError, "hash differs"):
                builder.verify_file(root, item)
            path.unlink()
            path.symlink_to("other")
            (root / "other").write_text("one")
            with self.assertRaisesRegex(ValueError, "redirected"):
                builder.verify_file(root, item)
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                builder.verify_file(root, {"path": "../input", "sha256": item["sha256"]})

    def test_source_inventory_rejects_external_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source").mkdir()
            (root / "private").write_text("not a source input")
            (root / "source/escape").symlink_to("../private")
            with self.assertRaisesRegex(ValueError, "escapes"):
                builder.source_inventory(root / "source")

    def test_docker_is_offline_local_scoped_and_preserves_registry_environment(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "DOCKER_HOST": "tcp://wrong.invalid:2376", "DOCKER_CONTEXT": "wrong",
            "DOCKER_TLS": "1", "DOCKER_CERT_PATH": "/private/certs", "DOCKER_TLS_VERIFY": "1",
            "DOCKER_CONFIG": "/private/registry", "HTTPS_PROXY": "http://proxy.invalid:8080"}):
            args, env = builder.docker_command(Path(directory), "sha256:" + "a" * 64, "#!/bin/sh\ntrue\n")
            self.assertIn("--host=unix:///var/run/docker.sock", args)
            self.assertIn("--network=none", args)
            self.assertIn("--user", args)
            self.assertIn("--cpus=4", args)
            self.assertIn("--memory=8g", args)
            self.assertEqual(env["DOCKER_CONFIG"], "/private/registry")
            self.assertEqual(env["HTTPS_PROXY"], "http://proxy.invalid:8080")
            self.assertTrue(all(key not in env for key in builder.DOCKER_SELECTORS))
            self.assertEqual(os.environ["DOCKER_HOST"], "tcp://wrong.invalid:2376")
            with self.assertRaisesRegex(ValueError, "Moving image tags"):
                builder.docker_command(Path(directory), "compiler:latest", "true")

    def test_link_overlay_removes_explicit_dynamic_cxx_library_and_keeps_other_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Makefile").write_text("LIBS = -lc -lstdc++ -lpthread\nLDFLAGS = -Wl,--gc-sections\nall:\n\t@echo $(LIBS)\n\t@echo $(LDFLAGS)\n")
            (root / "sdk-link.mk").write_text(builder.SDK_LINK)
            output = subprocess.run(["make", "-sf", "Makefile", "-f", "sdk-link.mk"], cwd=root, check=True, capture_output=True, text=True).stdout
            self.assertIn("-lc /usr/lib/gcc-cross/aarch64-linux-gnu/9/libstdc++.a -lpthread", output)
            self.assertNotIn(" -lstdc++ ", output)
            self.assertIn("-Wl,--gc-sections -static-libstdc++ -Wl,-t", output)

    def test_actual_patch_order_shared_source_and_complete_private_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream, recipe, project, work = (root / name for name in ("upstream", "recipe", "project", "work"))
            retroarch = project / "retroarch"
            for path in (upstream, recipe / "patches/common", recipe / "common_src", retroarch / "patches"):
                path.mkdir(parents=True)
            (upstream / "engine.c").write_text("upstream\n")
            (upstream / "COPYING").write_text("Retain original engine licence\n")
            upstream_id = commit(upstream)
            first = recipe / "patches/common/0001.patch"
            second = recipe / "patches/common/0002.patch"
            first.write_text(diff("engine.c", "upstream\n", "recipe-stage-one\n"))
            second.write_text(diff("engine.c", "recipe-stage-one\n", "recipe-stage-two\n"))
            shared = recipe / "common_src/theme.c"
            shared.write_text("recipe-theme\n")
            (recipe / "build.sh").write_text(RECIPE)
            recipe_id = commit(recipe)
            extension = retroarch / "patches/extension.patch"
            extension.write_text(diff("theme.c", "recipe-theme\n", "project-theme\n"))
            for name in ("build_candidate.py", "build-candidate.md", "source-lock.json"):
                (retroarch / name).write_text("retained " + name)
            (project / "LICENSE").write_text("MIT fixture\n")
            item = lambda path, base: {"path": path.relative_to(base).as_posix(), "sha256": builder.sha(path)}
            lock = {"schema": 1, "upstream": {"commit": upstream_id, "tree": git(upstream, "rev-parse", "HEAD^{tree}")},
                    "recipe": {"commit": recipe_id, "files": [item(path, recipe) for path in sorted([first, second, shared, recipe / "build.sh"])]},
                    "helpers": [], "extension": item(extension, retroarch), "patched_source": [],
                    "toolchain": {"image_id": "sha256:" + "a" * 64}}
            lock_path = retroarch / "build-inputs.lock.json"
            builder.save(lock_path, lock)
            environment = builder.compiler_environment(RECIPE)
            with patch.object(builder, "ROOT", retroarch), patch.object(builder, "PROJECT", project), patch.object(builder, "LOCK", lock_path), patch.object(builder, "compiler_environment", return_value=environment):
                result = builder.prepare(upstream, recipe, work)
                self.assertEqual((work / "source/engine.c").read_text(), "recipe-stage-two\n")
                self.assertEqual((work / "source/theme.c").read_text(), "project-theme\n")
                self.assertEqual((upstream / "engine.c").read_text(), "upstream\n")
                self.assertEqual(shared.read_text(), "recipe-theme\n")
                self.assertFalse(result["target_executed"])
                self.assertFalse(result["distribution_cleared"])
                with tarfile.open(work / "source-inputs.tar.gz") as archive:
                    names = archive.getnames()
                    self.assertIn("upstream/COPYING", names)
                    self.assertIn("modified/theme.c", names)
                    self.assertIn("recipe/build.sh", names)
                    self.assertFalse(any(".git" in Path(name).parts for name in names))
                    self.assertEqual(archive.extractfile("modified/engine.c").read(), b"recipe-stage-two\n")
                builder.validate_work(work)
                (work / "source/engine.c").write_text("tampered\n")
                with self.assertRaisesRegex(ValueError, "hash differs"):
                    builder.validate_work(work)
                with self.assertRaisesRegex(ValueError, "new, separate"):
                    builder.prepare(upstream, recipe, upstream / "build")


if __name__ == "__main__":
    unittest.main()
