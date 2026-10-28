# SPDX-License-Identifier: MIT
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

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

    def test_original_controller_source_exports_without_binaries_or_native_scopes(self):
        development = self.project / "dev"
        development.mkdir()
        for name in ("host_virtual_controller.c", "controller.so", "unreviewed.c"):
            (development / name).write_text("fixture source\n")
        native = self.project / "ppsspp/native.c"
        native.parent.mkdir()
        native.write_text("separately licensed native fixture\n")
        entries = dev_release.original_source_entries(self.project)
        names = {name for name, _ in entries}
        self.assertIn("smartpro-original-source/dev/host_virtual_controller.c", names)
        self.assertNotIn("smartpro-original-source/dev/controller.so", names)
        self.assertNotIn("smartpro-original-source/dev/unreviewed.c", names)
        self.assertNotIn("smartpro-original-source/ppsspp/native.c", names)
        exported = self.root / "source-export"
        dev_release.materialize_source(entries, exported)
        self.assertEqual((exported / "dev/host_virtual_controller.c").read_bytes(),
                         (development / "host_virtual_controller.c").read_bytes())

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

    def test_git_replacement_cannot_attribute_replacement_bytes_to_original_commit(self):
        original = self.git("rev-parse", "HEAD")
        (self.project / "psp_shell/__main__.py").write_text("print('replacement')\n")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "replacement")
        replacement = self.git("rev-parse", "HEAD")
        branch = self.git("symbolic-ref", "HEAD")
        self.git("update-ref", branch, original)
        self.git("replace", original, replacement)
        self.assertEqual(self.git("status", "--porcelain"), "")
        selection, _ = self.resolve()
        self.assertEqual(selection["frontend"]["commit"], original)
        self.assertTrue(selection["frontend"]["working_tree_modified"])

    def test_identity_comparison_uses_the_resolved_commit_after_head_moves(self):
        entries = self.entries()
        original = self.git("rev-parse", "HEAD")
        (self.project / "psp_shell/__main__.py").write_text("print('later')\n")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "later")
        self.assertTrue(release_descriptor.matches_committed_inventory(
            self.project, entries, self.lock, self.git, original))

    def test_descriptor_and_lock_are_read_from_captured_bytes(self):
        entries = self.entries()
        expected = copy.deepcopy(self.descriptor)
        self.path.write_text('{"qualification":{"hardware_qualified":true}}')
        self.lock.write_text("broken later edit")
        selection, _ = release_descriptor.resolve(self.project, self.path, entries, self.lock)
        self.assertEqual(selection["descriptor"], expected)

    def prepare_payload(self):
        (self.project / "assets/fonts").mkdir(parents=True)
        (self.project / "assets/fonts/OFL.txt").write_text("fixture font notice\n")
        (self.project / "tools").mkdir()
        for name in release_descriptor.PAYLOAD_TOOLS:
            (self.project / "tools" / name).write_text("# original fixture\n")
        (self.project / "psp_shell/retained.py").write_text("original = True\n")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "payload fixture")

    def build(self, output):
        return dev_release.build(self.project, output, self.descriptor["release_id"],
                                 self.descriptor["source_date_epoch"], source_lock=self.lock,
                                 include_source=True, release_descriptor=self.path)

    def test_late_live_edits_deletions_additions_and_lock_changes_cannot_mix_artifacts(self):
        self.prepare_payload()
        expected = dict(self.entries())
        original_build = dev_release.build_payload

        def change_live_tree(captured_project, *args, **kwargs):
            self.assertNotEqual(captured_project, self.project)
            (self.project / "psp_shell/__main__.py").write_text("print('late edit')\n")
            (self.project / "psp_shell/retained.py").unlink()
            (self.project / "psp_shell/late.py").write_text("must_not_ship = True\n")
            self.path.write_text("broken later descriptor")
            self.lock.write_text("broken later lock")
            return original_build(captured_project, *args, **kwargs)

        output = self.root / "release"
        with mock.patch.object(dev_release, "build_payload", side_effect=change_live_tree):
            self.build(output)
        release = self.descriptor["release_id"]
        with zipfile.ZipFile(output / (release + "-original-source.zip")) as archive:
            source = {name: archive.read(name) for name in archive.namelist()}
        for name, data in expected.items():
            self.assertEqual(source[name], data)
        with zipfile.ZipFile(output / (release + "-host-preview.zip")) as archive:
            prefix = "smartpro-host-preview/"
            receipt = json.loads(archive.read(prefix + "metadata/original-payload.json"))
            self.assertTrue(receipt["source_inventory_verified"])
            for item in receipt["source_payload"]:
                self.assertEqual(archive.read(prefix + item["payload_path"]),
                                 source["smartpro-original-source/" + item["source_path"]])
            self.assertNotIn(prefix + "app/psp_shell/late.py", archive.namelist())
            provenance = json.loads(archive.read(prefix + "metadata/source-provenance.json"))
            self.assertEqual(provenance["source_lock"], json.loads(expected[
                "smartpro-original-source/metadata/spruce-source-lock.json"]))
        report = json.loads((output / "build-report.json").read_bytes())
        self.assertFalse(report["release_selection"]["frontend"]["working_tree_modified"])
        self.assertTrue(report["payload_source_inventory_verified"])

    def test_changed_captured_payload_aborts_without_publishing_output(self):
        self.prepare_payload()
        original_build = dev_release.build_payload

        def tamper(captured_project, *args, **kwargs):
            (captured_project / "psp_shell/__main__.py").write_text("print('unexpected captured edit')\n")
            return original_build(captured_project, *args, **kwargs)

        output = self.root / "rejected"
        with mock.patch.object(dev_release, "build_payload", side_effect=tamper):
            with self.assertRaisesRegex(overlay.OverlayError, "differs from captured source inventory"):
                self.build(output)
        self.assertFalse(output.exists())
        self.assertFalse(any(path.name.startswith(".development-release-") for path in self.root.iterdir()))

    def test_default_release_and_timestamp_come_from_the_captured_descriptor(self):
        self.prepare_payload()
        original_resolve = dev_release.resolve_descriptor

        def changed_after_capture(*args, **kwargs):
            value = {**self.descriptor, "release_id": "smartpro-psp-0.1.0-later",
                     "source_date_epoch": self.descriptor["source_date_epoch"] + 86400}
            self.path.write_text(json.dumps(value))
            return original_resolve(*args, **kwargs)

        output = self.root / "captured-defaults"
        with mock.patch.object(dev_release, "resolve_descriptor", side_effect=changed_after_capture):
            dev_release.build(self.project, output, source_lock=self.lock, release_descriptor=self.path)
        report = json.loads((output / "build-report.json").read_bytes())
        self.assertEqual(report["release_id"], self.descriptor["release_id"])
        self.assertEqual(report["source_date_epoch"], self.descriptor["source_date_epoch"])

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
