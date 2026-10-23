# SPDX-License-Identifier: MIT
"""Synthetic casebooks can become complete proposals, never device authority."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

from tools import qualification_review as qualification

recorder = qualification.recorder


class QualificationReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="qualification-host-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root, self.card, self.session = (self.base / name for name in ("root", "card", "session"))
        self.raw = self.base / "raw-evidence"
        for path in (self.root, self.card, self.raw):
            path.mkdir(mode=0o700)
        (self.root / "proc/device-tree").mkdir(parents=True)
        (self.root / "proc/device-tree/model").write_text("TrimUI Smart Pro TG5040")
        (self.root / "etc").mkdir()
        (self.root / "etc/version").write_text("1.1.1")
        (self.root / "proc/mounts").write_text("/dev/mmcblk0p1 /mnt/SDCARD vfat rw 0 0\n")
        native = self.root / "usr/trimui/bin/MainUI"
        native.parent.mkdir(parents=True)
        header = bytearray(64)
        header[:6] = b"\x7fELF\x02\x01"
        header[18:20] = (183).to_bytes(2, "little")
        native.write_bytes(header)  # Static synthetic header; never executable.
        paths = qualification.required_installed_paths() | {"Emu/PSP/PPSSPPSDL_TrimUI", "RetroArch/ra64.universal"}
        self.installed = {}
        for name in paths:
            path = self.card / name
            path.parent.mkdir(parents=True, exist_ok=True)
            content = ("# synthetic non-executable host fixture: " + name + "\n").encode()
            path.write_bytes(content)
            self.installed[name] = hashlib.sha256(content).hexdigest()
        profile = json.loads(recorder.DEFAULT_PROFILE.read_text())
        profile["baseline_files"] = self.installed
        self.profile = self.base / "profile.json"
        self.profile.write_bytes(recorder.encoded(profile))
        recorder.create(self.session, self.profile)
        self.scope = qualification.template(self.session)
        self.scope["candidate"].update(frontend_commit="a" * 40, signer_sha256="b" * 64, installed_files=self.installed)
        self.scope["device"].update(firmware="1.1.1", filesystem="vfat")
        self.scope["save_policy"] = {"Saves/saves/fixture.sav": "unchanged"}
        self.raw_number = 0
        for role, name in (("candidate_package", "package_sha256"), ("candidate_descriptor", "release_descriptor_sha256")):
            item = self.artifact(role)
            self.scope["identity_evidence"].append(item)
            self.scope["candidate"][name] = item["sha256"]
        prefix = "App/PSPMode/integration/app/"
        source_rows = [{"path": name.removeprefix(prefix), "sha256": hashed, "size": (self.card / name).stat().st_size}
                       for name, hashed in sorted(self.installed.items()) if name.startswith(prefix)]
        source_rows.append({"path": "packaging/current-release.json", "sha256": self.scope["candidate"]["release_descriptor_sha256"], "size": 1})
        source_rows.sort(key=lambda item: item["path"])
        self.scope["candidate"]["source_inventory_sha256"] = hashlib.sha256(json.dumps(source_rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        source_record = {"schema": 1, "descriptor_sha256": self.scope["candidate"]["release_descriptor_sha256"],
                         "frontend": {"commit": self.scope["candidate"]["frontend_commit"], "working_tree_modified": False},
                         "source_inventory": source_rows, "source_inventory_sha256": self.scope["candidate"]["source_inventory_sha256"]}
        self.scope["identity_evidence"].append(self.artifact("candidate_source_inventory", recorder.encoded(source_record)))
        for runtime in self.scope["runtimes"]:
            runtime.update(binary_sha256=self.installed[runtime["installed_path"]], source_commit="c" * 40)
        save = self.card / "Saves/saves/fixture.sav"
        save.parent.mkdir(parents=True)
        save.write_bytes(b"synthetic battery save; no owner data")
        for phase in ("before", "after"):
            recorder.capture(self.session, phase, self.root, self.card, saves=["Saves/saves/fixture.sav"])
        self.clock = datetime(2026, 10, 23, tzinfo=timezone.utc)
        self.boot_number = 0

    def artifact(self, role, content=None):
        self.raw_number += 1
        name = "raw-%04d" % self.raw_number
        content = content if content is not None else ("Synthetic retained artifact %s %s" % (name, role)).encode()
        (self.raw / name).write_bytes(content)
        return {"path": name, "sha256": hashlib.sha256(content).hexdigest(), "scope": role}

    def observation(self, case, test="case", context="core", cycle=1, *, provenance="host_fixture"):
        key = next(item for item in qualification._requirements(self.scope) if item[:3] == (case, test, context))
        runtime = next((item for item in self.scope["runtimes"] if item["id"] == context), None)
        self.boot_number += 1
        started = self.clock
        self.clock += timedelta(seconds=2)
        value = {"schema": 1, "kind": "qualification-observation", "scope_sha256": qualification.scope_digest(self.scope),
                 "provenance": provenance, "test": test, "context": context, "cycle": cycle,
                 "boot_id": str(uuid.UUID(int=self.boot_number)), "started_at": started.isoformat(),
                 "ended_at": (started + timedelta(seconds=1)).isoformat(),
                 "runtime_sha256": runtime["binary_sha256"] if runtime else None,
                 "runtime_source_commit": runtime["source_commit"] if runtime else None,
                 "raw": [self.artifact(role) for role in sorted(key[4])], "state": None, "retest_of": None}
        if test == "state_resume":
            value["state"] = {"game_sha256": "d" * 64, "state_sha256": "e" * 64, "slot": 0,
                              "save_boot_id": value["boot_id"], "load_boot_id": value["boot_id"]}
        if test == "native_engine":
            for item in value["raw"]:
                if item["scope"] == "corresponding_source":
                    replacement = self.artifact("corresponding_source", b"exact synthetic corresponding-source archive")
                    self.assertEqual(replacement["sha256"], runtime["source_archive_sha256"])
                    item.update(replacement)
        return value

    def record(self, case, test="case", context="core", cycle=1, *, status="pass", observation=None):
        value = observation or self.observation(case, test, context, cycle)
        return qualification.record_observation(self.session, self.scope, case, status, value, self.raw)

    def review(self, **kwargs):
        return qualification.review(self.session, self.scope, self.raw, **kwargs)

    def complete_casebook(self, *, provenance="host_fixture"):
        for case, test, context, minimum, _ in qualification._requirements(self.scope):
            total = 5 if test == "cold_boot" else minimum
            for cycle in range(1, total + 1):
                self.record(case, test, context, cycle,
                            observation=self.observation(case, test, context, cycle, provenance=provenance))

    def issue_codes(self, report):
        return {item["code"] for item in report["issues"]}

    def test_template_preserves_unknowns_and_all_original_source_module_expectations(self):
        value = qualification.template(self.session)
        self.assertIsNone(value["candidate"]["frontend_commit"])
        self.assertEqual(set(value["candidate"]["installed_files"]), qualification.required_installed_paths())
        self.assertTrue(all(item is None for item in value["candidate"]["installed_files"].values()))
        self.assertFalse(value["runtimes"][0]["state_resume"])
        self.assertIn("ports", value["excluded_features"])
        self.assertEqual(qualification.validate_scope(value), value)

    def test_empty_current_casebook_reports_per_context_missing_cycles_and_exclusions(self):
        report = self.review()
        self.assertEqual(report["status"], "incomplete")
        self.assertFalse(report["evidence_structurally_complete"])
        requirements = {(item["test"], item["context"]): item["required"] for item in report["context_cycles"]}
        for context in ("ppsspp", "retroarch"):
            self.assertEqual(requirements[("launch_quit", context)], 20)
        for context in ("classic", "psp", "ppsspp", "retroarch"):
            self.assertEqual(requirements[("sleep_wake", context)], 10)
        self.assertEqual(report["cases"]["ports"]["status"], "excluded")
        self.assertFalse(report["hardware_qualified"])
        self.assertFalse(report["production_configuration_generated"])

    def test_observation_template_leaves_actual_provenance_times_and_raw_evidence_unknown(self):
        value = qualification.observation_template(self.scope, "launch_return", "launch_quit", "ppsspp", 1)
        self.assertIsNone(value["provenance"])
        self.assertIsNone(value["boot_id"])
        self.assertIsNone(value["started_at"])
        self.assertTrue(all(item["sha256"] is None and item["path"] is None for item in value["raw"]))
        with self.assertRaises(ValueError):
            qualification.record_observation(self.session, self.scope, "launch_return", "pass", value, self.raw)
        with self.assertRaisesRegex(ValueError, "outside"):
            qualification.observation_template(self.scope, "boot", "launch_quit", "ppsspp", 1)

    def test_completed_host_casebook_remains_host_only_without_any_gate_promotion(self):
        self.complete_casebook()
        report = self.review()
        self.assertEqual(report["issues"], [])
        self.assertTrue(report["evidence_structurally_complete"])
        self.assertEqual(report["status"], "host_or_static_evidence_only")
        self.assertFalse(report["physical_operator_claims_complete"])
        for field in ("hardware_qualified", "runtime_verified", "source_use_verified", "distribution_cleared", "automatic_activation"):
            self.assertIs(report[field], False)
        self.assertEqual(report["independent_review"]["status"], "not_supplied")
        self.assertTrue(report["review_required"])

    def test_physical_operator_label_cannot_turn_mounted_host_snapshots_into_physical_evidence(self):
        self.complete_casebook(provenance="physical_operator")
        report = self.review()
        self.assertTrue(report["evidence_structurally_complete"])
        self.assertFalse(report["physical_operator_claims_complete"])
        self.assertEqual(report["status"], "host_or_static_evidence_only")
        self.assertFalse(report["hardware_qualified"])

    def test_existing_free_text_all_pass_notes_cannot_substitute_for_detailed_casebook(self):
        for case in recorder.CASES:
            recorder.record(self.session, case, "pass", "Synthetic all-pass note without raw cycle proof")
        self.assertTrue(recorder.report(self.session)["operator_cases_all_pass"])
        report = self.review()
        self.assertIn("incomplete_or_inconsistent_attempt", self.issue_codes(report))
        self.assertFalse(report["evidence_structurally_complete"])

    def test_unknown_candidate_runtime_and_support_matrix_remain_explicit(self):
        self.scope["candidate"]["frontend_commit"] = None
        self.scope["candidate"]["installed_files"].pop(next(iter(qualification.required_installed_paths())))
        self.scope["runtimes"][0]["source_commit"] = None
        self.scope["device"]["firmware"] = None
        report = self.review()
        self.assertTrue({"missing_candidate_identity", "incomplete_expected_installed_inventory", "missing_runtime_identity",
                         "missing_device_support_matrix"}.issubset(self.issue_codes(report)))

    def test_observed_module_runtime_firmware_and_filesystem_must_match_expected(self):
        self.scope["candidate"]["installed_files"]["App/PyUI/launch.sh"] = "0" * 64
        self.scope["device"].update(firmware="1.0.4", filesystem="exfat")
        report = self.review()
        self.assertIn("observed_candidate_inventory_incomplete_or_changed", self.issue_codes(report))
        self.assertIn("observed_device_or_source_identity_mismatch", self.issue_codes(report))
        self.assertIn("observed_filesystem_missing_or_mismatched", self.issue_codes(report))

    def test_record_helper_appends_existing_hash_linked_attempts_without_touching_snapshot(self):
        raw_snapshot = (self.session / "before.json").read_bytes()
        first = self.record("input", context="classic", status="fail")
        second_observation = self.observation("input", context="classic")
        first_raw = (self.session / "input/001.json").read_bytes()
        second_observation["retest_of"] = hashlib.sha256(first_raw).hexdigest()
        second = self.record("input", context="classic", observation=second_observation)
        self.assertEqual(second["previous_sha256"], hashlib.sha256(first_raw).hexdigest())
        self.assertEqual((self.session / "input/001.json").read_bytes(), first_raw)
        self.assertEqual((self.session / "before.json").read_bytes(), raw_snapshot)
        report = self.review()
        history = [item for item in report["retained_attempt_history"] if item["case"] == "input"]
        self.assertEqual([item["status"] for item in history], ["fail", "pass"])
        self.assertFalse(first["hardware_qualified"])

    def test_duplicate_cycle_without_explicit_retest_reference_does_not_inflate_pass_count(self):
        self.record("boot", "cold_boot", "classic", 1)
        self.record("boot", "cold_boot", "classic", 1)
        report = self.review()
        self.assertIn("incomplete_or_inconsistent_attempt", self.issue_codes(report))
        row = next(item for item in report["context_cycles"] if item["test"] == "cold_boot" and item["context"] == "classic")
        self.assertEqual(row["passed"], 1)

    def test_passing_retest_cannot_predate_the_failure_it_supersedes(self):
        failed = self.observation("input", context="classic")
        self.record("input", status="fail", observation=failed)
        replacement = self.observation("input", context="classic")
        replacement.update(started_at=(self.clock - timedelta(hours=1)).isoformat(),
                           ended_at=(self.clock - timedelta(minutes=59)).isoformat(),
                           retest_of=hashlib.sha256((self.session / "input/001.json").read_bytes()).hexdigest())
        self.record("input", observation=replacement)
        report = self.review()
        self.assertIn("incomplete_or_inconsistent_attempt", self.issue_codes(report))
        self.assertEqual(report["cases"]["input"]["status"], "fail")
        history = [item for item in report["retained_attempt_history"] if item["case"] == "input"]
        self.assertEqual([item["status"] for item in history], ["fail"])

    def test_numbered_cycle_order_cannot_run_backwards_even_without_overlap(self):
        second = self.observation("boot", "cold_boot", "classic", 2)
        first = self.observation("boot", "cold_boot", "classic", 1)
        self.record("boot", observation=first)
        self.record("boot", observation=second)
        report = self.review()
        issue = next(item for item in report["issues"] if item["code"] == "missing_or_failed_context_cycles"
                     and item["case"] == "boot" and item["test"] == "cold_boot" and item["context"] == "classic")
        self.assertTrue(issue["contiguous"])
        self.assertFalse(issue["chronological"])

    def test_later_retest_of_earlier_cycle_preserves_valid_first_execution_order(self):
        self.record("boot", "cold_boot", "classic", 1, status="fail")
        self.record("boot", "cold_boot", "classic", 2)
        replacement = self.observation("boot", "cold_boot", "classic", 1)
        replacement["retest_of"] = hashlib.sha256((self.session / "boot/001.json").read_bytes()).hexdigest()
        self.record("boot", observation=replacement)
        report = self.review()
        self.assertNotIn("incomplete_or_inconsistent_attempt", self.issue_codes(report))
        row = next(item for item in report["context_cycles"] if item["test"] == "cold_boot" and item["context"] == "classic")
        self.assertTrue(row["complete"])
        self.assertEqual(row["passed"], 2)

    def test_cycle_gaps_overlaps_and_reused_cold_boot_identity_are_rejected(self):
        first = self.observation("boot", "cold_boot", "classic", 1)
        second = self.observation("boot", "cold_boot", "psp", 2)
        second.update(started_at=first["started_at"], ended_at=first["ended_at"], boot_id=first["boot_id"])
        self.record("boot", observation=first)
        self.record("boot", observation=second)
        report = self.review()
        self.assertIn("cold_boot_total_or_unique_boot_ids_missing", self.issue_codes(report))
        self.assertIn("overlapping_cycle_intervals", self.issue_codes(report))
        row = next(item for item in report["context_cycles"] if item["test"] == "cold_boot" and item["context"] == "psp")
        self.assertFalse(row["contiguous"] if "contiguous" in row else row["complete"])

    def test_same_path_raw_artifact_replacement_or_missing_file_invalidates_attempt(self):
        value = self.observation("input", context="classic")
        self.record("input", observation=value)
        (self.raw / value["raw"][0]["path"]).write_bytes(b"changed same path")
        report = self.review()
        self.assertIn("incomplete_or_inconsistent_attempt", self.issue_codes(report))
        self.assertFalse(report["evidence_structurally_complete"])

    def test_empty_special_symlink_and_traversal_raw_files_are_refused(self):
        value = self.observation("input", context="classic")
        item = value["raw"][0]
        path = self.raw / item["path"]
        path.unlink()
        path.symlink_to(self.profile)
        with self.assertRaises((OSError, ValueError)):
            self.record("input", observation=value)
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(ValueError):
            self.record("input", observation=value)
        item["path"] = "../profile.json"
        with self.assertRaisesRegex(ValueError, "evidence path"):
            self.record("input", observation=value)

    def test_cold_boot_and_other_raw_evidence_cannot_be_falsely_cross_scoped(self):
        value = self.observation("boot", "cold_boot", "classic")
        value["raw"][0]["scope"] = "sleep_wake"
        self.record("boot", observation=value)
        report = self.review()
        self.assertIn("incomplete_or_inconsistent_attempt", self.issue_codes(report))

    def test_card_overlay_and_internal_recovery_are_three_distinct_evidence_scopes(self):
        value = self.observation("restore")
        first = value["raw"][0]
        for item in value["raw"]:
            if item["scope"] in {"card_restore", "overlay_restore", "internal_restore"}:
                item.update(path=first["path"], sha256=first["sha256"])
        self.record("restore", observation=value)
        self.assertIn("incomplete_or_inconsistent_attempt", self.issue_codes(self.review()))

    def test_state_resume_requires_exact_game_state_slot_and_same_boot(self):
        runtime = self.scope["runtimes"][0]
        runtime["state_resume"] = True
        self.scope["excluded_features"].pop("state_resume")
        value = self.observation("save_resume", "state_resume", runtime["id"])
        value["state"]["load_boot_id"] = str(uuid.UUID(int=999))
        with self.assertRaisesRegex(ValueError, "same-boot"):
            self.record("save_resume", observation=value)
        value["state"]["load_boot_id"] = value["boot_id"]
        value["state"]["slot"] = True
        with self.assertRaises(ValueError):
            self.record("save_resume", observation=value)

    def test_native_candidate_requires_actual_matching_corresponding_source_artifact(self):
        runtime = self.scope["runtimes"][0]
        runtime["kind"] = "native_candidate"
        runtime["source_archive_sha256"] = hashlib.sha256(b"exact synthetic corresponding-source archive").hexdigest()
        self.scope["excluded_features"].pop("native_candidates")
        value = self.observation("native_controls", "native_engine", runtime["id"])
        next(item for item in value["raw"] if item["scope"] == "corresponding_source")["sha256"] = "0" * 64
        note = qualification.validate_observation(value, "native_controls", self.scope)
        recorder.record(self.session, "native_controls", "pass", note)
        self.assertIn("incomplete_or_inconsistent_attempt", self.issue_codes(self.review()))

    def test_unsupported_and_excluded_runtime_scopes_never_become_passing_titles(self):
        self.scope["omitted_runtimes"] = [{"id": "san_andreas", "status": "unsupported", "reason": "No verified original-device contract."}]
        report = self.review()
        self.assertEqual(report["omitted_runtimes"][0]["status"], "unsupported")
        self.assertEqual(report["cases"]["ports"]["status"], "excluded")
        self.scope["omitted_runtimes"][0]["id"] = "ppsspp"
        with self.assertRaisesRegex(ValueError, "omitted"):
            self.review()

    def test_selected_port_adds_individual_title_launch_sleep_and_save_contracts(self):
        port = {"id": "sonic_mania", "engine": "port", "kind": "port", "installed_path": "Data/ports/sonic/SonicMania",
                "binary_sha256": "f" * 64, "source_commit": "f" * 40, "source_archive_sha256": None, "state_resume": False}
        self.scope["runtimes"].append(port)
        self.scope["excluded_features"].pop("ports")
        report = self.review()
        port_rows = [item for item in report["context_cycles"] if item["context"] == port["id"]]
        self.assertEqual({(item["test"], item["required"]) for item in port_rows}, {("case", 1), ("launch_quit", 20), ("sleep_wake", 10)})
        self.assertNotEqual(report["cases"]["ports"]["status"], "excluded")

    def test_independent_reviewer_statement_is_distinct_from_completeness_and_cannot_qualify(self):
        item = self.artifact("reviewer_statement")
        reviewer = {"schema": 1, "kind": "qualification-reviewer-scope", "scope_sha256": qualification.scope_digest(self.scope),
                    "casebook_sha256": self.review()["casebook_sha256"],
                    "reviewer_sha256": "a" * 64, "independent": True, "scopes": ["core"], "decision": "accept", "evidence": item}
        report = self.review(reviewer=reviewer)
        declared = report["independent_review"]
        self.assertEqual(declared["status"], "operator_supplied_statement")
        self.assertTrue(declared["all_scopes_declared"])
        self.assertFalse(declared["authenticated"])
        self.assertFalse(declared["qualification_granted"])
        self.assertFalse(report["evidence_structurally_complete"])
        self.assertFalse(report["hardware_qualified"])
        self.record("input", context="classic")
        revised = self.review(reviewer=reviewer)
        self.assertEqual(revised["independent_review"]["status"], "stale_casebook_statement")
        self.assertFalse(revised["independent_review"]["casebook_binding_matches"])
        reviewer["scopes"] = ["native:unselected"]
        with self.assertRaises(ValueError):
            self.review(reviewer=reviewer)

    def test_candidate_package_bytes_and_scope_hash_cannot_drift_between_attempts(self):
        value = self.observation("input", context="classic")
        value["scope_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "another candidate"):
            self.record("input", observation=value)
        item = self.scope["identity_evidence"][0]
        (self.raw / item["path"]).unlink()
        report = self.review()
        self.assertIn("candidate_raw_evidence_missing_or_changed", self.issue_codes(report))

    def test_source_inventory_list_digest_is_distinct_from_its_retained_json_file_hash(self):
        item = next(item for item in self.scope["identity_evidence"] if item["scope"] == "candidate_source_inventory")
        self.assertNotEqual(item["sha256"], self.scope["candidate"]["source_inventory_sha256"])
        self.assertEqual(qualification.source_inventory_identity(self.raw, item, self.scope["candidate"]),
                         self.scope["candidate"]["source_inventory_sha256"])
        self.scope["candidate"]["source_inventory_sha256"] = item["sha256"]
        self.assertIn("candidate_raw_evidence_missing_or_changed", self.issue_codes(self.review()))

    def test_rehashed_source_record_cannot_relabel_a_modified_frontend_or_installed_module(self):
        item = next(item for item in self.scope["identity_evidence"] if item["scope"] == "candidate_source_inventory")
        value = json.loads((self.raw / item["path"]).read_text())
        value["frontend"]["working_tree_modified"] = True
        replacement = self.artifact("candidate_source_inventory", recorder.encoded(value))
        item.update(replacement)
        self.assertIn("candidate_raw_evidence_missing_or_changed", self.issue_codes(self.review()))

    def test_save_policy_distinguishes_expected_gameplay_writes_from_unexpected_changes(self):
        path = self.session / "after.json"
        value = json.loads(path.read_text())
        value.pop("content_sha256")
        value["save_hashes_only"][0].update(size=7, sha256=hashlib.sha256(b"changed").hexdigest())
        value["save_comparison"][0]["unchanged"] = False
        path.write_bytes(recorder.encoded(recorder.checksummed(value)))
        report = self.review()
        self.assertIn("unexpected_battery_save_change", self.issue_codes(report))
        self.scope["save_policy"]["Saves/saves/fixture.sav"] = "gameplay_change_expected"
        report = self.review()
        self.assertNotIn("unexpected_battery_save_change", self.issue_codes(report))
        self.assertEqual(report["save_readback"]["expected_gameplay_changes"], 1)
        self.assertTrue(report["save_readback"]["native_readback_review_required"])
        self.assertFalse(report["hardware_qualified"])

    def test_declared_expected_save_write_must_actually_be_observed(self):
        self.scope["save_policy"]["Saves/saves/fixture.sav"] = "gameplay_change_expected"
        self.assertIn("expected_gameplay_save_change_not_observed", self.issue_codes(self.review()))

    def test_nested_raw_parent_replacement_during_hashing_cannot_inherit_old_evidence(self):
        parent = self.raw / "nested"
        parent.mkdir()
        content = b"synthetic nested artifact"
        (parent / "log").write_bytes(content)
        item = {"path": "nested/log", "scope": "built_in_input", "sha256": hashlib.sha256(content).hexdigest()}
        original = os.read
        replaced = []
        def changed(descriptor, count):
            result = original(descriptor, count)
            if result and not replaced:
                parent.rename(self.raw / "old-nested")
                parent.mkdir()
                (parent / "log").write_bytes(content)
                replaced.append(True)
            return result
        with mock.patch.object(qualification.os, "read", side_effect=changed), self.assertRaisesRegex(ValueError, "named raw artifact"):
            qualification._artifact(self.raw, item)

    def test_hash_budget_rejects_large_selected_artifact_before_reading_or_recording(self):
        value = self.observation("input", context="classic")
        with mock.patch.object(qualification, "MAX_TOTAL_RAW_BYTES", 1), self.assertRaisesRegex(ValueError, "aggregate hash budget"):
            self.record("input", observation=value)
        self.assertFalse((self.session / "input").exists())

    def test_snapshot_or_attempt_content_edits_are_rejected_by_existing_recorder(self):
        self.record("input", context="classic")
        path = self.session / "input/001.json"
        value = json.loads(path.read_text())
        value["status"] = "fail"
        path.write_bytes(recorder.encoded(value))
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.review()

    def test_plan_case_set_must_match_the_existing_thirteen_area_recorder(self):
        value = json.loads(qualification.DEFAULT_PLAN.read_text())
        value["cases"].pop("restore")
        plan = self.base / "bad-plan.json"
        plan.write_bytes(recorder.encoded(value))
        with self.assertRaisesRegex(ValueError, "plan case set"):
            self.review(plan=plan)

    def test_raw_artifact_changed_after_first_hash_is_rechecked_before_report(self):
        self.record("input", context="classic")
        original = qualification._artifact
        counts = {}
        def changed(root, item, **kwargs):
            result = original(root, item, **kwargs)
            key = item["path"]
            counts[key] = counts.get(key, 0) + 1
            if counts[key] == 1 and item["scope"] == "built_in_input":
                (self.raw / key).write_bytes(b"replaced during long review")
            return result
        with mock.patch.object(qualification, "_artifact", side_effect=changed):
            report = self.review()
        self.assertIn("raw_evidence_changed_during_review", self.issue_codes(report))

    def test_private_report_publication_is_new_external_and_preserves_existing_bytes(self):
        report = self.review()
        output = self.base / "proposal.json"
        receipt = qualification.publish(output, report, (self.session, self.raw))
        self.assertEqual(receipt["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
        original = output.read_bytes()
        with self.assertRaises(FileExistsError):
            qualification.publish(output, report, (self.session, self.raw))
        self.assertEqual(output.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, "outside"):
            qualification.publish(self.session / "proposal.json", report, (self.session, self.raw))

    def test_failed_publication_returns_no_receipt_and_never_deletes_uncertain_output(self):
        output = self.base / "uncertain.json"
        with mock.patch.object(recorder.os, "fsync", side_effect=OSError("fixture read-only storage")):
            with self.assertRaises(OSError):
                qualification.publish(output, self.review(), (self.session, self.raw))
        self.assertTrue(output.exists())

    def test_cli_reviews_existing_unrun_session_without_hardware_actions_or_activation(self):
        scope = self.base / "scope.json"
        scope.write_bytes(recorder.encoded(self.scope))
        output = self.base / "cli-proposal.json"
        result = subprocess.run([sys.executable, str(qualification.TOOLS / "qualification_review.py"), "review",
                                 "--session", str(self.session), "--scope", str(scope), "--evidence-root", str(self.raw),
                                 "--output", str(output)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(output.read_text())
        self.assertEqual(report["status"], "incomplete")
        self.assertFalse(report["automatic_activation"])
        self.assertFalse(report["hardware_qualified"])


if __name__ == "__main__":
    unittest.main()
