# SPDX-License-Identifier: MIT
"""Optional pinned state-completion patch; no full engine/device qualification.

Compiles real patched SaveState queue, Process, slot-finalization and evidence
functions plus upstream SHA256. Emulator/serializer/platform fixture services
are explicit; their bytes are not real PSP states.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from test_native_menu_patch import block, checked


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOCK = ROOT / "state-evidence.lock.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StateEvidenceMetadataTests(unittest.TestCase):
    def test_optional_patch_is_locked_and_not_a_previous_full_build(self):
        lock = json.loads(LOCK.read_text())
        default = json.loads((ROOT / "source-lock.json").read_text())
        self.assertEqual(lock["upstream_commit"], default["upstream"]["commit"])
        self.assertEqual(digest(ROOT / lock["patch"]["path"]), lock["patch"]["sha256"])
        self.assertNotIn(lock["patch"]["path"], [item["path"] for item in default["patches"]])
        self.assertEqual(lock["patch"]["license"], "GPL-2.0-or-later")
        self.assertFalse(lock["qualification"]["full_engine_build"])
        self.assertFalse(lock["qualification"]["device_tested"])
        self.assertFalse(lock["qualification"]["external_exporter"])
        self.assertFalse(lock["qualification"]["resume_enabled"])


class StateEvidenceSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("PPSSPP_SOURCE_ROOT")
        if not source:
            raise unittest.SkipTest("Set PPSSPP_SOURCE_ROOT to the pinned v1.20.3 checkout")
        if not shutil.which("git") or not shutil.which("g++"):
            raise AssertionError("State source acceptance requires git and g++")
        cls.lock = json.loads(LOCK.read_text())
        cls.source = Path(source).resolve()
        cls.temporary = tempfile.TemporaryDirectory(prefix="ppsspp-state-evidence-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = Path(cls.temporary.name)
        for item in cls.lock["source_files"]:
            original = cls.source / item["path"]
            if not original.is_file() or digest(original) != item["sha256"]:
                raise AssertionError("Pinned state source preimage differs: " + str(original))
            target = cls.work / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
        patch = ROOT / cls.lock["patch"]["path"]
        checked(["git", "apply", "--check", str(patch)], cwd=cls.work)
        checked(["git", "apply", str(patch)], cwd=cls.work)
        for item in cls.lock["patched_files"]:
            if digest(cls.work / item["path"]) != item["sha256"]:
                raise AssertionError("Patched state source differs: " + item["path"])
        header = (cls.work / "Core/SaveState.h").read_text()
        source = (cls.work / "Core/SaveState.cpp").read_text()
        replacements = {
            "STATUS": block(header, "enum class Status", semicolon=True),
            "EVIDENCE_TYPE": block(header, "struct SlotEvidence", semicolon=True),
            "SAVE_START": block(source, "struct SaveStart", semicolon=True),
            "OPERATION_TYPE": block(source, "enum class OperationType", semicolon=True),
            "OPERATION": block(source, "struct Operation {", semicolon=True),
            "GAME_PREFIX_GENERATOR": block(source, "static std::string GenerateFullDiscId"),
            "GAME_PREFIX": block(source, "std::string GetGamePrefix("),
            "SLOT_FILENAME": block(source, "std::string GenerateSaveSlotFilename("),
            "SLOT_PATH": block(source, "Path GenerateSaveSlotPath("),
            "DELETE": block(source, "static void DeleteIfExists("),
            "RENAME": block(source, "static void RenameIfExists("),
            "ENQUEUE": block(source, "void Enqueue("),
            "SAVE": block(source, "void Save(const Path &filename"),
            "SAVE_SLOT": block(source, "void SaveSlot("),
            "FINGERPRINT_TYPE": block(source, "struct ProjectFileFingerprint", semicolon=True),
            "FINGERPRINT": block(source, "static bool ProjectFingerprintFile("),
            "VALIDATE_ID": block(source, "static bool ProjectEvidenceID("),
            "SAVE_EVIDENCE": block(source, "void SaveSlotWithEvidence("),
            "SESSION_CODE": "",
            "FLUSH": block(source, "std::vector<Operation> Flush("),
            "PROCESS": block(source, "void Process("),
            "INIT": block(source, "void Init("),
            "SHUTDOWN": block(source, "void Shutdown("),
        }
        code = (HERE / "state_evidence_acceptance.cpp.in").read_text()
        for marker, value in replacements.items():
            token = "/*@@" + marker + "@@*/"
            if code.count(token) != 1:
                raise AssertionError("State fixture marker differs: " + marker)
            code = code.replace(token, value)
        if "/*@@" in code:
            raise AssertionError("Unexpanded state fixture marker")
        cpp = cls.work / "state-evidence.cpp"
        cpp.write_text(code)
        cls.binary = cls.work / "state-evidence"
        command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Wno-unused-parameter",
                   "-Wno-unused-variable", "-DSDL=1", "-DMOBILE_DEVICE=1", "-I", str(cls.work),
                   str(cpp), str(cls.work / "Common/Crypto/sha256.cpp"), "-o", str(cls.binary)]
        checked(command, cwd=cls.work)
        cls.no_sdl = cls.work / "state-evidence-no-sdl"
        checked([item for item in command[:-1] if item != "-DSDL=1"] + [str(cls.no_sdl)], cwd=cls.work)

    def run_scenario(self, scenario: str, *, no_sdl=False):
        with tempfile.TemporaryDirectory(prefix="ppsspp-state-case-") as directory:
            binary = self.no_sdl if no_sdl else self.binary
            result = checked([str(binary), scenario, directory], cwd=self.work)
            return dict(line.split("=", 1) for line in result.stdout.splitlines())

    def test_actual_queued_process_produces_exact_completed_identity(self):
        result = self.run_scenario("success")
        self.assertEqual(result["engine"], digest(self.binary))
        self.assertEqual(result["game"], hashlib.sha256(b"fixture ROM bytes\n").hexdigest())
        self.assertEqual(result["state"], hashlib.sha256(b"fixture state bytes\n").hexdigest())

    def test_unprocessed_queue_screenshot_and_lost_kernel_cannot_produce_evidence(self):
        self.run_scenario("unprocessed")
        self.run_scenario("kernel-lost")

    def test_state_format_label_matches_locked_serializer_and_save_start(self):
        serializer = (self.work / "Common/Serialize/Serializer.h").read_text()
        source = (self.work / "Core/SaveState.cpp").read_text()
        self.assertIn("REVISION_TITLE = 5", serializer)
        self.assertIn("REVISION_CURRENT = REVISION_TITLE", serializer)
        self.assertIn('p.Section("SaveStart", 1, 3)', block(source, "void SaveStart::DoState("))

    def test_optional_patch_composes_with_existing_menu_patch(self):
        default = json.loads((ROOT / "source-lock.json").read_text())
        with tempfile.TemporaryDirectory(prefix="ppsspp-combined-patches-") as directory:
            work = Path(directory)
            for item in default["source_files"] + self.lock["source_files"]:
                original = self.source / item["path"]
                self.assertEqual(digest(original), item["sha256"])
                target = work / item["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, target)
            for item in default["patches"] + [self.lock["patch"]]:
                patch = ROOT / item["path"]
                checked(["git", "apply", "--check", str(patch)], cwd=work)
                checked(["git", "apply", str(patch)], cwd=work)
            for item in default["patched_files"] + self.lock["patched_files"]:
                self.assertEqual(digest(work / item["path"]), item["sha256"])

    def test_failed_final_rename_is_not_success(self):
        self.run_scenario("rename-failure")

    def test_serializer_failure_and_empty_state_have_no_evidence(self):
        for scenario in ("write-failure", "empty-state"):
            with self.subTest(scenario=scenario):
                self.run_scenario(scenario)

    def test_queue_and_each_network_rejection_deliver_failure(self):
        for scenario in ("network-slot", "network-save", "network-queue", "hardcore"):
            with self.subTest(scenario=scenario):
                self.run_scenario(scenario)

    def test_explicit_hardcore_save_permission_is_preserved(self):
        self.run_scenario("hardcore-save-allowed")

    def test_changed_game_path_disc_and_rom_have_no_evidence(self):
        for scenario in ("rom-changed", "rom-replaced", "disc-changed", "game-path-changed"):
            with self.subTest(scenario=scenario):
                self.run_scenario(scenario)

    def test_reinitialization_and_shutdown_invalidate_pending_evidence(self):
        for scenario in ("reinitialized", "shutdown"):
            with self.subTest(scenario=scenario):
                self.run_scenario(scenario)

    def test_bad_request_inactive_game_and_missing_disc_are_rejected(self):
        for scenario in ("bad-request", "bad-slot", "inactive", "missing-disc"):
            with self.subTest(scenario=scenario):
                self.run_scenario(scenario)

    def test_nonregular_empty_and_oversize_files_cannot_be_fingerprinted(self):
        for scenario in ("rom-directory", "rom-fifo", "rom-empty", "rom-oversize"):
            with self.subTest(scenario=scenario):
                self.run_scenario(scenario)

    def test_without_sdl_cannot_report_engine_evidence(self):
        self.assertEqual(self.run_scenario("success", no_sdl=True), {})


if __name__ == "__main__":
    unittest.main()
