# SPDX-License-Identifier: MIT
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / "packaging"))
import dev_release
import overlay
import release_descriptor


class ReleaseDescriptorTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="release-selection-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        (self.project / "packaging").mkdir(parents=True)
        (self.project / "psp_shell").mkdir()
        (self.project / "psp_shell/__main__.py").write_text("print('fixture')\n")
        (self.project / "LICENSE").write_text("original fixture\n")
        self.descriptor = json.loads((PROJECT / "packaging/current-release.json").read_bytes())
        self.path = self.project / "packaging/current-release.json"
        self.save()
        self.lock = self.root / "spruce-source-lock.json"
        self.lock.write_text(json.dumps({"base": self.descriptor["base"]}))
        self.git("init", "-q")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "fixture")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()

    def save(self):
        self.path.write_text(json.dumps(self.descriptor, sort_keys=True) + "\n")

    def entries(self):
        return dev_release.original_source_entries(self.project) + [
            ("smartpro-original-source/metadata/spruce-source-lock.json", self.lock.read_bytes())]

    def resolve(self):
        return release_descriptor.resolve(self.project, self.path, self.entries(), self.lock)

    def test_exact_frontend_revision_and_modified_source_are_distinct(self):
        selection, _ = self.resolve()
        self.assertEqual(selection["frontend"], {"commit": self.git("rev-parse", "HEAD"),
                                                "working_tree_modified": False})
        (self.project / "psp_shell/__main__.py").write_text("print('changed')\n")
        changed, _ = self.resolve()
        self.assertTrue(changed["frontend"]["working_tree_modified"])
        self.assertNotEqual(selection["source_inventory_sha256"], changed["source_inventory_sha256"])

    def test_git_index_flags_cannot_hide_modified_exported_source(self):
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                source = self.project / "psp_shell/__main__.py"
                original = source.read_bytes()
                self.git("update-index", flag, "project/psp_shell/__main__.py")
                try:
                    source.write_text("print('hidden change')\n")
                    self.assertEqual(self.git("status", "--porcelain"), "")
                    selection, _ = self.resolve()
                    self.assertTrue(selection["frontend"]["working_tree_modified"])
                finally:
                    source.write_bytes(original)
                    self.git("update-index", "--no-" + flag[2:], "project/psp_shell/__main__.py")
        self.assertFalse(self.resolve()[0]["frontend"]["working_tree_modified"])

    def test_git_index_flags_cannot_hide_missing_exported_source(self):
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                source = self.project / "psp_shell/__main__.py"
                original = source.read_bytes()
                self.git("update-index", flag, "project/psp_shell/__main__.py")
                try:
                    source.unlink()
                    self.assertEqual(self.git("status", "--porcelain"), "")
                    selection, _ = self.resolve()
                    self.assertTrue(selection["frontend"]["working_tree_modified"])
                finally:
                    source.write_bytes(original)
                    self.git("update-index", "--no-" + flag[2:], "project/psp_shell/__main__.py")
        self.assertFalse(self.resolve()[0]["frontend"]["working_tree_modified"])

    def test_sparse_exclusions_outside_export_scope_do_not_mark_source_modified(self):
        excluded = ("inherited-runtime/not-exported.bin", "project/ppsspp/native.c",
                    "project/evidence/retained.json", "project/assets/ignored.bin")
        for name in excluded:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("excluded fixture\n")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "excluded source fixture")
        for name in excluded:
            self.git("update-index", "--skip-worktree", name)
            (self.root / name).unlink()
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertFalse(self.resolve()[0]["frontend"]["working_tree_modified"])

    def test_changed_consumed_source_lock_marks_frontend_modified(self):
        lock = json.loads(self.lock.read_bytes())
        lock["additional_context"] = "changed outside the project directory"
        self.lock.write_text(json.dumps(lock))
        selection, _ = self.resolve()
        self.assertTrue(selection["frontend"]["working_tree_modified"])

    def test_source_export_rebuild_preserves_identity_and_rejects_changed_bytes(self):
        selection, snapshot = self.resolve()
        (self.project / "metadata").mkdir()
        (self.project / "metadata/release-source.json").write_text(json.dumps(snapshot))
        shutil.rmtree(self.root / ".git")
        self.assertEqual(self.resolve()[0], selection)
        (self.project / "psp_shell/__main__.py").write_text("print('changed')\n")
        with self.assertRaisesRegex(overlay.OverlayError, "source export changed"):
            self.resolve()

    def test_descriptor_cannot_select_another_base_or_unsupported_payload(self):
        original = copy.deepcopy(self.descriptor)
        for field, value in (("base", {"source_commit": "0" * 40}),
                             ("selected_original_payload", ["psp_shell"]),
                             ("selected_native_binaries", ["PPSSPPSDL_TrimUI"]),
                             ("qualification", {"hardware_qualified": True})):
            with self.subTest(field=field):
                self.descriptor = {**original, field: value}
                self.save()
                with self.assertRaises(overlay.OverlayError):
                    self.resolve()

    def test_missing_git_and_export_is_not_assigned_a_fake_frontend_revision(self):
        shutil.rmtree(self.root / ".git")
        with self.assertRaisesRegex(overlay.OverlayError, "Git identity unavailable"):
            self.resolve()

    def test_release_override_must_match_descriptor_before_any_output_is_built(self):
        output = self.root / "output"
        with self.assertRaisesRegex(overlay.OverlayError, "--release differs"):
            dev_release.build(self.project, output, "wrong-release", self.descriptor["source_date_epoch"],
                              source_lock=self.lock, release_descriptor=self.path)
        self.assertFalse(output.exists())

    def test_original_source_export_retains_certification_runner(self):
        (self.project / "dev").mkdir()
        (self.project / "dev/certify.py").write_text("print('certify')\n")
        self.assertIn("smartpro-original-source/dev/certify.py", dict(self.entries()))

    def test_original_performance_lock_is_exported_without_native_sources(self):
        (self.project / "ppsspp").mkdir()
        (self.project / "ppsspp/performance-source-lock.json").write_text('{"schema":1}\n')
        (self.project / "ppsspp/native.c").write_text("/* excluded upstream fixture */\n")
        entries = dict(self.entries())
        self.assertIn("smartpro-original-source/ppsspp/performance-source-lock.json", entries)
        self.assertNotIn("smartpro-original-source/ppsspp/native.c", entries)


if __name__ == "__main__":
    unittest.main()
