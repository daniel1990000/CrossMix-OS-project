# SPDX-License-Identifier: MIT
"""Local upstream changes create review work, never automatic updates."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import upstream_drift as drift


class UpstreamDriftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="drift-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / "base"
        self.base.mkdir()
        self.run_git(self.base, "init", "-q")
        self.run_git(self.base, "config", "user.name", "Drift Fixture")
        self.run_git(self.base, "config", "user.email", "fixture@example.invalid")
        (self.base / "UI").mkdir()
        (self.base / "UI/main.py").write_text("# original fixture\n")
        (self.base / "LICENSE").write_text("fixture terms\n")
        (self.base / "outside.txt").write_text("outside\n")
        self.commit(self.base)
        self.pin = self.run_git(self.base, "rev-parse", "HEAD").strip()
        self.candidate = Path(self.temp.name) / "candidate"
        self.run_git(self.base, "clone", "-q", str(self.base), str(self.candidate))
        self.run_git(self.candidate, "config", "user.name", "Drift Fixture")
        self.run_git(self.candidate, "config", "user.email", "fixture@example.invalid")

    def run_git(self, root, *args):
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True).stdout

    def commit(self, root):
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-qm", "fixture revision")

    def review(self):
        return drift.compare(self.base, self.candidate, self.pin, ("UI/", "LICENSE"),
                             required_files={"UI/main.py": hashlib.sha256(b"# original fixture\n").hexdigest()})

    def test_unchanged_revision_does_not_grant_qualification(self):
        report = self.review()
        self.assertEqual(report["changes"], [])
        self.assertFalse(report["review_required"])
        for field in ("pins_updated", "device_qualified", "candidate_executed", "distribution_cleared"):
            self.assertIs(report[field], False)

    def test_add_remove_mode_and_license_changes_have_exact_identities(self):
        (self.candidate / "UI/main.py").chmod(0o755)
        (self.candidate / "UI/new \u65e5\u672c.py").write_text("# new transitive fixture\n")
        (self.candidate / "LICENSE").unlink()
        (self.candidate / "outside.txt").write_text("changed outside\n")
        self.commit(self.candidate)
        report = self.review()
        changes = {item["path"]: item for item in report["changes"]}
        self.assertEqual(len(changes), 3)
        self.assertEqual(changes["UI/main.py"]["before"]["mode"], "100644")
        self.assertEqual(changes["UI/main.py"]["after"]["mode"], "100755")
        self.assertEqual(changes["UI/new \u65e5\u672c.py"]["change"], "added")
        self.assertEqual(changes["LICENSE"]["change"], "removed")
        self.assertIn("rights-and-notices", changes["LICENSE"]["review_areas"])
        self.assertTrue(report["scope_expansion_review_required"])
        self.assertEqual(report["changed_outside_scope"], 1)

    def test_symlink_is_metadata_and_is_never_followed(self):
        (self.candidate / "UI/link.py").symlink_to("/private/unreadable")
        self.commit(self.candidate)
        entry = self.review()["changes"][0]
        self.assertEqual(entry["after"]["mode"], "120000")
        self.assertEqual(entry["change"], "added")

    def test_submodule_identity_change_is_reviewed(self):
        self.run_git(self.candidate, "update-index", "--add", "--cacheinfo", "160000," + self.pin + ",UI/submodule")
        self.run_git(self.candidate, "commit", "-qm", "fixture gitlink")
        (self.candidate / "UI/submodule").mkdir()
        item = self.review()["changes"][0]
        self.assertEqual(item["after"]["kind"], "commit")
        self.assertEqual(item["after"]["git_object"], self.pin)

    def test_dirty_candidate_is_rejected(self):
        (self.candidate / "UI/main.py").write_text("# unreviewed\n")
        with self.assertRaisesRegex(ValueError, "changed tracked"):
            self.review()

    def test_hidden_dirty_candidate_is_rejected(self):
        self.run_git(self.candidate, "update-index", "--assume-unchanged", "UI/main.py")
        (self.candidate / "UI/main.py").write_text("# hidden\n")
        with self.assertRaisesRegex(ValueError, "differs from Git HEAD"):
            self.review()

    def test_candidate_fsmonitor_and_clean_filter_never_execute(self):
        marker = Path(self.temp.name) / "unexpected-execution"
        script = self.candidate / "hook.sh"
        script.write_text("#!/bin/sh\ntouch '" + str(marker) + "'\ncat\n")
        script.chmod(0o755)
        (self.candidate / ".gitattributes").write_text("*.py filter=fixture\n")
        self.commit(self.candidate)
        self.run_git(self.candidate, "config", "core.fsmonitor", str(script))
        self.run_git(self.candidate, "config", "filter.fixture.clean", str(script))
        self.run_git(self.candidate, "config", "filter.fixture.required", "true")
        self.assertFalse(self.review()["candidate_executed"])
        self.assertFalse(marker.exists())

    def test_git_replace_cannot_change_recorded_revision_meaning(self):
        (self.candidate / "UI/main.py").write_text("# alternate commit\n")
        self.commit(self.candidate)
        alternate = self.run_git(self.candidate, "rev-parse", "HEAD").strip()
        self.run_git(self.candidate, "checkout", "-q", "--detach", self.pin)
        self.run_git(self.candidate, "replace", self.pin, alternate)
        report = self.review()
        self.assertEqual(report["baseline_commit"], report["candidate_commit"])
        self.assertEqual(report["changes"], [])

    def test_wrong_baseline_and_untracked_injection_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "commit differs"):
            drift.compare(self.base, self.candidate, "0" * 40, ("UI/",))
        (self.candidate / "UI/untracked.py").write_text("# not committed\n")
        with self.assertRaisesRegex(ValueError, "untracked"):
            self.review()

    def test_sparse_omission_is_not_a_committed_removal(self):
        self.run_git(self.candidate, "sparse-checkout", "init", "--no-cone")
        self.run_git(self.candidate, "sparse-checkout", "set", "--no-cone", "/LICENSE")
        self.assertFalse((self.candidate / "UI/main.py").exists())
        self.assertEqual(self.review()["changes"], [])

    def test_ordinary_deleted_worktree_file_is_not_a_sparse_omission(self):
        (self.candidate / "UI/main.py").unlink()
        with self.assertRaisesRegex(ValueError, "missing without a sparse"):
            self.review()

    def test_recheck_catches_input_changed_during_review(self):
        real_tree = drift.tree
        def changed(root, commit):
            value = real_tree(root, commit)
            if root == self.candidate:
                (root / "UI/main.py").write_text("# raced\n")
            return value
        with mock.patch.object(drift, "tree", side_effect=changed), self.assertRaisesRegex(ValueError, "changed tracked"):
            self.review()

    def test_tree_refuses_revision_expressions_and_large_metadata(self):
        with self.assertRaisesRegex(ValueError, "exact SHA-1"):
            drift.tree(self.base, "HEAD")
        with mock.patch.object(drift, "MAX_TREE", 1), self.assertRaisesRegex(ValueError, "bound"):
            drift.tree(self.base, self.pin)

    def test_output_is_exclusive_outside_sources_and_fsynced(self):
        report = self.review()
        output = Path(self.temp.name) / "review.json"
        receipt = drift.publish(output, report, (self.base, self.candidate))
        self.assertEqual(receipt["report_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertEqual(json.loads(output.read_text())["candidate_commit"], self.pin)
        with self.assertRaises(FileExistsError):
            drift.publish(output, report, (self.base, self.candidate))
        with self.assertRaisesRegex(ValueError, "outside"):
            drift.publish(self.base / "report.json", report, (self.base, self.candidate))

    def test_failed_durable_write_retains_uncertain_bytes_without_receipt(self):
        output = Path(self.temp.name) / "failed.json"
        with mock.patch.object(drift.os, "fsync", side_effect=OSError("fixture full storage")):
            with self.assertRaises(OSError):
                drift.publish(output, self.review(), (self.base, self.candidate))
        self.assertTrue(output.exists())
        with self.assertRaises(FileExistsError):
            drift.publish(output, self.review(), (self.base, self.candidate))

    def test_failed_write_does_not_delete_a_replacement(self):
        output = Path(self.temp.name) / "failed.json"
        def replace(_):
            output.rename(output.with_suffix(".owned"))
            output.write_bytes(b"unrelated replacement")
            raise OSError("fixture storage failure")
        with mock.patch.object(drift.os, "fsync", side_effect=replace), self.assertRaises(OSError):
            drift.publish(output, self.review(), (self.base, self.candidate))
        self.assertEqual(output.read_bytes(), b"unrelated replacement")

    def test_parent_replacement_does_not_redirect_publication(self):
        parent = Path(self.temp.name) / "reports"
        parent.mkdir()
        moved = Path(self.temp.name) / "moved-reports"
        output = parent / "review.json"
        real_open = os.open
        def swap(name, flags, *args, **kwargs):
            if name == output.name and flags & os.O_CREAT:
                parent.rename(moved)
                parent.mkdir()
                output.write_bytes(b"unrelated new directory")
            return real_open(name, flags, *args, **kwargs)
        with mock.patch.object(drift.os, "open", side_effect=swap), self.assertRaisesRegex(ValueError, "changed during publication"):
            drift.publish(output, self.review(), (self.base, self.candidate))
        self.assertEqual(output.read_bytes(), b"unrelated new directory")
        self.assertTrue((moved / output.name).exists())


if __name__ == "__main__":
    unittest.main()
