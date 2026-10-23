# SPDX-License-Identifier: MIT
"""Failure-injection checks for complete host certification, not device evidence."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PROJECT = Path(__file__).resolve().parents[1]
RUNNER = PROJECT / "dev/certify.py"
spec = importlib.util.spec_from_file_location("host_certification", RUNNER)
certification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(certification)


class CertificationSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="certification-source-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Certification Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / "input.py").write_text("# original fixture\n")
        self.git("add", "input.py")
        self.git("commit", "-qm", "pinned fixture")
        self.commit = self.git("rev-parse", "HEAD").strip()

    def git(self, *arguments):
        return subprocess.run(["git", "-C", str(self.root), *arguments], check=True,
                              capture_output=True, text=True).stdout

    def verify(self):
        return certification.verify_checkout(self.root, self.commit, {"input.py": None})

    def test_exact_source_identity_is_recorded(self):
        record = self.verify()
        self.assertEqual(record["observed_commit"], self.commit)
        self.assertTrue(record["tracked_content_clean"])
        self.assertEqual(record["required_files_checked"], 1)

    def test_missing_or_nested_source_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            certification.verify_checkout(self.root / "absent", self.commit, {})
        nested = self.root / "nested"
        nested.mkdir()
        with self.assertRaisesRegex(ValueError, "checkout root"):
            certification.verify_checkout(nested, self.commit, {})

    def test_changed_commit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Source commit differs"):
            certification.verify_checkout(self.root, "0" * 40, {"input.py": None})

    def test_staged_and_unstaged_changes_are_rejected(self):
        for staged in (False, True):
            with self.subTest(staged=staged):
                (self.root / "input.py").write_text("# modified fixture\n")
                if staged:
                    self.git("add", "input.py")
                with self.assertRaisesRegex(ValueError, "changed tracked files"):
                    self.verify()
                self.git("reset", "--hard", "HEAD")

    def test_missing_required_file_and_bad_hash_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing or not regular"):
            certification.verify_checkout(self.root, self.commit, {"omitted.py": None})
        with self.assertRaisesRegex(ValueError, "differs from its lock"):
            certification.verify_checkout(self.root, self.commit, {"input.py": "0" * 64})

    def test_untracked_source_injection_is_rejected(self):
        (self.root / "injected.py").write_text("# untracked source\n")
        with self.assertRaisesRegex(ValueError, "untracked files"):
            self.verify()

    def test_assume_unchanged_does_not_hide_changed_source_bytes(self):
        self.git("update-index", "--assume-unchanged", "input.py")
        (self.root / "input.py").write_text("# hidden modification\n")
        self.assertEqual(self.git("diff", "--name-only", "HEAD"), "")
        with self.assertRaisesRegex(ValueError, "differs from Git HEAD"):
            self.verify()

    def test_assume_unchanged_does_not_hide_a_deleted_consumed_file(self):
        other = self.root / "consumed.py"
        other.write_text("# consumed by source acceptance tests\n")
        self.git("add", "consumed.py")
        self.git("commit", "-qm", "additional consumed input")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.git("update-index", "--assume-unchanged", "consumed.py")
        other.unlink()
        self.assertEqual(self.git("diff", "--name-only", "HEAD"), "")
        with self.assertRaisesRegex(ValueError, "missing without a sparse exclusion"):
            self.verify()

    def test_sparse_excluded_optional_input_may_be_absent(self):
        (self.root / "omitted.py").write_text("# intentionally outside the source test scope\n")
        self.git("add", "omitted.py")
        self.git("commit", "-qm", "optional input")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.git("sparse-checkout", "set", "--no-cone", "/input.py")
        self.assertFalse((self.root / "omitted.py").exists())
        self.assertEqual(self.verify()["materialized_files_checked"], 1)

    def test_hidden_executable_mode_change_is_rejected(self):
        self.git("config", "core.filemode", "false")
        self.git("update-index", "--assume-unchanged", "input.py")
        (self.root / "input.py").chmod(0o755)
        self.assertEqual(self.git("diff", "--name-only", "HEAD"), "")
        with self.assertRaisesRegex(ValueError, "file mode differs"):
            self.verify()

    def test_replacement_objects_cannot_substitute_the_pinned_source_tree(self):
        original = (self.root / "input.py").read_bytes()
        (self.root / "input.py").write_text("# replacement tree\n")
        self.git("add", "input.py")
        self.git("commit", "-qm", "replacement tree")
        replacement = self.git("rev-parse", "HEAD").strip()
        self.git("checkout", "--detach", self.commit)
        self.git("replace", self.commit, replacement)
        self.assertEqual((self.root / "input.py").read_bytes(), original)
        self.assertEqual(self.verify()["observed_commit"], self.commit)

    def test_group_execution_cannot_hide_a_missing_owner_execute_bit(self):
        source = self.root / "input.py"
        source.chmod(0o755)
        self.git("add", "input.py")
        self.git("commit", "-qm", "executable source fixture")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.git("config", "core.filemode", "false")
        self.git("update-index", "--assume-unchanged", "input.py")
        source.chmod(0o645)
        self.assertEqual(self.git("diff", "--name-only", "HEAD"), "")
        with self.assertRaisesRegex(ValueError, "file mode differs"):
            self.verify()

    def test_all_source_roots_must_be_explicit(self):
        records = []
        with self.assertRaisesRegex(ValueError, "SPRUCE_SOURCE_ROOT"):
            certification.verify_sources({}, records)
        self.assertEqual(records, [])

    def test_failed_preflight_replaces_previous_success_record(self):
        output = Path(self.temporary.name) / "certification.json"
        output.write_text('{"successful": true}\n')
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(certification, "verify_sources", side_effect=ValueError("injected mismatch")):
                self.assertEqual(certification.certify(output), 1)
        record = json.loads(output.read_text())
        self.assertFalse(record["successful"])
        self.assertEqual(record["phase"], "source-preflight")
        self.assertEqual(record["error"], "injected mismatch")
        self.assertEqual(record["suites"], [])


class CertificationResultTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="certification-suite-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.suite = self.root / "tests"
        self.suite.mkdir()
        self.report = self.root / "result.json"

    def run_case(self, body):
        (self.suite / "test_fixture.py").write_text("import unittest\n" + body)
        result = subprocess.run([sys.executable, str(RUNNER), "--test-directory", str(self.suite),
                                 "--test-report", str(self.report)], capture_output=True, text=True)
        return result, json.loads(self.report.read_text())

    def test_actual_counts_do_not_depend_on_an_expected_total(self):
        result, report = self.run_case("class Fixture(unittest.TestCase):\n"
                                       "    def test_one(self): self.assertTrue(True)\n"
                                       "    def test_two(self): self.assertEqual(2, 2)\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(report["successful"])
        self.assertEqual(report["tests_run"], 2)
        self.assertEqual(report["passed"], 2)

    def test_runtime_skip_is_a_failed_certification_with_reason(self):
        result, report = self.run_case("class Fixture(unittest.TestCase):\n"
                                       "    def test_missing_dependency(self): self.skipTest('injected missing source')\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report["successful"])
        self.assertEqual(report["skipped"], 1)
        self.assertEqual(report["tests_run"], 1)
        self.assertEqual(report["passed"], 0)
        self.assertEqual(report["skip_details"][0]["reason"], "injected missing source")

    def test_class_setup_skip_is_rejected_even_when_no_test_started(self):
        result, report = self.run_case("class Fixture(unittest.TestCase):\n"
                                       "    @classmethod\n"
                                       "    def setUpClass(cls): raise unittest.SkipTest('injected setup skip')\n"
                                       "    def test_one(self): pass\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["tests_run"], 0)
        self.assertEqual(report["skipped"], 1)

    def test_failures_import_errors_and_expected_failures_are_rejected(self):
        cases = (("class Fixture(unittest.TestCase):\n"
                  "    def test_one(self): self.fail('injected failure')\n", "failures"),
                 ("raise RuntimeError('injected import failure')\n", "errors"),
                 ("class Fixture(unittest.TestCase):\n"
                  "    @unittest.expectedFailure\n"
                  "    def test_one(self): self.fail('injected expected failure')\n", "expected_failures"))
        for body, field in cases:
            with self.subTest(field=field):
                result, report = self.run_case(body)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(report["successful"])
                self.assertEqual(report[field], 1)

    def test_empty_and_absent_suites_are_rejected(self):
        result, report = self.run_case("# Empty fixture suite\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["tests_run"], 0)
        absent = self.root / "absent"
        result = subprocess.run([sys.executable, str(RUNNER), "--test-directory", str(absent),
                                 "--test-report", str(self.report)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(self.report.read_text())
        self.assertFalse(report["successful"])
        self.assertIn("suite is missing", report["error"])


if __name__ == "__main__":
    unittest.main()
