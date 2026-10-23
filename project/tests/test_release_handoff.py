# SPDX-License-Identifier: MIT
import copy
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

from tools import release_handoff as handoff
from tools.fixture_card import create_fixture


class ReleaseHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="release-handoff-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.public, self.private = self.root / "reviewed.pub", self.root / "disposable.private"
        handoff.ov.keygen(self.private, self.public)
        self.fingerprint = handoff.ov.digest(self.public.read_bytes())
        self.review = self.root / "independent-review.sha256"
        self.release = "handoff-fixture-1"
        self.bundle = self.root / "bundle"
        self.fixture()

    def fixture(self):
        ov = handoff.ov
        card = self.root / "host-fixture"
        create_fixture(card)
        profile = ov.read_json(card / "fixture-profile.json")
        descriptor = {"schema": 1, "release_id": self.release, "delivery": "original-only-host-preview",
                      "base": {"source_commit": ov.SPRUCE_COMMIT, "pyui_git_tree": ov.PYUI_TREE},
                      "selected_original_payload": ["psp_shell", "bridge", "profiles", "ppsspp/theme", "assets"],
                      "selected_native_binaries": [], "selected_upstream_patches": [], "qualification": handoff.GATES.copy()}
        sources = {"LICENSE": b"MIT original fixture license\n", "assets/fonts/OFL.txt": b"SIL OPEN FONT LICENSE\n",
                   "psp_shell/__main__.py": b"print('original host fixture')\n",
                   "packaging/current-release.json": ov.canonical(descriptor) + b"\n",
                   "docs/Unicode \u6309\u952e.md": b"Original fixture notes\n"}
        inventory = [{"path": name, "sha256": ov.digest(raw), "size": len(raw)} for name, raw in sorted(sources.items())]
        snapshot = {"schema": 1, "frontend": {"commit": "a" * 40, "working_tree_modified": False},
                    "descriptor_sha256": ov.digest(sources["packaging/current-release.json"]),
                    "source_inventory": inventory, "source_inventory_sha256": ov.digest(ov.canonical(inventory))}
        self.selection = {"descriptor": descriptor, "descriptor_sha256": snapshot["descriptor_sha256"],
                          "frontend": snapshot["frontend"], "source_inventory_sha256": snapshot["source_inventory_sha256"]}
        payload = {"app/psp_shell/__main__.py": sources["psp_shell/__main__.py"],
                   "notices/ORIGINAL-PROJECT-LICENSE.txt": sources["LICENSE"],
                   "notices/NotoSans-OFL.txt": sources["assets/fonts/OFL.txt"],
                   "notices/DEPENDENCIES.txt": b"Original fixture; no upstream binaries or user data.\n",
                   "metadata/development-release.json": ov.canonical({"schema": 1, "release_selection": self.selection,
                       "device_activation_qualified": False}) + b"\n"}
        payload_dir = self.root / "original-payload"
        for name, data in payload.items():
            path = payload_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        ov.create_archive(payload_dir, self.artifacts / (self.release + ".tar"), self.private, self.public,
                          profile, self.release, "python-extension")
        report = {"schema": 1, "release_id": self.release, "status": "host-development-preview",
                  "device_activation_qualified": False, "device_gates": handoff.GATES.copy(),
                  "private_key_packaged": False, "production_authenticity_claim": False,
                  "signature_hash_inventory_verified": True, "byte_identical_overlay_rebuild_with_same_key": True,
                  "fixture_stage_activate_rollback": True, "release_selection": self.selection,
                  "development_key_id": self.fingerprint, "payload_files": len(payload),
                  "smoke": {"executed": True, "physical_device_verified": False, "real_game_launches": 0}}
        (self.artifacts / "build-report.json").write_bytes(ov.canonical(report) + b"\n")
        (self.artifacts / "release-source.json").write_bytes(ov.canonical(snapshot) + b"\n")
        (self.artifacts / "development-verification.pub").write_bytes(self.public.read_bytes())
        instructions = b"HOST DEVELOPMENT PREVIEW ONLY. Synthetic fixture instructions.\n"
        (self.artifacts / "START-HERE.txt").write_bytes(instructions)
        (self.artifacts / "host-preview.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture-image")
        self.zip_write(self.release + "-host-preview.zip", {
            **{"smartpro-host-preview/" + name: raw for name, raw in payload.items()},
            "smartpro-host-preview/RUN.txt": instructions})
        self.zip_write(self.release + "-original-source.zip", {
            **{"smartpro-original-source/" + name: raw for name, raw in sources.items()},
            "smartpro-original-source/metadata/release-source.json": ov.canonical(snapshot) + b"\n"})
        self.refresh_review()

    def zip_write(self, name, entries):
        with zipfile.ZipFile(self.artifacts / name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for key, data in entries.items():
                item = zipfile.ZipInfo(key)
                item.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(item, data)

    def refresh_review(self):
        raw = "".join(handoff.ov.file_digest(self.artifacts / name) + "  " + name + "\n"
                      for name in sorted(handoff.artifact_names(self.release))).encode()
        (self.artifacts / "SHA256SUMS").write_bytes(raw)
        self.review.write_bytes(raw)
        self.review_sha = handoff.ov.digest(raw)

    def kwargs(self):
        return {"public_key": self.public, "expected_fingerprint": self.fingerprint,
                "trust_reference": "reviewed-host-fixture"}

    def prepare(self, **overrides):
        kwargs = {**self.kwargs(), "stable_url": "https://example.org/review/fixture",
                  "reviewed_checksums": self.review, "expected_checksums_sha256": self.review_sha}
        kwargs.update(overrides)
        return handoff.prepare(self.artifacts, self.bundle, **kwargs)

    def verify(self, digest, **overrides):
        kwargs = {**self.kwargs(), "expected_index": digest}
        kwargs.update(overrides)
        return handoff.verify(self.bundle, **kwargs)

    def test_bundle_joins_signature_source_notices_preview_and_keeps_gates_closed(self):
        result = self.prepare()
        self.assertFalse(result["device_ready"])
        checked = self.verify(result["index_sha256"])
        self.assertFalse(checked["production_trust_established"])
        self.assertFalse(checked["published"])
        candidate = checked["candidate"]
        self.assertEqual(candidate["source_files"], 5)
        self.assertEqual(candidate["payload_files"], 5)
        self.assertEqual(candidate["device_gates"], handoff.GATES)
        self.assertEqual(candidate["selected_native_binaries"], [])
        index, files = handoff.load_bundle(self.bundle, result["index_sha256"])
        self.assertFalse(index["download_availability_verified"])
        self.assertNotIn(self.private.name, str(files))
        self.assertFalse(any(b"\x7fELF" == raw[:4] for raw in files.values()))
        self.assertIn(b"No installed emulator", files["README.md"])
        self.assertFalse(json.loads(files["support-export.json"])["automatic_upload"])
        self.assertTrue(all(x["status"] == "pending" for x in json.loads(files["custody-checklist.json"])["steps"]))

    def test_no_in_bundle_key_or_wrong_fingerprint_is_independent_trust(self):
        with self.assertRaisesRegex(handoff.ov.OverlayError, "independent"):
            self.prepare(public_key=self.artifacts / "development-verification.pub")
        with self.assertRaisesRegex(handoff.ov.OverlayError, "fingerprint"):
            self.prepare(expected_fingerprint="b" * 64)
        with self.assertRaisesRegex(handoff.ov.OverlayError, "independent"):
            self.prepare(reviewed_checksums=self.artifacts / "SHA256SUMS")
        self.assertFalse(self.bundle.exists())

    def test_independent_artifact_checksums_cover_unsigned_outer_files(self):
        (self.artifacts / "host-preview.png").write_bytes(b"\x89PNG\r\n\x1a\nprivate image replacement")
        # Update only the untrusted in-directory checksum file, not the independent review.
        original_review = self.review.read_bytes()
        self.refresh_review()
        self.review.write_bytes(original_review)
        with self.assertRaisesRegex(handoff.ov.OverlayError, "independent review"):
            self.prepare(expected_checksums_sha256=handoff.ov.digest(original_review))
        self.assertFalse(self.bundle.exists())

    def test_device_or_native_descriptor_cannot_be_promoted_by_outer_report(self):
        path = self.artifacts / "build-report.json"
        original = path.read_bytes()
        for field, value in (("device_ready", True), ("selected_native_binaries", ["unreviewed-engine"])):
            report = json.loads(original)
            if field == "device_ready":
                report["device_activation_qualified"] = value
            else:
                report["release_selection"]["descriptor"][field] = value
            path.write_bytes(handoff.ov.canonical(report))
            self.refresh_review()
            with self.subTest(field=field), self.assertRaises(handoff.ov.OverlayError):
                self.prepare()
            self.assertFalse(self.bundle.exists())

    def test_changed_report_selection_cannot_break_signed_source_binding(self):
        path = self.artifacts / "build-report.json"
        report = json.loads(path.read_bytes())
        report["release_selection"]["frontend"]["commit"] = "b" * 40
        path.write_bytes(handoff.ov.canonical(report))
        self.refresh_review()
        with self.assertRaisesRegex(handoff.ov.OverlayError, "source identity"):
            self.prepare()

    def test_source_zip_changed_bytes_are_not_authorized_by_updated_outer_checksums(self):
        name = self.release + "-original-source.zip"
        with zipfile.ZipFile(self.artifacts / name) as archive:
            entries = {row.filename: archive.read(row) for row in archive.infolist()}
        entries["smartpro-original-source/psp_shell/__main__.py"] = b"changed original code"
        self.zip_write(name, entries)
        self.refresh_review()
        with self.assertRaisesRegex(handoff.ov.OverlayError, "source archive differs"):
            self.prepare()
        self.assertFalse(self.bundle.exists())

    def test_preview_zip_must_match_the_exact_signed_payload(self):
        name = self.release + "-host-preview.zip"
        with zipfile.ZipFile(self.artifacts / name) as archive:
            entries = {row.filename: archive.read(row) for row in archive.infolist()}
        entries["smartpro-host-preview/app/psp_shell/__main__.py"] = b"changed preview code"
        self.zip_write(name, entries)
        self.refresh_review()
        with self.assertRaisesRegex(handoff.ov.OverlayError, "preview ZIP"):
            self.prepare()

    def test_zip_traversal_duplicates_links_and_private_material_are_refused(self):
        for name, data in (("../escape", b"x"), ("smartpro-host-preview/secrets/key", b"x"),
                           ("smartpro-host-preview/assets/hidden", b"\x7fELFbinary"),
                           ("smartpro-host-preview/assets/key", b"-----BEGIN RSA PRIVATE KEY-----\n" + b"A" * 64 + b"\n-----END RSA PRIVATE KEY-----")):
            raw = io.BytesIO()
            with zipfile.ZipFile(raw, "w") as archive:
                archive.writestr(name, data)
            with self.subTest(name=name), self.assertRaises(handoff.ov.OverlayError):
                handoff.zip_contents(raw.getvalue(), "smartpro-host-preview")
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            item = zipfile.ZipInfo("smartpro-host-preview/link")
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(item, b"../../outside")
        with self.assertRaisesRegex(handoff.ov.OverlayError, "links"):
            handoff.zip_contents(raw.getvalue(), "smartpro-host-preview")

    def test_zip_uncompressed_size_and_entry_count_are_bounded(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("smartpro-host-preview/large", b"0" * 1000)
        with mock.patch.object(handoff.ov, "MAX_FILE", 100), self.assertRaises(handoff.ov.OverlayError):
            handoff.zip_contents(raw.getvalue(), "smartpro-host-preview")
        with mock.patch.object(handoff, "MAX_FILES", 0), self.assertRaises(handoff.ov.OverlayError):
            handoff.zip_contents(raw.getvalue(), "smartpro-host-preview")

    def test_zip_metadata_bomb_is_rejected_before_central_directory_materialization(self):
        raw = b"PK\x05\x06" + struct.pack("<4H2LH", 0, 0, 65535, 65535, 0, 0, 0)
        with mock.patch.object(handoff.zipfile, "ZipFile", side_effect=AssertionError("must not parse central directory")) as opened:
            with self.assertRaisesRegex(handoff.ov.OverlayError, "central-directory"):
                handoff.zip_contents(raw, "smartpro-host-preview")
            opened.assert_not_called()
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            for number in range(3):
                archive.writestr("smartpro-host-preview/file%d" % number, b"small original file")
        changed = bytearray(raw.getvalue())
        struct.pack_into("<HH", changed, len(changed) - 14, 1, 1)
        with mock.patch.object(handoff.zipfile, "ZipFile", side_effect=AssertionError("must not parse directory")) as opened:
            with self.assertRaisesRegex(handoff.ov.OverlayError, "record count"):
                handoff.zip_contents(changed, "smartpro-host-preview")
            opened.assert_not_called()

    def test_symlink_fifo_and_output_inside_inputs_are_refused(self):
        image = self.artifacts / "host-preview.png"
        original = image.read_bytes()
        image.unlink()
        image.symlink_to(self.review)
        with self.assertRaises(OSError):
            self.prepare()
        image.unlink()
        os.mkfifo(image)
        with self.assertRaises(handoff.ov.OverlayError):
            self.prepare()
        image.unlink()
        image.write_bytes(original)
        self.refresh_review()
        with self.assertRaisesRegex(handoff.ov.OverlayError, "outside"):
            handoff.prepare(self.artifacts, self.artifacts / "bundle", **self.kwargs(),
                            stable_url="https://example.org/review", reviewed_checksums=self.review,
                            expected_checksums_sha256=self.review_sha)

    def test_existing_output_and_added_bundle_files_never_get_overwritten_or_accepted(self):
        self.bundle.mkdir()
        sentinel = self.bundle / "keep"
        sentinel.write_bytes(b"unrelated work")
        with self.assertRaises(handoff.ov.OverlayError):
            self.prepare()
        self.assertEqual(sentinel.read_bytes(), b"unrelated work")
        sentinel.unlink()
        self.bundle.rmdir()
        prepared = self.prepare()
        (self.bundle / "extra-original-source.py").write_bytes(b"unreviewed source")
        with self.assertRaisesRegex(handoff.ov.OverlayError, "unindexed"):
            self.verify(prepared["index_sha256"])

    def test_index_digest_and_device_scope_are_independently_checked(self):
        prepared = self.prepare()
        with self.assertRaisesRegex(handoff.ov.OverlayError, "independent expected"):
            self.verify("b" * 64)
        path = self.bundle / "index.json"
        value = json.loads(path.read_bytes())
        value["device_ready"] = True
        path.write_bytes(handoff.ov.canonical(value))
        with self.assertRaisesRegex(handoff.ov.OverlayError, "device"):
            self.verify(handoff.ov.digest(path.read_bytes()))

    def test_https_download_metadata_cannot_contain_credentials_tokens_or_private_addresses(self):
        for url in ("http://example.org/file", "https://user:pass@example.org/file", "https://example.org/file?token=PRIVATE",
                    "https://127.0.0.1/file", "https://192.168.1.2/file", "https://example.local/file",
                    "https://example.org/%2e%2e/private", "https://example.org/file#secret"):
            with self.subTest(url=url), self.assertRaises(handoff.ov.OverlayError):
                handoff.public_url(url)

    def test_custody_and_recovery_references_remain_operator_evidence(self):
        prepared = self.prepare()
        previous = None
        for step in ("readback", "key-custody", "recovery"):
            output = self.root / (step + ".json")
            result = handoff.custody_receipt(self.bundle, output, step=step, evidence_reference="private-owner-record",
                                            expected_index=prepared["index_sha256"], previous=previous, **self.kwargs())
            receipt = json.loads(output.read_bytes())
            self.assertEqual(result["receipt_sha256"], handoff.ov.file_digest(output))
            self.assertFalse(receipt["actual_private_key_custody_verified"])
            self.assertFalse(receipt["actual_key_recovery_verified"])
            self.assertFalse(receipt["production_trust_established"])
            self.assertEqual(receipt["previous_receipt_sha256"], handoff.ov.file_digest(previous) if previous else None)
            with self.assertRaises(FileExistsError):
                handoff.custody_receipt(self.bundle, output, step=step, evidence_reference="private-owner-record",
                                        expected_index=prepared["index_sha256"], **self.kwargs())
            previous = output

    def test_actual_external_registry_rotation_and_revocation_produce_specific_receipts(self):
        prepared = self.prepare()
        current_pub, current_private = self.root / "current.pub", self.root / "current.private"
        handoff.ov.keygen(current_private, current_pub)
        fingerprint = handoff.ov.digest(current_pub.read_bytes())
        registry = self.root / "registry.json"
        active = {"id": fingerprint, "public_key": current_pub.name, "introduced_epoch": 1, "status": "active"}
        old = {"id": self.fingerprint, "public_key": self.public.name, "introduced_epoch": 0, "status": "retired"}
        registry.write_bytes(handoff.ov.canonical({"schema": 1, "keys": [old, active]}))
        kwargs = {"public_key": current_pub, "expected_fingerprint": fingerprint,
                  "trust_reference": "reviewed-rotation", "registry": registry,
                  "expected_index": prepared["index_sha256"], "evidence_reference": "registry-owner-record"}
        rotation = self.root / "rotation.json"
        result = handoff.custody_receipt(self.bundle, rotation, step="rotation", **kwargs)
        self.assertEqual(result["status"], "retired-package-verified-through-new-primary")
        self.verify(prepared["index_sha256"], public_key=current_pub, expected_fingerprint=fingerprint, registry=registry)
        old["status"] = "revoked"
        old.pop("public_key")
        registry.write_bytes(handoff.ov.canonical({"schema": 1, "keys": [old, active]}))
        result = handoff.custody_receipt(self.bundle, self.root / "revocation.json", step="revocation", previous=rotation, **kwargs)
        self.assertEqual(result["status"], "external-registry-rejects-exact-package")
        with self.assertRaisesRegex(handoff.ov.OverlayError, "unknown or revoked"):
            self.verify(prepared["index_sha256"], public_key=current_pub, expected_fingerprint=fingerprint, registry=registry)

    def test_rotation_receipt_cannot_be_invented_without_a_retired_key_registry(self):
        prepared = self.prepare()
        with self.assertRaisesRegex(handoff.ov.OverlayError, "transition"):
            handoff.custody_receipt(self.bundle, self.root / "receipt.json", step="rotation", evidence_reference="fixture",
                                    expected_index=prepared["index_sha256"], **self.kwargs())
        self.assertFalse((self.root / "receipt.json").exists())

    def revocation_kwargs(self):
        current_pub, current_private = self.root / "current.pub", self.root / "current.private"
        handoff.ov.keygen(current_private, current_pub)
        fingerprint = handoff.ov.digest(current_pub.read_bytes())
        registry = self.root / "registry.json"
        registry.write_bytes(handoff.ov.canonical({"schema": 1, "keys": [
            {"id": self.fingerprint, "introduced_epoch": 0, "status": "revoked"},
            {"id": fingerprint, "public_key": current_pub.name, "introduced_epoch": 1, "status": "active"}]}))
        return {"public_key": current_pub, "expected_fingerprint": fingerprint,
                "trust_reference": "reviewed-revocation", "registry": registry,
                "evidence_reference": "registry-owner-record"}

    def update_bundle_index(self, name, data):
        (self.bundle / name).write_bytes(data)
        path = self.bundle / "index.json"
        index = json.loads(path.read_bytes())
        for row in index["files"]:
            if row["path"] == name:
                row.update(bytes=len(data), sha256=handoff.ov.digest(data))
        path.write_bytes(handoff.ov.canonical(index))
        return handoff.ov.digest(path.read_bytes())

    def test_revocation_receipt_refuses_an_unrelated_unknown_signer(self):
        self.prepare()
        kwargs = self.revocation_kwargs()
        private, public = self.root / "unknown.private", self.root / "unknown.pub"
        handoff.ov.keygen(private, public)
        substitute = self.root / "substitute.tar"
        profile = handoff.ov.read_json(self.root / "host-fixture/fixture-profile.json")
        handoff.ov.create_archive(self.root / "original-payload", substitute, private, public,
                                  profile, self.release, "python-extension")
        digest = self.update_bundle_index("artifacts/" + self.release + ".tar", substitute.read_bytes())
        output = self.root / "receipt.json"
        with self.assertRaises(handoff.ov.OverlayError):
            handoff.custody_receipt(self.bundle, output, step="revocation", expected_index=digest, **kwargs)
        self.assertFalse(output.exists())

    def test_revocation_receipt_refuses_corrupted_payload_before_counting_registry_rejection(self):
        self.prepare()
        kwargs = self.revocation_kwargs()
        name = "artifacts/" + self.release + ".tar"
        raw = bytearray((self.bundle / name).read_bytes())
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            offset = archive.getmember("payload/app/psp_shell/__main__.py").offset_data
        raw[offset] ^= 1
        digest = self.update_bundle_index(name, bytes(raw))
        output = self.root / "receipt.json"
        with self.assertRaisesRegex(handoff.ov.OverlayError, "hash rejected"):
            handoff.custody_receipt(self.bundle, output, step="revocation", expected_index=digest, **kwargs)
        self.assertFalse(output.exists())

    def test_revocation_receipt_requires_original_only_artifact_scope(self):
        self.prepare()
        kwargs = self.revocation_kwargs()
        name = "artifacts/build-report.json"
        report = json.loads((self.bundle / name).read_bytes())
        report["device_activation_qualified"] = True
        digest = self.update_bundle_index(name, handoff.ov.canonical(report))
        output = self.root / "receipt.json"
        with self.assertRaisesRegex(handoff.ov.OverlayError, "unqualified original host preview"):
            handoff.custody_receipt(self.bundle, output, step="revocation", expected_index=digest, **kwargs)
        self.assertFalse(output.exists())

    def test_final_fsync_failure_preserves_uncertain_bundle_without_claiming_success(self):
        real_fsync = os.fsync

        def fail_parent(fd):
            if self.bundle.exists() and stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("injected final durability failure")
            return real_fsync(fd)

        with mock.patch.object(handoff.os, "fsync", side_effect=fail_parent), self.assertRaises(OSError):
            self.prepare()
        self.assertTrue((self.bundle / "index.json").is_file())

    def test_atomic_publication_cannot_replace_concurrently_created_output(self):
        loader = ctypes.CDLL
        real_libc = loader(None, use_errno=True)
        rename = real_libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int

        def appear(*args):
            self.bundle.mkdir()
            (self.bundle / "keep").write_bytes(b"concurrent unrelated output")
            return rename(*args)

        def library(name, *args, **kwargs):
            return SimpleNamespace(renameat2=appear) if name is None else loader(name, *args, **kwargs)

        with mock.patch.object(handoff.ctypes, "CDLL", side_effect=library), \
                self.assertRaises(OSError):
            self.prepare()
        self.assertEqual((self.bundle / "keep").read_bytes(), b"concurrent unrelated output")
        self.assertEqual(len(list(self.root.glob(".handoff-*"))), 1)

    def test_failed_publication_never_recursively_cleans_a_replaceable_pathname(self):
        with mock.patch.object(handoff.ctypes, "CDLL", return_value=SimpleNamespace()), \
                mock.patch("shutil.rmtree", side_effect=AssertionError("recursive pathname cleanup is forbidden")) as remove:
            with self.assertRaisesRegex(handoff.ov.OverlayError, "no-replace"):
                handoff._publish_directory(self.bundle, {"README.md": b"reviewed fixture"}, [])
            remove.assert_not_called()
        staged = list(self.root.glob(".handoff-*"))
        self.assertEqual(len(staged), 1)
        self.assertEqual((staged[0] / "README.md").read_bytes(), b"reviewed fixture")
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        (unrelated / "owner-data").write_bytes(b"keep unrelated user bytes")
        staged[0].rename(self.root / "retained-owned-staging")
        unrelated.rename(staged[0])
        self.assertEqual((staged[0] / "owner-data").read_bytes(), b"keep unrelated user bytes")

    def test_swapped_source_directory_never_receives_a_successful_publication_receipt(self):
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        (unrelated / "owner-data").write_bytes(b"keep unrelated user bytes")
        loader = ctypes.CDLL
        real_libc = loader(None, use_errno=True)
        rename = real_libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int

        def swap(parent, name, *rest):
            os.rename(name, b"owned-staging-held", src_dir_fd=parent, dst_dir_fd=parent)
            os.rename(b"unrelated", name, src_dir_fd=parent, dst_dir_fd=parent)
            return rename(parent, name, *rest)

        with mock.patch.object(handoff.ctypes, "CDLL", return_value=SimpleNamespace(renameat2=swap)), \
                self.assertRaisesRegex(handoff.ov.OverlayError, "directory identity"):
            handoff._publish_directory(self.bundle, {"README.md": b"reviewed fixture"}, [])
        self.assertEqual((self.bundle / "owner-data").read_bytes(), b"keep unrelated user bytes")
        self.assertEqual((self.root / "owned-staging-held/README.md").read_bytes(), b"reviewed fixture")

    def test_prepare_receipt_requires_final_published_file_readback(self):
        publish = handoff._publish_directory

        def change(*args, **kwargs):
            publish(*args, **kwargs)
            (self.bundle / "README.md").write_bytes(b"changed after publication")

        with mock.patch.object(handoff, "_publish_directory", side_effect=change), \
                self.assertRaisesRegex(handoff.ov.OverlayError, "readback differs"):
            self.prepare()
        self.assertEqual((self.bundle / "README.md").read_bytes(), b"changed after publication")

    def test_root_replacement_between_mkdir_and_open_is_never_adopted_for_writes(self):
        unrelated = self.root / "unrelated"
        unrelated.mkdir(mode=0o700)
        (unrelated / "owner-data").write_bytes(b"keep unrelated user bytes")
        real_open = os.open

        def swap(name, flags, *args, **kwargs):
            if isinstance(name, str) and name.startswith(".handoff-") and flags & os.O_DIRECTORY:
                parent = kwargs["dir_fd"]
                os.rename(name, "owned-staging-held", src_dir_fd=parent, dst_dir_fd=parent)
                os.rename("unrelated", name, src_dir_fd=parent, dst_dir_fd=parent)
            return real_open(name, flags, *args, **kwargs)

        with mock.patch.object(handoff.os, "open", side_effect=swap), \
                self.assertRaisesRegex(handoff.ov.OverlayError, "creation and open"):
            handoff._publish_directory(self.bundle, {"fixture": b"original"}, [])
        self.assertFalse(self.bundle.exists())
        staged = list(self.root.glob(".handoff-*"))[0]
        self.assertEqual((staged / "owner-data").read_bytes(), b"keep unrelated user bytes")
        self.assertFalse((staged / "fixture").exists())

    def test_nested_replacement_between_mkdir_and_open_is_never_adopted_for_writes(self):
        unrelated = self.root / "unrelated"
        unrelated.mkdir(mode=0o700)
        (unrelated / "owner-data").write_bytes(b"keep unrelated user bytes")
        real_open = os.open

        def swap(name, flags, *args, **kwargs):
            if name == "artifacts" and flags & os.O_DIRECTORY:
                parent = kwargs["dir_fd"]
                os.rename(name, "owned-artifacts-held", src_dir_fd=parent, dst_dir_fd=parent)
                os.rename(unrelated, name, dst_dir_fd=parent)
            return real_open(name, flags, *args, **kwargs)

        with mock.patch.object(handoff.os, "open", side_effect=swap), \
                self.assertRaisesRegex(handoff.ov.OverlayError, "creation and open"):
            handoff._publish_directory(self.bundle, {"artifacts/fixture": b"original"}, [])
        self.assertFalse(self.bundle.exists())
        staged = list(self.root.glob(".handoff-*"))[0]
        self.assertEqual((staged / "artifacts/owner-data").read_bytes(), b"keep unrelated user bytes")
        self.assertFalse((staged / "artifacts/fixture").exists())


if __name__ == "__main__":
    unittest.main()
