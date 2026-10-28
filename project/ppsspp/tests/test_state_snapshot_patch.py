# SPDX-License-Identifier: MIT
"""Optional 0006 immutable snapshot contract at exact native function boundaries.

Uses the existing explicit serializer/platform fixture, actual patched native
save/session functions and real POSIX files/process interruption. No production
profile or full-emulator/device qualification is constructed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

from psp_shell.state_evidence import PrivateStateSession, StateEvidenceError
from test_native_menu_patch import block, checked
import test_state_session_patch as session_fixture
from test_state_session_patch import packet, parse, sha

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOCK = ROOT / "state-snapshot.lock.json"
POINTS = ("state-before-rename", "snapshot-partial-write", "snapshot-before-fsync", "snapshot-after-fsync",
          "result-partial-write", "result-before-rename", "completion-before-rename", "completion-after-rename")

WRAPPERS = r'''
static std::string snapshotFailure, mutationSource;
static std::string SnapshotFDName(int fd) {
    char descriptor[64], path[4096];
    snprintf(descriptor, sizeof(descriptor), "/proc/self/fd/%d", fd);
    ssize_t length = readlink(descriptor, path, sizeof(path) - 1);
    return length > 0 ? std::string(path, length) : "";
}
static bool SnapshotFileFD(int fd) {
    std::string name = SnapshotFDName(fd);
    return name.find("/.trimui-state-snapshots/") != std::string::npos;
}
static ssize_t SnapshotWrite(int fd, const void *data, size_t size) {
    if (SnapshotFileFD(fd)) {
        if (snapshotFailure == "snapshot-write") { errno = EIO; return -1; }
        if (snapshotFailure == "source-change") std::ofstream(mutationSource, std::ios::app) << "changed";
        if (snapshotFailure == "snapshot-corrupt") {
            std::string changed(static_cast<const char *>(data), size);
            changed[0] ^= 1;
            return ::write(fd, changed.data(), changed.size());
        }
        if (interruptionPoint == "snapshot-partial-write") {
            assert(::write(fd, data, std::min(size, size_t(9))) == 9);
            InterruptAt("snapshot-partial-write");
        }
    }
    return InterruptionWrite(fd, data, size);
}
static int SnapshotFsync(int fd) {
    if (SnapshotFileFD(fd)) {
        InterruptAt("snapshot-before-fsync");
        if (snapshotFailure == "snapshot-fsync") { errno = EIO; return -1; }
        int result = ::fsync(fd);
        if (result == 0) InterruptAt("snapshot-after-fsync");
        return result;
    }
    if (snapshotFailure == "snapshot-directory-fsync" && SnapshotFDName(fd).find("/.trimui-state-snapshots") != std::string::npos) {
        errno = EIO; return -1;
    }
    return ::fsync(fd);
}
static int SnapshotRenameAt(int from, const char *oldName, int to, const char *newName) {
    if (snapshotFailure == "result-rename" && std::string(newName) == "result") { errno = EIO; return -1; }
    if (snapshotFailure == "completion-rename" && std::string(newName) == "save-completed") { errno = EIO; return -1; }
    return InterruptionRenameAt(from, oldName, to, newName);
}
'''


def session_code(source):
    marker = source.index("\t// Explicit private-session extension")
    return block(source, "void Load(const Path &filename") + "\n" + source[marker:source.index("\n\tbool UndoSaveSlot(", marker)]


class SnapshotMetadataTests(unittest.TestCase):
    def test_optional_patch_locks_unchanged_session_preimage_and_keeps_activation_disabled(self):
        lock = json.loads(LOCK.read_text())
        session = json.loads((ROOT / "state-session.lock.json").read_text())
        self.assertEqual(lock["upstream_commit"], session["upstream_commit"])
        self.assertEqual(lock["preimage_files"], [session["patched_files"][0]])
        self.assertEqual(sha(ROOT / lock["patch"]["path"]), lock["patch"]["sha256"])
        self.assertFalse(any(lock["qualification"].values()))
        release = json.loads((ROOT.parent / "packaging/current-release.json").read_text())
        self.assertNotIn(lock["patch"]["path"], release["selected_upstream_patches"])
        self.assertFalse(lock["limits"]["automatic_deletion"])


class SnapshotSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        session_fixture.StateSessionSourceTests.setUpClass()
        cls.addClassCleanup(session_fixture.StateSessionSourceTests.doClassCleanups)
        cls.work = session_fixture.StateSessionSourceTests.work
        old_source = (cls.work / "Core/SaveState.cpp").read_text()
        lock = json.loads(LOCK.read_text())
        for item in lock["preimage_files"]:
            if sha(cls.work / item["path"]) != item["sha256"]:
                raise AssertionError("Snapshot preimage differs")
        patch = ROOT / lock["patch"]["path"]
        if sha(patch) != lock["patch"]["sha256"]:
            raise AssertionError("Snapshot patch differs")
        checked(["git", "apply", "--check", str(patch)], cwd=cls.work)
        checked(["git", "apply", str(patch)], cwd=cls.work)
        for item in lock["patched_files"]:
            if sha(cls.work / item["path"]) != item["sha256"]:
                raise AssertionError("Snapshot postimage differs")
        source = (cls.work / "Core/SaveState.cpp").read_text()
        code = (cls.work / "state-session.cpp").read_text()
        old = session_code(old_source)
        if code.count(old) != 1:
            raise AssertionError("Exact native session body not found")
        code = code.replace(old, session_code(source))
        code = code[:code.index("int main(")] + (HERE / "state_snapshot_main.cpp.in").read_text()
        code = code.replace("#include <signal.h>", "#include <signal.h>\n#include <dirent.h>\n#include <sys/file.h>\n#include <cerrno>")
        code = code.replace("namespace SaveState {", WRAPPERS + "\nnamespace SaveState {", 1)
        code = code.replace("#define write InterruptionWrite", "#define write SnapshotWrite\n#define fsync SnapshotFsync")
        code = code.replace("#define renameat InterruptionRenameAt", "#define renameat SnapshotRenameAt")
        code = code.replace("#undef write", "#undef write\n#undef fsync")
        cpp = cls.work / "state-snapshot.cpp"
        cpp.write_text(code)
        cls.binary = cls.work / "state-snapshot"
        checked(["g++", "-std=c++17", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Wno-unused-variable",
                 "-DSDL=1", "-DMOBILE_DEVICE=1", "-I", str(cls.work), str(cpp),
                 str(cls.work / "Common/Crypto/sha256.cpp"), "-o", str(cls.binary)], cwd=cls.work)

    def scenario(self, name, *, retain=None):
        with tempfile.TemporaryDirectory(prefix="ppsspp-immutable-snapshot-") as directory:
            root = Path(directory)
            states = root / "states"
            states.mkdir()
            game = root / "game ü.iso"
            game.write_bytes(b"fixture ROM bytes\n")
            private = root / "private"
            private.mkdir(mode=0o700)
            fields = ["a" * 32, "b" * 32, "c" * 32, "fixture-boot", "4", "game:fixture", str(game), sha(game),
                      sha(self.binary), str(states), "save", "", "",
                      "ppsspp:d357e6a32934800d3d80b49f910a603e1b069751:chunk5-savestart3", "2"]
            request = private / "request"
            request.write_bytes(packet(b"TPSE1Q\n", fields))
            request.chmod(0o600)
            if name.startswith("kill-"):
                point = name.removeprefix("kill-same-slot-").removeprefix("kill-separate-slot-")
                child = subprocess.Popen([str(self.binary), name, str(root), str(request)], cwd=self.work,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    ready, _, _ = select.select([child.stdout], [], [], 10)
                    self.assertTrue(ready, "Snapshot fixture did not reach interruption point")
                    self.assertEqual(child.stdout.readline().strip(), "interruption=" + point)
                    child.kill()
                    output, errors = child.communicate(timeout=5)
                    self.assertEqual(child.returncode, -signal.SIGKILL, output + errors)
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.communicate(timeout=5)
            else:
                checked([str(self.binary), name, str(root), str(request)], cwd=self.work)
            previous_bytes = (root / "previous-save-completed").read_bytes()
            previous = parse(previous_bytes)
            latest = parse((private / "result").read_bytes())
            completed = parse((private / "save-completed").read_bytes())
            old_snapshot = Path(previous[20])
            self.assertEqual(old_snapshot.parent, states / ".trimui-state-snapshots")
            self.assertEqual(old_snapshot.read_bytes(), b"fixture state bytes\n")
            self.assertEqual(sha(old_snapshot), previous[16])
            self.assertEqual(old_snapshot.stat().st_mode & 0o777, 0o600)
            self.assertEqual(previous[6:9], ["save", "1", "success"])
            self.assertLessEqual(int(completed[7]), int(latest[7]))
            if completed[7] == latest[7]:
                self.assertEqual(completed, latest)
            self.assertEqual(sha(Path(completed[20])), completed[16])
            self.assertEqual(Path(completed[20]).stat().st_size, int(completed[19]))
            # Exercise real transport/envelope/sequence checks, stopping at the
            # still-unqualified authority gate. Never manufacture a capability.
            transport = SimpleNamespace(_directory=os.open(private, os.O_RDONLY | os.O_DIRECTORY), _fields=tuple(fields))
            transport._read_result = lambda purpose="result": PrivateStateSession._read_result(transport, purpose)
            transport._validate_result_envelope = lambda result, minimum_sequence=1: PrivateStateSession._validate_result_envelope(transport, result, minimum_sequence)
            reached = []
            def unqualified(*args):
                reached.append(args[-1])
                raise StateEvidenceError("STATE_PROFILE_UNQUALIFIED", "No qualified authority is supplied by this fixture")
            transport._consume_result = unqualified
            try:
                values, error = PrivateStateSession.consume_completed(transport, None, None)
                self.assertEqual(values, ())
                self.assertEqual(reached, [tuple(completed)])
                self.assertEqual(error, "STATE_OPERATION_FAILED" if latest[8] == "failure" else "STATE_PROFILE_UNQUALIFIED")
                with self.assertRaises(StateEvidenceError):
                    PrivateStateSession._validate_result_envelope(transport, tuple(completed), int(completed[7]) + 1)
                for index in range(6):
                    changed = list(fields)
                    changed[index] += "-fresh"
                    with self.assertRaises(StateEvidenceError):
                        PrivateStateSession._validate_result_envelope(SimpleNamespace(_fields=tuple(changed)), tuple(completed))
            finally:
                os.close(transport._directory)
            if name == "success":
                self.assertEqual(latest[6:9], ["save", "2", "success"])
                self.assertNotEqual(latest[20], previous[20])
                self.assertEqual(Path(latest[20]).read_bytes(), b"new immutable snapshot fixture bytes\n")
            if name.startswith("fail-"):
                self.assertEqual((private / "save-completed").read_bytes(), previous_bytes)
                if name in {"fail-result-rename", "fail-completion-rename"}:
                    self.assertEqual(latest[7], "1" if name == "fail-result-rename" else "2")
                else:
                    self.assertEqual(latest[6:9], ["save", "2", "failure"])
            observation = {"scenario": name, "original_root": str(root), "prior_snapshot_valid": True, "prior_snapshot_sha256": previous[16],
                           "final_sequence": latest[7], "completion_sequence": completed[7],
                           "completion_bounded_by_final": True, "qualified_capability_created": False,
                           "artifacts": {str(path.relative_to(root)): {"sha256": sha(path), "size": path.stat().st_size}
                                         for path in sorted(root.rglob("*")) if path.is_file() and not path.is_symlink()}}
            if retain is not None:
                shutil.copytree(root, Path(retain) / name, symlinks=True)
            return observation

    def test_successful_same_slot_save_keeps_both_exact_immutable_generations(self):
        self.scenario("success")

    def test_process_death_at_each_state_snapshot_and_publication_window_preserves_prior_snapshot(self):
        for point in POINTS:
            for slot in ("same-slot", "separate-slot"):
                with self.subTest(point=point, slot=slot):
                    self.scenario("kill-" + slot + "-" + point)

    def test_write_hash_source_change_and_fsync_failures_preserve_prior_completion(self):
        for failure in ("snapshot-write", "snapshot-corrupt", "source-change", "snapshot-fsync", "snapshot-directory-fsync",
                        "result-rename", "completion-rename"):
            with self.subTest(failure=failure):
                self.scenario("fail-" + failure)

    def test_caps_include_interrupted_files_and_never_delete_prior_or_unknown_files(self):
        for failure in ("count-cap", "byte-cap"):
            with self.subTest(failure=failure):
                self.scenario("fail-" + failure)

    def test_foreign_links_and_public_snapshot_directory_fail_closed(self):
        for failure in ("entry-symlink", "entry-hardlink", "directory-mode"):
            with self.subTest(failure=failure):
                self.scenario("fail-" + failure)


if __name__ == "__main__":
    unittest.main()
