# SPDX-License-Identifier: MIT
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / "packaging"))
sys.path.insert(0, str(PROJECT / "tools"))
import overlay as ov
from fixture_card import create_fixture


class PackageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="spruce-package-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.card = self.root / "card"
        create_fixture(self.card)
        self.profile = ov.read_json(self.card / "fixture-profile.json")
        self.inventory = ov.read_json(self.card / "fixture-inventory.json")
        self.public, secret = ov.Sodium().keypair()
        self.public_path, self.secret_path = self.root / "public", self.root / "private"
        self.public_path.write_bytes(self.public)
        self.secret_path.write_bytes(secret)
        self.source = self.root / "payload"
        (self.source / "app/psp_shell").mkdir(parents=True)
        (self.source / ov.ENTRYPOINT).write_text("print('original host prototype')\n")
        (self.source / "assets").mkdir()
        (self.source / "assets/original.txt").write_text("original art description\n")

    def package(self, release="demo-1", **kwargs):
        path = self.root / (release + ".tar")
        manifest = ov.create_archive(self.source, path, self.secret_path, self.public_path,
                                     self.profile, release, "python-extension", **kwargs)
        return path, manifest

    def stage(self, release="demo-1", **kwargs):
        path, manifest = self.package(release, **kwargs)
        ov.stage_archive(path, self.public, self.card, self.profile, self.inventory, fixture=True)
        return manifest

    def activate(self, release="demo-1"):
        return ov.activate_release(self.card, release, self.public, self.profile, self.inventory, fixture=True)

    def health(self, release="demo-1"):
        root = ov.managed_root(self.card)
        record = {"schema": 1, "release_id": release, "profile_id": self.profile["id"],
                  "manifest_sha256": ov.file_digest(root / "releases" / release / "manifest.json"),
                  "checks": {x: True for x in ("first_frame", "input", "settings", "classic_fallback", "clean_exit")},
                  "evidence_reference": "automated host fixture only"}
        return ov.confirm_health(self.card, self.public, record)

    def rewrite(self, source, change):
        entries = []
        with tarfile.open(source, "r:") as archive:
            for item in archive:
                entries.append((copy.copy(item), archive.extractfile(item).read()))
        change(entries)
        result = self.root / "tampered.tar"
        with tarfile.open(result, "w", format=tarfile.USTAR_FORMAT) as archive:
            for item, data in entries:
                item.size = len(data)
                archive.addfile(item, io.BytesIO(data))
        return result

    def test_deterministic_and_signature_exact_bytes(self):
        first, _ = self.package()
        second = self.root / "second.tar"
        ov.create_archive(self.source, second, self.secret_path, self.public_path, self.profile,
                          "demo-1", "python-extension")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        bad = self.rewrite(first, lambda entries: entries.__setitem__(0, (entries[0][0], entries[0][1] + b" ")))
        with self.assertRaisesRegex(ov.OverlayError, "signature"):
            ov.stage_archive(bad, self.public, self.card, self.profile, self.inventory, fixture=True)
        self.assertFalse(ov.managed_root(self.card).exists())

    def test_payload_hash_rejected_before_extraction(self):
        first, _ = self.package()
        bad = self.rewrite(first, lambda entries: entries.__setitem__(2, (entries[2][0], b"different contents")))
        with self.assertRaises(ov.OverlayError):
            ov.stage_archive(bad, self.public, self.card, self.profile, self.inventory, fixture=True)
        self.assertFalse(ov.managed_root(self.card).exists())

    def test_unknown_key_and_revocation(self):
        first, _ = self.package()
        other, _ = ov.Sodium().keypair()
        with self.assertRaisesRegex(ov.OverlayError, "signature"):
            ov.VerifiedArchive(first, other)
        registry = self.root / "trust.json"
        registry.write_text(json.dumps({"schema": 1, "keys": [{"id": ov.digest(self.public), "status": "revoked",
                                                               "introduced_epoch": 1}]}))
        with self.assertRaisesRegex(ov.OverlayError, "revoked"):
            ov.load_trust_store(self.public_path, registry)

    def test_rotation_can_verify_retired_but_not_sign(self):
        registry = self.root / "trust.json"
        registry.write_text(json.dumps({"schema": 1, "keys": [{"id": ov.digest(self.public), "status": "retired",
                "public_key": "public", "introduced_epoch": 1}]}))
        first, _ = self.package()
        with ov.VerifiedArchive(first, ov.load_trust_store(self.public_path, registry)):
            pass
        with self.assertRaisesRegex(ov.OverlayError, "active"):
            ov.load_trust_store(self.public_path, registry, signing=True)

    def test_paths_links_duplicates_and_special_files(self):
        first, _ = self.package()
        for path in ("../outside", "/absolute", "payload/../../outside", "payload/a\\b", "payload/C:/bad"):
            with self.subTest(path=path):
                def alter(entries):
                    entries[2][0].name = path
                bad = self.rewrite(first, alter)
                with self.assertRaises(ov.OverlayError):
                    ov.VerifiedArchive(bad, self.public)
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE):
            with self.subTest(kind=kind):
                def alter(entries):
                    entries[2][0].type = kind
                    entries[2][0].linkname = "../../outside"
                with self.assertRaises(ov.OverlayError):
                    ov.VerifiedArchive(self.rewrite(first, alter), self.public)
        bad = self.rewrite(first, lambda entries: entries.append(entries[2]))
        with self.assertRaises(ov.OverlayError):
            ov.VerifiedArchive(bad, self.public)

    def test_pax_compression_limits_extra_files_rejected(self):
        first, _ = self.package()
        with mock.patch.object(ov, "MAX_ARCHIVE", 1024):
            with self.assertRaisesRegex(ov.OverlayError, "size limit"):
                ov.VerifiedArchive(first, self.public)
        pax = self.root / "pax.tar"
        with tarfile.open(pax, "w", format=tarfile.PAX_FORMAT) as archive:
            item = tarfile.TarInfo("x")
            item.pax_headers = {"comment": "forbidden extension"}
            archive.addfile(item, io.BytesIO(b""))
        with self.assertRaisesRegex(ov.OverlayError, "extended"):
            ov.VerifiedArchive(pax, self.public)
        def extra(entries):
            item = tarfile.TarInfo("payload/assets/unlisted")
            item.mode = 0o644
            entries.append((item, b"unlisted"))
        with self.assertRaisesRegex(ov.OverlayError, "inventory"):
            ov.VerifiedArchive(self.rewrite(first, extra), self.public)

    def test_case_collision_and_source_symlinks(self):
        (self.source / "assets/ORIGINAL.txt").write_text("collision")
        with self.assertRaisesRegex(ov.OverlayError, "collid"):
            self.package()
        (self.source / "assets/ORIGINAL.txt").unlink()
        (self.source / "assets/link").symlink_to(self.public_path)
        with self.assertRaisesRegex(ov.OverlayError, "links"):
            self.package()

    def test_no_binary_rom_or_private_key_payload(self):
        for name, data in (("Roms/g.sav", b"save"), ("app/firmware.awimg", b"firmware"),
                           ("assets/unlabelled", b"\x7fELFxxx"), ("metadata/private.key", b"secret")):
            with self.subTest(name=name):
                path = self.source / name
                path.parent.mkdir(exist_ok=True, parents=True)
                path.write_bytes(data)
                with self.assertRaises(ov.OverlayError):
                    self.package()
                path.unlink()

    def test_model_baseline_firmware_and_free_space(self):
        first, _ = self.package()
        for key, value in (("model", "smart-pro-s"), ("firmware", "1.0.4"), ("base_commit", "0" * 40)):
            bad = copy.deepcopy(self.inventory)
            bad["device"][key] = value
            with self.assertRaises(ov.OverlayError):
                ov.stage_archive(first, self.public, self.card, self.profile, bad, fixture=True)
        with mock.patch.object(ov.shutil, "disk_usage", return_value=mock.Mock(free=0)):
            with self.assertRaisesRegex(ov.OverlayError, "free space"):
                ov.stage_archive(first, self.public, self.card, self.profile, self.inventory, fixture=True)
        (self.card / "base/runtime.txt").write_text("stale base")
        with self.assertRaisesRegex(ov.OverlayError, "contract changed"):
            ov.stage_archive(first, self.public, self.card, self.profile, self.inventory, fixture=True)

    def test_fixture_flag_is_not_device_bypass(self):
        first, _ = self.package()
        with self.assertRaisesRegex(ov.OverlayError, "explicit --fixture"):
            ov.stage_archive(first, self.public, self.card, self.profile, self.inventory)
        device_profile = copy.deepcopy(self.profile)
        device_profile["execution_environment"] = "device"
        manifest = {"profile": device_profile}
        inv = copy.deepcopy(self.inventory)
        inv.update(kind="read-only-device-inventory", source_profile_verified=True)
        with self.assertRaisesRegex(ov.OverlayError, "cannot bypass"):
            ov.check_compatibility(manifest, device_profile, inv, self.card, fixture=True, activating=True)
        with self.assertRaisesRegex(ov.OverlayError, "unverified"):
            ov.check_compatibility(manifest, device_profile, inv, self.card, activating=True)

    def test_full_fixture_stage_activate_health_and_rollback_preserves_saves(self):
        (self.card / "Roms").mkdir()
        (self.card / "Saves").mkdir()
        (self.card / "Roms/game.rom").write_bytes(b"ROM sentinel")
        save = self.card / "Saves/game.srm"
        save.write_bytes(b"save sentinel")
        self.stage()
        self.activate()
        state = ov.managed_root(self.card) / "state"
        self.assertTrue((state / "activation.pending.json").exists())
        self.health()
        self.assertFalse((state / "activation.pending.json").exists())
        self.stage("demo-2")
        self.activate("demo-2")
        save.write_bytes(b"newer save from gameplay")
        result = ov.rollback(self.card, self.public)
        self.assertEqual(result["current_release"], "demo-1")
        self.assertTrue((state / "force-classic").exists())
        self.assertEqual(save.read_bytes(), b"newer save from gameplay")
        self.assertEqual((self.card / "Roms/game.rom").read_bytes(), b"ROM sentinel")

    def test_release_immutable_and_tamper_detected(self):
        self.stage()
        path, _ = self.package("other")
        with ov.VerifiedArchive(path, self.public):
            pass
        archive = self.root / "demo-1.tar"
        with self.assertRaisesRegex(ov.OverlayError, "immutable"):
            ov.stage_archive(archive, self.public, self.card, self.profile, self.inventory, fixture=True)
        release = ov.managed_root(self.card) / "releases/demo-1"
        (release / "assets/original.txt").write_text("tampered")
        with self.assertRaisesRegex(ov.OverlayError, "hash"):
            self.activate()

    def test_staging_fault_leaves_no_release_or_selector(self):
        first, _ = self.package()
        with mock.patch.object(ov.os, "rename", side_effect=OSError("power fault fixture")):
            with self.assertRaises(OSError):
                ov.stage_archive(first, self.public, self.card, self.profile, self.inventory, fixture=True)
        root = ov.managed_root(self.card)
        self.assertEqual(list((root / "releases").iterdir()), [])
        self.assertFalse((root / "state/current.json").exists())

    def test_activation_fault_and_corrupt_selector_recover(self):
        self.stage()
        real_write = ov.write_record
        def write(path, value):
            if path.name == "current.json":
                raise OSError("interrupted activation fixture")
            return real_write(path, value)
        with mock.patch.object(ov, "write_record", side_effect=write):
            with self.assertRaises(OSError):
                self.activate()
        state = ov.managed_root(self.card) / "state"
        (state / "current.json").write_text("corrupt")
        self.assertIsNone(ov.rollback(self.card, self.public)["current_release"])
        self.assertTrue((state / "force-classic").exists())

    def test_corrupted_committed_selector_restores_last_good_release(self):
        self.stage()
        self.activate()
        self.health()
        state = ov.managed_root(self.card) / "state"
        (state / "current.json").write_bytes(b"broken")
        result = ov.rollback(self.card, self.public)
        self.assertEqual(result["current_release"], "demo-1")

    def test_downgrade_and_incomplete_health(self):
        self.stage(security_epoch=2)
        self.activate()
        with self.assertRaises(ov.OverlayError):
            ov.confirm_health(self.card, self.public, {})
        self.health()
        self.stage("demo-2", security_epoch=1)
        with self.assertRaisesRegex(ov.OverlayError, "downgrade"):
            self.activate("demo-2")

    def test_managed_root_symlink_rejected(self):
        (self.card / "App").symlink_to(self.root)
        first, _ = self.package()
        with self.assertRaisesRegex(ov.OverlayError, "symlink"):
            ov.stage_archive(first, self.public, self.card, self.profile, self.inventory, fixture=True)

    def test_cli_verify_and_wrong_key_failure(self):
        first, _ = self.package()
        command = [sys.executable, str(PROJECT / "packaging/overlay.py"), "verify", str(first), "--public-key", str(self.public_path)]
        ok = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["release_id"], "demo-1")
        self.public_path.write_bytes(b"x" * 31)
        bad = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("raw-byte", bad.stderr)

    def test_payload_builder_only_includes_original_allowlist(self):
        from build_payload import build_payload
        project = self.root / "source-project"
        (project / "psp_shell").mkdir(parents=True)
        (project / "psp_shell/__main__.py").write_text("print('demo')\n")
        (project / "tools").mkdir()
        for tool in ("__init__.py", "recovery_payload.py", "recovery_preflight.py", "backup_catalog.py"):
            (project / "tools" / tool).write_bytes((PROJECT / "tools" / tool).read_bytes())
        (project / "tools/unselected.py").write_text("raise RuntimeError('must not ship')\n")
        (project / "psp_shell/__pycache__").mkdir()
        (project / "psp_shell/__pycache__/private.pyc").write_bytes(b"ignored")
        (project / "assets/fonts").mkdir(parents=True)
        (project / "assets/fonts/OFL.txt").write_text("font notice")
        (project / "LICENSE").write_text("original project license")
        (project / "state").mkdir()
        (project / "state/private.json").write_text('{"password":"not packaged"}')
        (project / "psp_shell/state").mkdir()
        (project / "psp_shell/state/private.py").write_text("private = 'must not ship'\n")
        output = self.root / "prepared-payload"
        build_payload(project, output)
        names = [x.relative_to(output).as_posix() for x in output.rglob("*") if x.is_file()]
        self.assertIn(ov.ENTRYPOINT, names)
        self.assertIn("app/tools/recovery_payload.py", names)
        self.assertIn("app/tools/__init__.py", names)
        self.assertNotIn("app/tools/unselected.py", names)
        self.assertFalse(any("private" in x for x in names))
        self.assertTrue((output / "notices/ORIGINAL-PROJECT-LICENSE.txt").exists())

    def test_development_deliverable_fixed_signer_is_reproducible_and_contains_no_private_key(self):
        import dev_release
        import zipfile
        project = self.root / "mini-project"
        (project / "psp_shell").mkdir(parents=True)
        (project / "psp_shell/__main__.py").write_text("print('host fixture')\n")
        (project / "tools").mkdir()
        for tool in ("__init__.py", "recovery_payload.py", "recovery_preflight.py", "backup_catalog.py"):
            (project / "tools" / tool).write_bytes((PROJECT / "tools" / tool).read_bytes())
        (project / "assets/fonts").mkdir(parents=True)
        (project / "assets/fonts/OFL.txt").write_text("font notice")
        (project / "LICENSE").write_text("original code license")
        (project / "docs").mkdir()
        (project / "docs/author-notification-draft.txt").write_text("private unsent draft")
        for name in ("release-a", "release-b"):
            dev_release.build(project, self.root / name, "dev-test", ov.PLAN_SOURCE_DATE_EPOCH,
                              include_source=True, private_key=self.secret_path, public_key=self.public_path)
        first, second = self.root / "release-a", self.root / "release-b"
        for name in ("dev-test.tar", "dev-test-host-preview.zip", "dev-test-original-source.zip"):
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
        with zipfile.ZipFile(first / "dev-test-original-source.zip") as archive:
            self.assertFalse(any("author-notification" in x for x in archive.namelist()))
        self.assertTrue(self.secret_path.exists())  # caller-owned signer is never deleted
        self.assertFalse(any("private" in x.name for x in first.iterdir()))
        report = json.loads((first / "build-report.json").read_text())
        self.assertFalse(report["device_activation_qualified"])
        self.assertFalse(report["smoke"]["executed"])
        with ov.VerifiedArchive(first / "dev-test.tar", (first / "development-verification.pub").read_bytes()):
            pass


if __name__ == "__main__":
    unittest.main()
