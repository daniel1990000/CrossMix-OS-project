# SPDX-License-Identifier: MIT
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools import operational_trust as ot


class OperationalTrustTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.private, self.public = self.root / "recovered.key", self.root / "independent.pub"
        ot.ov.keygen(self.private, self.public)
        self.expected = ot.ov.digest(self.public.read_bytes())
        self.request = ot.challenge(self.expected, "a" * 64, "private-retention-retrieval-123")
        self.challenge = self.root / "challenge.json"
        self.challenge_sha = ot.write_report(self.challenge, self.request)

    def proof(self):
        return ot.prove(self.private, self.public, self.challenge, self.challenge_sha)

    def verify(self, report, **overrides):
        args = {"public_key": self.public, "expected_challenge_sha256": self.challenge_sha,
                "expected_fingerprint": self.expected}
        args.update(overrides)
        return ot.verify(report, **args)

    def test_real_recovered_key_proves_possession_without_claiming_custody(self):
        report = self.proof()
        result = self.verify(report)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["recovered_key_matches_expected"])
        for gate in ot.GATES:
            self.assertIs(result[gate], False)
        self.assertNotIn(str(self.private), json.dumps(report))
        self.assertNotIn(self.private.read_bytes().hex(), json.dumps(report))
        self.assertEqual(self.private.stat().st_size, 64)

    def test_proof_of_another_key_fails_even_with_the_expected_public_suffix(self):
        other_private, other_public = self.root / "other.key", self.root / "other.pub"
        ot.ov.keygen(other_private, other_public)
        raw = other_private.read_bytes()
        other_private.write_bytes(raw[:32] + self.public.read_bytes())
        with self.assertRaisesRegex(ot.ov.OverlayError, "signature rejected"):
            ot.prove(other_private, self.public, self.challenge, self.challenge_sha)

    def test_new_challenge_rejects_replay_of_an_older_possession_proof(self):
        report = self.proof()
        fresh = ot.challenge(self.expected, "a" * 64, "private-retention-retrieval-123")
        self.assertNotEqual(fresh["nonce_hex"], self.request["nonce_hex"])
        fresh_sha = ot.ov.digest(ot.ov.canonical(fresh) + b"\n")
        with self.assertRaisesRegex(ot.ov.OverlayError, "challenge checksum"):
            self.verify(report, expected_challenge_sha256=fresh_sha)

    def test_challenge_substitution_cannot_be_accepted_from_its_own_checksum(self):
        self.challenge.write_bytes(ot.ov.canonical(ot.challenge(self.expected, "b" * 64, "different")) + b"\n")
        with self.assertRaisesRegex(ot.ov.OverlayError, "challenge checksum"):
            self.proof()

    def test_modified_signed_challenge_fails_even_when_local_checksum_is_changed(self):
        report = self.proof()
        report["challenge"]["retained_envelope_sha256"] = "b" * 64
        changed = ot.ov.digest(ot.ov.canonical(report["challenge"]) + b"\n")
        report["challenge_file_sha256"] = changed
        with self.assertRaisesRegex(ot.ov.OverlayError, "signature rejected"):
            self.verify(report, expected_challenge_sha256=changed)

    def test_public_key_and_fingerprint_are_independent_inputs(self):
        report = self.proof()
        with self.assertRaisesRegex(ot.ov.OverlayError, "fingerprint differs"):
            self.verify(report, expected_fingerprint="b" * 64)
        self.public.write_bytes(os.urandom(32))
        with self.assertRaisesRegex(ot.ov.OverlayError, "fingerprint differs"):
            self.verify(report)

    def test_report_cannot_claim_production_or_retained_storage_authority(self):
        report = self.proof()
        for gate in ot.GATES:
            changed = copy.deepcopy(report)
            changed[gate] = True
            with self.subTest(gate=gate), self.assertRaisesRegex(ot.ov.OverlayError, "proof scope"):
                self.verify(changed)

    def test_private_file_modes_hardlinks_and_shared_parent_are_refused(self):
        for mode in (0o644, 0o660, 0o700):
            self.private.chmod(mode)
            with self.subTest(mode=mode), self.assertRaisesRegex(ot.ov.OverlayError, "owner-readable"):
                self.proof()
        self.private.chmod(0o600)
        alias = self.root / "hardlink"
        alias.hardlink_to(self.private)
        with self.assertRaisesRegex(ot.ov.OverlayError, "unshared"):
            self.proof()
        alias.unlink()
        self.root.chmod(0o755)
        with self.assertRaisesRegex(ot.ov.OverlayError, "owner-only"):
            self.proof()
        self.root.chmod(0o700)

    def test_symlink_key_or_parent_and_repository_private_key_are_refused(self):
        link = self.root / "alias.key"
        link.symlink_to(self.private)
        with self.assertRaises(OSError):
            ot.prove(link, self.public, self.challenge, self.challenge_sha)
        parent = self.root / "alias"
        parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            ot.prove(parent / self.private.name, self.public, self.challenge, self.challenge_sha)
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(ot.ov.OverlayError, "outside repositories"):
            self.proof()

    def test_private_file_changed_during_read_cannot_receive_proof(self):
        original = ot.fingerprint
        calls = 0

        def change_on_private(info):
            nonlocal calls
            if info.st_size == 64:
                calls += 1
                if calls == 1:
                    self.private.write_bytes(os.urandom(64))
            return original(info)

        with mock.patch.object(ot, "fingerprint", side_effect=change_on_private):
            with self.assertRaisesRegex(ot.ov.OverlayError, "file changed"):
                self.proof()

    def test_existing_report_is_preserved_and_errors_do_not_echo_private_path(self):
        output = self.root / "proof.json"
        output.write_bytes(b"preserve existing evidence")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = ot.main(["prove", "--private-key", str(self.private), "--public-key", str(self.public),
                              "--challenge-file", str(self.challenge), "--expected-challenge-sha256",
                              self.challenge_sha, "--output", str(output)])
        self.assertEqual(result, 2)
        self.assertEqual(output.read_bytes(), b"preserve existing evidence")
        self.assertNotIn(str(self.private), stderr.getvalue())

    def test_subprocess_commands_produce_independently_verifiable_public_proof(self):
        output = self.root / "proof.json"
        script = Path(ot.__file__)
        proved = subprocess.run([sys.executable, str(script), "prove", "--private-key", str(self.private),
                                 "--public-key", str(self.public), "--challenge-file", str(self.challenge),
                                 "--expected-challenge-sha256", self.challenge_sha, "--output", str(output)],
                                text=True, capture_output=True, check=True)
        self.assertFalse(json.loads(proved.stdout)["operational_trust_established"])
        checked = subprocess.run([sys.executable, str(script), "verify", "--proof", str(output),
                                  "--public-key", str(self.public), "--expected-challenge-sha256",
                                  self.challenge_sha, "--expected-fingerprint", self.expected],
                                 text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(checked.stdout)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
