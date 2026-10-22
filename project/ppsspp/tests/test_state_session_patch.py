# SPDX-License-Identifier: MIT
"""Real pinned private-session parser/caller/export with explicit engine fixtures."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_native_menu_patch import block, checked

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def packet(magic, fields):
    return magic + b"".join(str(len(value.encode())).encode() + b":" + value.encode() + b"," for value in fields)


def parse(data, magic=b"TPSE1R\n"):
    if not data.startswith(magic):
        raise AssertionError("bad magic")
    rest = data[len(magic):]
    fields = []
    while rest:
        length, rest = rest.split(b":", 1)
        count = int(length)
        fields.append(rest[:count].decode())
        if rest[count:count + 1] != b",":
            raise AssertionError("bad netstring")
        rest = rest[count + 1:]
    return fields


class StateSessionSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.environ.get("PPSSPP_SOURCE_ROOT")
        if not configured:
            raise unittest.SkipTest("Set PPSSPP_SOURCE_ROOT to pinned v1.20.3")
        cls.source = Path(configured)
        cls.temp = tempfile.TemporaryDirectory(prefix="ppsspp-session-source-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        base = json.loads((ROOT / "source-lock.json").read_text())
        api = json.loads((ROOT / "state-evidence.lock.json").read_text())
        session = json.loads((ROOT / "state-session.lock.json").read_text())
        for item in base["source_files"] + api["source_files"] + session["source_files"]:
            original = cls.source / item["path"]
            if sha(original) != item["sha256"]:
                raise AssertionError("Session source preimage differs: " + item["path"])
            target = cls.work / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
        for item in base["patches"] + [api["patch"], session["patch"]]:
            patch = ROOT / item["path"]
            if sha(patch) != item["sha256"]:
                raise AssertionError("Session patch differs")
            checked(["git", "apply", "--check", str(patch)], cwd=cls.work)
            checked(["git", "apply", str(patch)], cwd=cls.work)
        for item in session["patched_files"]:
            if sha(cls.work / item["path"]) != item["sha256"]:
                raise AssertionError("Session source postimage differs: " + item["path"])
        source = (cls.work / "Core/SaveState.cpp").read_text()
        header = (cls.work / "Core/SaveState.h").read_text()
        marker = source.index("\t// Explicit private-session extension")
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
            "SAVE_SLOT": block(source, "static void SaveSlotInternal("),
            "FINGERPRINT_TYPE": block(source, "struct ProjectFileFingerprint", semicolon=True),
            "FINGERPRINT": block(source, "static bool ProjectFingerprintFile("),
            "VALIDATE_ID": block(source, "static bool ProjectEvidenceID("),
            "SAVE_EVIDENCE": block(source, "void SaveSlotWithEvidence("),
            "SESSION_CODE": block(source, "void Load(const Path &filename") + "\n" + source[marker:source.index("\n\tbool UndoSaveSlot(", marker)],
            "FLUSH": block(source, "std::vector<Operation> Flush("),
            "PROCESS": block(source, "void Process("),
            "INIT": block(source, "void Init("),
            "SHUTDOWN": block(source, "void Shutdown("),
        }
        code = (HERE / "state_evidence_acceptance.cpp.in").read_text()
        code = code[:code.index("int main(")] + (HERE / "state_session_main.cpp.in").read_text()
        for marker, value in replacements.items():
            code = code.replace("/*@@" + marker + "@@*/", value)
        if "/*@@" in code:
            raise AssertionError("Missing session fixture substitution")
        cpp = cls.work / "state-session.cpp"
        cpp.write_text(code)
        cls.binary = cls.work / "state-session"
        checked(["g++", "-std=c++17", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Wno-unused-variable",
                 "-DSDL=1", "-DMOBILE_DEVICE=1", "-I", str(cls.work), str(cpp),
                 str(cls.work / "Common/Crypto/sha256.cpp"), "-o", str(cls.binary)], cwd=cls.work)

    def scenario(self, name, *, mutate=None):
        with tempfile.TemporaryDirectory(prefix="ppsspp-private-session-") as directory:
            root = Path(directory)
            state = root / "states/ULUS12345_1.00_2.ppst"
            state.parent.mkdir()
            game = root / "game ü.iso"
            game.write_bytes(b"fixture ROM bytes\n")
            state.write_bytes(b"fixture state bytes\n")
            private = root / "private"
            private.mkdir(mode=0o700)
            request = private / "request"
            resume = name.startswith("resume") or name == "wrong-state"
            fields = ["a" * 32, "b" * 32, "c" * 32, "fixture-boot", "4", "game:fixture", str(game), sha(game),
                      sha(self.binary), str(state.parent), "resume" if resume else "save", str(state) if resume else "",
                      sha(state) if resume else "", "ppsspp:d357e6a32934800d3d80b49f910a603e1b069751:chunk5-savestart3", "2"]
            request.write_bytes(packet(b"TPSE1Q\n", fields))
            request.chmod(0o600)
            if mutate:
                mutate(request, private)
            checked([str(self.binary), name, str(root), str(request)], cwd=self.work)
            if name in {"reject-config", "wrong-state"}:
                self.assertFalse((private / "result").exists())
                return None
            if name == "export-failure":
                self.assertTrue((private / "result").is_dir())
                self.assertEqual(parse((private / "save-completed").read_bytes())[6:9], ["save", "1", "success"])
                return None
            result = parse((private / "result").read_bytes())
            self.assertEqual(len(result), 27)
            self.assertEqual(result[:6], fields[:6])
            self.assertEqual(result[7], "3" if name == "resume-save-then-write-failure" else "2" if name == "save-then-write-failure" else "1")
            self.assertEqual((private / "result").stat().st_mode & 0o777, 0o600)
            if name in {"save-then-write-failure", "resume-save-then-write-failure"}:
                saved = parse((private / "save-completed").read_bytes())
                self.assertEqual(saved[:6], fields[:6])
                self.assertEqual(saved[6:9], ["save", "2" if resume else "1", "success"])
                self.assertEqual(saved[16], sha(state))
                self.assertEqual((private / "save-completed").stat().st_mode & 0o777, 0o600)
                if resume:
                    loaded = parse((private / "load-completed").read_bytes())
                    self.assertEqual(loaded[6:9], ["load", "1", "success"])
                    self.assertEqual(loaded[16], fields[12])
                    self.assertNotEqual(loaded[16], sha(state))
            return result

    def test_actual_save_caller_defers_to_process_and_exports_completed_identity(self):
        result = self.scenario("save")
        self.assertEqual(result[6:9], ["save", "1", "success"])
        self.assertEqual(result[14], sha(self.binary))
        self.assertEqual(result[16], hashlib.sha256(b"fixture state bytes\n").hexdigest())

    def test_failed_finalization_and_rom_change_export_failure(self):
        for name in ("rename-failure", "rom-changed"):
            with self.subTest(name=name):
                result = self.scenario(name)
                self.assertEqual(result[8], "failure")
                self.assertEqual(result[10:], [""] * 17)

    def test_actual_state_load_process_exports_acknowledgement(self):
        result = self.scenario("resume")
        self.assertEqual(result[6:9], ["load", "1", "success"])
        self.assertEqual(result[21], "2")

    def test_failed_state_load_has_no_successful_acknowledgement(self):
        result = self.scenario("resume-failure")
        self.assertEqual(result[8], "failure")

    def test_later_failed_save_retains_exact_completed_same_session_identity(self):
        # The real SaveSlot/Process functions successfully finalize slot bytes,
        # then fail a second write in the same request. The fixture main checks
        # the first state bytes survive. The latest status reports failure while
        # a separate bounded completion retains the exact successful identity.
        result = self.scenario("save-then-write-failure")
        self.assertEqual(result[6:9], ["save", "2", "failure"])
        self.assertEqual(result[10:], [""] * 17)

    def test_resumed_session_retains_new_save_independently_of_old_load(self):
        result = self.scenario("resume-save-then-write-failure")
        self.assertEqual(result[6:9], ["save", "3", "failure"])
        self.assertEqual(result[10:], [""] * 17)

    def test_partial_export_reports_callback_failure_without_final_result(self):
        # The fixture main asserts callback FAILURE after the positive receipt
        # is written but publication of the final result is obstructed. The
        # consumer requires a valid final result before considering receipts.
        self.scenario("export-failure")

    def test_private_modes_and_symlinks_rejected(self):
        self.scenario("reject-config", mutate=lambda request, private: private.chmod(0o755))
        self.scenario("reject-config", mutate=lambda request, private: request.chmod(0o644))
        def symlink(request, private):
            moved = private / "real-request"
            request.rename(moved)
            request.symlink_to(moved)
        self.scenario("reject-config", mutate=symlink)

    def test_malformed_request_and_native_state_mismatch_rejected(self):
        self.scenario("reject-config", mutate=lambda request, private: request.write_bytes(b"TPSE1Q\n99999:bad,"))
        self.scenario("wrong-state")

    def test_actual_native_command_line_and_autoload_call_sites_are_guarded(self):
        native = (self.work / "UI/NativeApp.cpp").read_text()
        emu = (self.work / "UI/EmuScreen.cpp").read_text()
        self.assertIn("SaveState::ConfigureProjectStateSessionArgs(argc, argv, &projectStateError)", block(native, "void NativeInit("))
        self.assertIn("stateToLoad.Valid() && !SaveState::ProjectStateSessionHandlesLoad()", native)
        self.assertIn("SaveState::ProjectStateSessionHandlesLoad()", block(emu, "void EmuScreen::AutoLoadSaveState("))

    def test_real_principal_source_save_fresh_process_resume_and_acknowledgement(self):
        with tempfile.TemporaryDirectory(prefix="state-principal-roundtrip-") as directory:
            root = Path(directory)
            card = root / "card"
            (card / "Roms/PSP").mkdir(parents=True)
            (card / "Emu/PSP").mkdir(parents=True)
            (card / "states").mkdir()
            (card / "spruce/scripts").mkdir(parents=True)
            (card / "Roms/PSP/game.iso").write_bytes(b"fixture ROM bytes\n")
            (card / "ppsspp.ini").write_text("Native state fixture\n")
            (card / "spruce/scripts/principal.sh").write_text("# Independent host principal profile fixture\n")
            (card / "Emu/PSP/config.json").write_text(json.dumps({"label": "PSP", "extlist": "iso", "launch": "launch.sh", "default_emulator": "PPSSPP"}))
            shutil.copy2(self.binary, card / "engine")
            results = []
            for operation in ("save-then-write-failure", "write-failure", "resume", "resume-save-then-write-failure", "resume"):
                result = subprocess.run([sys.executable, str(HERE / "state_principal_roundtrip.py"), "principal", str(root), operation],
                    text=True, capture_output=True, timeout=30, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                results.append(json.loads(result.stdout))
            self.assertTrue(all(result["foreground_clear"] and result["children_reaped"] >= 1 for result in results))
            self.assertEqual({result["checkpoint"] for result in results[:3]}, {results[0]["checkpoint"]})
            self.assertNotEqual(results[3]["checkpoint"], results[0]["checkpoint"])
            self.assertEqual(results[3]["checkpoint"], results[4]["checkpoint"])
            self.assertNotEqual(results[0]["state_sha256"], results[3]["state_sha256"])
            self.assertEqual(results[3]["state_sha256"], results[4]["state_sha256"])


if __name__ == "__main__":
    unittest.main()
