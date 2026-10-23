# SPDX-License-Identifier: MIT
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import component_audit as audit


class ComponentAuditTests(unittest.TestCase):
    def setUp(self):
        self.documents, self.provenance = audit.read_documents()
        self.original = copy.deepcopy(self.documents)

    def test_real_records_pair_replacement_custody_and_keep_all_gates_false(self):
        report = audit.audit(self.documents)
        self.assertTrue(report["records_consistent"])
        self.assertFalse(report["native_distribution_requested"])
        self.assertFalse(report["fresh_remote_retrieval_performed"])
        self.assertEqual(len(report["component_classifications"]), 16)
        self.assertEqual(len(report["reviewed_candidates"]), 2)
        self.assertTrue(all(r["matching_prior_custody_records"] for r in report["reviewed_candidates"]))
        for gate in ("native_binary_distribution_cleared", "source_use_verified", "hardware_qualified", "runtime_gates_enabled"):
            self.assertIs(report[gate], False)
        scopes = set(report["component_classifications"].values())
        self.assertTrue({"build-tools", "static-library", "target-dynamic-dependency", "runtime-assets"} <= scopes)

    def test_historical_candidates_do_not_acquire_replacement_custody(self):
        names = [k for k, (_, generation) in audit.CANDIDATES.items() if generation == "historical"]
        report = audit.audit(self.documents, candidates=names)
        self.assertTrue(all(not r["matching_prior_custody_records"] for r in report["reviewed_candidates"]))
        self.assertNotEqual(report["reviewed_candidates"][0]["sha256"],
                            audit.audit(self.documents)["reviewed_candidates"][0]["sha256"])

    def test_duplicate_component_or_candidate_rows_are_rejected(self):
        for record, field in (("ledger", "components"), ("release", "optional_native_references")):
            with self.subTest(field=field):
                docs = copy.deepcopy(self.original)
                docs[record][field].append(copy.deepcopy(docs[record][field][0]))
                with self.assertRaises(audit.AuditError):
                    audit.audit(docs)

    def test_unknown_components_or_candidates_require_explicit_scope_review(self):
        for record, field in (("ledger", "components"), ("release", "optional_native_references")):
            docs = copy.deepcopy(self.original)
            docs[record][field][0]["id"] = "unreviewed-extra-component"
            with self.subTest(field=field), self.assertRaises(audit.AuditError):
                audit.audit(docs)
        with self.assertRaises(audit.AuditError):
            audit.audit(self.documents, candidates=["a-file-path-or-unknown-target"])

    def test_selected_candidate_must_agree_with_its_descriptor_row(self):
        name = "ppsspp-state-r04-rebuild"
        self.documents["release"]["selected_native_binaries"] = [name]
        with self.assertRaises(audit.AuditError):
            audit.audit(self.documents)
        for row in self.documents["release"]["optional_native_references"]:
            row["selected"] = row["id"] == name
        report = audit.audit(self.documents)
        self.assertTrue(report["native_distribution_requested"])
        self.assertFalse(report["native_binary_distribution_cleared"])
        self.assertEqual(report["reviewed_candidates"][0]["status"], "blocked-on-component-review")

    def test_record_booleans_cannot_grant_clearance(self):
        for field in ("native_binary_distribution_cleared", "source_use_verified", "hardware_qualified",
                      "runtime_gates_enabled", "author_contact_sent"):
            docs = copy.deepcopy(self.original)
            docs["ledger"][field] = True
            with self.subTest(field=field), self.assertRaises(audit.AuditError):
                audit.audit(docs)
        self.documents["ledger"]["components"][0]["binary_distribution_cleared"] = True
        with self.assertRaises(audit.AuditError):
            audit.audit(self.documents)

    def test_changed_binary_or_source_pin_cannot_inherit_paired_receipt(self):
        for field, value in (("sha256", "a" * 64), ("source_commit", "b" * 40), ("recipe_commit", "c" * 40)):
            docs = copy.deepcopy(self.original)
            docs["release"]["optional_native_references"][2][field] = value
            with self.subTest(field=field), self.assertRaises(audit.AuditError):
                audit.audit(docs)

    def test_unrequested_historical_identity_and_patch_scope_are_still_checked(self):
        for field, value in (("sha256", "a" * 64), ("extension_set", [])):
            docs = copy.deepcopy(self.original)
            docs["release"]["optional_native_references"][0][field] = value
            with self.subTest(field=field), self.assertRaises(audit.AuditError):
                audit.audit(docs)

    def test_nested_component_hashes_and_revisions_must_be_exact(self):
        for field, value in (("commit", "v1.20.3"), ("sha256", "not-a-digest")):
            docs = copy.deepcopy(self.original)
            docs["ledger"]["components"][0]["identity"][field] = value
            with self.subTest(field=field), self.assertRaises(audit.AuditError):
                audit.audit(docs)

    def test_component_engine_pin_cannot_disagree_with_binary_source_lock(self):
        self.documents["ledger"]["components"][1]["identity"]["commit"] = "a" * 40
        with self.assertRaises(audit.AuditError):
            audit.audit(self.documents)

    def test_component_patch_digest_cannot_disagree_with_actual_project_patch(self):
        self.documents["ledger"]["components"][1]["identity"]["project_patches"][0]["sha256"] = "a" * 64
        with self.assertRaises(audit.AuditError):
            audit.audit(self.documents)

    def test_matching_forged_records_cannot_replace_actual_patch_byte_check(self):
        forged = "a" * 64
        self.documents["ledger"]["components"][1]["identity"]["project_patches"][0]["sha256"] = forged
        self.documents["ppsspp_lock"]["patches"][0]["sha256"] = forged
        self.documents["rebuild"]["ppsspp"]["project_patches"][0]["sha256"] = forged
        with self.assertRaises(audit.AuditError):
            audit.audit(self.documents)

    def test_changed_fixed_project_patch_cannot_inherit_prior_records(self):
        original = audit.safe_bytes

        def modified(root, path):
            value = original(root, path)
            return value + b"changed" if path.endswith("0002-save-slot-completion-evidence.patch") else value

        with patch.object(audit, "safe_bytes", side_effect=modified), self.assertRaises(audit.AuditError):
            audit.audit(self.documents)

    def test_missing_corresponding_source_receipt_is_not_paired_custody(self):
        self.documents["retention"]["artifacts"] = [
            row for row in self.documents["retention"]["artifacts"] if row["id"] != "ppsspp-source"]
        with self.assertRaises(audit.AuditError):
            audit.audit(self.documents)

    def test_reordered_or_short_retained_parts_are_rejected(self):
        for mutation in ("order", "size"):
            docs = copy.deepcopy(self.original)
            row = next(x for x in docs["retention"]["artifacts"] if x["id"] == "ra-source")
            if mutation == "order":
                row["parts"][0]["order"] = 1
            else:
                row["parts"][0]["size_bytes"] -= 1
            with self.subTest(mutation=mutation), self.assertRaises(audit.AuditError):
                audit.audit(docs)

    def test_absent_retrieval_claim_is_reported_without_inventing_new_retrieval(self):
        row = next(x for x in self.documents["retention"]["artifacts"] if x["id"] == "ppsspp-source")
        row["retained_storage_retrieval_verified"] = False
        report = audit.audit(self.documents)
        self.assertFalse(report["reviewed_candidates"][0]["matching_prior_custody_records"])
        self.assertFalse(report["fresh_remote_retrieval_performed"])

    def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected(self):
        for raw in (b'{"schema":1,"schema":1}', b'{"schema":NaN}'):
            with self.subTest(raw=raw), patch.object(audit, "safe_bytes", return_value=raw):
                with self.assertRaises(audit.AuditError):
                    audit.read_documents()

    def test_source_byte_check_uses_git_blob_and_does_not_compare_excerpt_hash_to_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = b"a full source fixture\nwith more than an excerpt\n"
            (root / "source.txt").write_bytes(data)
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            source = {"fresh_primary_source_review": {"source_files": [{
                "id": "fixture", "url": "https://github.com/example/repo/blob/" + "a" * 40 + "/source.txt",
                "scope": "lines 1-1", "sha256_of_returned_text": hashlib.sha256(b"a full source fixture\n").hexdigest(),
                "git_blob_sha": blob}]}}
            checks = audit.source_checks(source, {"example/repo": root})
            self.assertEqual(checks[0]["status"], "whole-file-identity-matched")
            (root / "source.txt").write_bytes(data + b"changed")
            with self.assertRaises(audit.AuditError):
                audit.source_checks(source, {"example/repo": root})

    def test_symlinks_traversal_and_fifo_inputs_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "regular").write_bytes(b"record")
            (root / "link").symlink_to(root / "regular")
            (root / "directory-link").symlink_to(root, target_is_directory=True)
            os.mkfifo(root / "pipe")
            for name in ("../regular", "/regular", "link", "directory-link/regular", "pipe"):
                with self.subTest(name=name), self.assertRaises((audit.AuditError, OSError)):
                    audit.safe_bytes(root, name)

    def test_oversized_or_changed_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "file").write_bytes(b"small record")
            with patch.object(audit, "MAX_INPUT", 3), self.assertRaises(audit.AuditError):
                audit.safe_bytes(root, "file")
            with patch.object(audit, "fingerprint", side_effect=[1, 2]), self.assertRaises(audit.AuditError):
                audit.safe_bytes(root, "file")

    def test_source_url_cannot_supply_a_local_traversal_or_mutable_revision(self):
        for suffix in ("main/file", "a" * 40 + "/../secret", "a" * 40 + "/%2e%2e/secret"):
            docs = copy.deepcopy(self.original)
            row = docs["ledger"]["fresh_primary_source_review"]["source_files"][0]
            row.pop("immutable_url", None)
            row["url"] = "https://github.com/example/repo/blob/" + suffix
            with self.subTest(suffix=suffix), self.assertRaises(audit.AuditError):
                audit.audit(docs)

    def test_cli_consistency_success_is_distinct_from_native_readiness(self):
        with patch("builtins.print"):
            self.assertEqual(audit.main([]), 0)
            self.assertEqual(audit.main(["--require-native-ready"]), 3)


if __name__ == "__main__":
    unittest.main()
