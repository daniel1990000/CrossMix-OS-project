#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise disposable host signing, rotation, revocation and package recovery.

No existing key, card or package is accepted as input. All signed material and
private keys live in one temporary host fixture and are removed before a public
fingerprint/hash-only report can be returned. This is not operational key custody.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import uuid

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "packaging"))
import overlay as ov

if __package__:
    from .fixture_card import create_fixture
else:
    from fixture_card import create_fixture

FIXTURE = b"print('original-only host trust rehearsal fixture')\n"
MAX_REPORT_BYTES = 64 * 1024


def rehearse():
    """Run real existing crypto/package APIs solely against generated fixtures."""
    checks = []

    def passed(name):
        checks.append({"check": name, "passed": True})

    def reject(name, operation, expected):
        try:
            operation()
        except ov.OverlayError as error:
            if expected not in str(error):
                raise RuntimeError("unexpected rejection in " + name) from error
            passed(name)
        else:
            raise RuntimeError("required rejection did not occur: " + name)

    def verify(path, trust):
        with ov.VerifiedArchive(path, trust):
            return None

    with tempfile.TemporaryDirectory(prefix="smartpro-trust-rehearsal-") as scratch_name:
        scratch = ov.ensure_no_links(Path(scratch_name))
        ov.require(not any((parent / ".git").exists() for parent in (scratch, *scratch.parents)),
                   "rehearsal scratch must stay outside repositories")
        card = scratch / "host-fixture"
        create_fixture(card)
        profile = ov.read_json(card / "fixture-profile.json")
        inventory = ov.read_json(card / "fixture-inventory.json")
        ov.require(all(profile.get(key) is False for key in
                       ("hardware_qualified", "runtime_verified", "source_use_verified")),
                   "rehearsal must retain unqualified fixture flags")
        keys = scratch / "disposable-keys"
        keys.mkdir(mode=0o700)
        keypairs = {}
        fingerprints = {}
        for name in ("old", "current"):
            private, public = keys / (name + ".private"), keys / (name + ".public")
            ov.keygen(private, public)
            keypairs[name] = (private, public)
            fingerprints[name] = ov.digest(ov.load_key(public, 32))
            ov.require(stat.S_IMODE(private.stat().st_mode) == 0o600,
                       "disposable private key permissions changed")
        ov.require(fingerprints["old"] != fingerprints["current"], "distinct signing keys required")
        registry = keys / "trust.json"

        def entry(name, status, epoch):
            value = {"id": fingerprints[name], "status": status, "introduced_epoch": epoch}
            if status != "revoked":
                value["public_key"] = keypairs[name][1].name
            return value

        registry_hashes = {}

        def registry_at(name, entries):
            registry.write_bytes(ov.canonical({"schema": 1, "keys": entries}) + b"\n")
            registry_hashes[name] = ov.file_digest(registry)

        registry_at("initial", [entry("old", "active", 0)])
        initial = ov.load_trust_store(keypairs["old"][1], registry, signing=True)
        payload = scratch / "original-payload"
        target = payload / ov.ENTRYPOINT
        target.parent.mkdir(parents=True)
        target.write_bytes(FIXTURE)
        packages = {}

        def package(name, signer, epoch):
            # create_archive has no registry argument. Its caller must explicitly
            # enforce signing status using the independently held registry first.
            ov.load_trust_store(keypairs[signer][1], registry, signing=True)
            path = scratch / (name + ".tar")
            manifest = ov.create_archive(payload, path, *keypairs[signer], profile,
                                         name, "python-extension", security_epoch=epoch)
            packages[name] = {"sha256": ov.file_digest(path), "bytes": path.stat().st_size,
                              "manifest_sha256": ov.digest(ov.canonical(manifest) + b"\n"),
                              "signer_fingerprint": fingerprints[signer]}
            return path

        old = package("trust-old-fixture", "old", 0)
        verify(old, initial)
        passed("initial_active_signature_and_payload_verified")
        repeated = scratch / "same-key-repeat.tar"
        ov.create_archive(payload, repeated, *keypairs["old"], profile,
                          "trust-old-fixture", "python-extension")
        ov.require(ov.file_digest(repeated) == ov.file_digest(old), "same-key archive differs")
        passed("same_key_archive_reproduced")

        registry_at("rotated", [entry("old", "retired", 0), entry("current", "active", 1)])
        rotated = ov.load_trust_store(keypairs["current"][1], registry, signing=True)
        verify(old, rotated)
        passed("retired_key_verifies_existing_archive")
        reject("retired_key_cannot_authorize_signing",
               lambda: ov.load_trust_store(keypairs["old"][1], registry, signing=True), "active")
        current = package("trust-current-fixture", "current", 1)
        verify(current, rotated)
        passed("rotated_active_key_signs_and_verifies")
        reject("new_key_is_unknown_to_original_registry", lambda: verify(current, initial), "unknown or revoked")

        public = keypairs["current"][1]
        original_public = public.read_bytes()
        try:
            public.write_bytes(bytes([original_public[0] ^ 1]) + original_public[1:])
            reject("mutated_public_key_rejected",
                   lambda: ov.load_trust_store(keypairs["old"][1], registry), "hash mismatch")
        finally:
            public.write_bytes(original_public)
        valid_registry = registry.read_bytes()
        try:
            duplicate = entry("current", "active", 1)
            registry.write_bytes(ov.canonical({"schema": 1, "keys": [duplicate, duplicate]}))
            reject("duplicate_registry_identity_rejected",
                   lambda: ov.load_trust_store(public, registry), "duplicate")
        finally:
            registry.write_bytes(valid_registry)

        # Preserve the signed manifest; change one actual payload byte in the
        # normalized archive. Verification must fail before staging can write.
        tampered = scratch / "tampered.tar"
        raw = bytearray(current.read_bytes())
        with tarfile.open(current, "r:") as archive:
            offset = archive.getmember("payload/" + ov.ENTRYPOINT).offset_data
        raw[offset] ^= 1
        tampered.write_bytes(raw)
        reject("signed_archive_payload_tamper_rejected", lambda: verify(tampered, rotated), "hash rejected")

        saves = card / "Saves"
        saves.mkdir()
        save = saves / "fixture.srm"
        save.write_bytes(b"original host save sentinel\n")
        ov.stage_archive(old, initial, card, profile, inventory, fixture=True)
        ov.activate_release(card, "trust-old-fixture", initial, profile, inventory, fixture=True)
        state = ov.managed_root(card) / "state"

        def health(name, trust):
            # Explicit synthetic fixture receipt; it does not observe a screen,
            # input, device health or a physical recovery operation.
            ov.confirm_health(card, trust, {
                "schema": 1, "release_id": name, "profile_id": profile["id"],
                "manifest_sha256": ov.file_digest(ov.managed_root(card) / "releases" / name / "manifest.json"),
                "checks": {check: True for check in
                           ("first_frame", "input", "settings", "classic_fallback", "clean_exit")},
                "evidence_reference": "synthetic host trust lifecycle fixture only"})

        health("trust-old-fixture", initial)
        ov.stage_archive(current, rotated, card, profile, inventory, fixture=True)
        ov.activate_release(card, "trust-current-fixture", rotated, profile, inventory, fixture=True)
        save.write_bytes(b"newer host save sentinel; never roll back\n")
        sentinel_hash = ov.file_digest(save)
        result = ov.rollback(card, rotated)
        ov.require(result["current_release"] == "trust-old-fixture" and
                   (state / "force-classic").is_file() and ov.file_digest(save) == sentinel_hash,
                   "pending activation rollback did not preserve host save")
        passed("pending_activation_rolls_back_to_retired_key_without_changing_save")
        ov.activate_release(card, "trust-current-fixture", rotated, profile, inventory, fixture=True)
        health("trust-current-fixture", rotated)

        registry_at("revoked", [entry("old", "revoked", 0), entry("current", "active", 1)])
        revoked = ov.load_trust_store(public, registry, signing=True)
        reject("revoked_archive_rejected", lambda: verify(old, revoked), "unknown or revoked")
        reject("revoked_key_cannot_be_primary",
               lambda: ov.load_trust_store(keypairs["old"][1], registry), "revoked")
        verify(current, revoked)
        passed("revoking_old_key_preserves_current_archive_trust")
        selector = copy.deepcopy(ov.current_record(state))
        reject("rollback_to_revoked_release_blocked", lambda: ov.rollback(card, revoked), "unknown or revoked")
        ov.require(ov.current_record(state) == selector and
                   (state / "force-classic").is_file() and ov.file_digest(save) == sentinel_hash,
                   "revoked rollback changed selected release or newer save")
        passed("blocked_rollback_retains_selector_classic_request_and_newer_save")

        # Recovery uses the pristine original fixture payload and current signer,
        # not a trust exception for the revoked archive or a lower security epoch.
        recovery = package("trust-recovery-fixture", "current", 2)
        ov.stage_archive(recovery, revoked, card, profile, inventory, fixture=True)
        ov.activate_release(card, "trust-recovery-fixture", revoked, profile, inventory, fixture=True)
        health("trust-recovery-fixture", revoked)
        ov.require(ov.current_record(state)["current_release"] == "trust-recovery-fixture" and
                   ov.file_digest(save) == sentinel_hash, "trusted fixture recovery failed")
        passed("new_current_key_recovery_package_preserves_newer_save")
        report = {"schema": 1, "kind": "host-disposable-trust-rehearsal", "status": "passed",
                  "operational_trust_established": False, "hardware_tested": False,
                  "source_use_verified": False, "distribution_cleared": False,
                  "public_key_fingerprints": fingerprints, "registries_sha256": registry_hashes,
                  "packages": packages, "original_fixture_sha256": ov.digest(FIXTURE),
                  "newer_fixture_save_sha256": sentinel_hash, "checks": checks,
                  "recovery": {"retired_release_rollback": "passed-in-host-fixture",
                               "revoked_release_rollback": "blocked-selector-preserved",
                               "current_key_recovery_package": "passed-in-host-fixture",
                               "classic_request_is_physical_recovery_proof": False},
                  "limitations": ["Disposable host keys; operational custody and recovery remain untested.",
                                  "Synthetic health receipts establish no physical frame, input or restore result.",
                                  "External registry selection is a caller responsibility; it is never read from a package.",
                                  "Revocation removes affected package rollback eligibility; it does not undo installed code.",
                                  "Reports contain no private keys or recoverable signed artifacts."]}
    ov.require(not scratch.exists(), "disposable rehearsal cleanup failed")
    report["disposable_keys_and_packages_removed"] = True
    return report


def write_report(path, report):
    """Publish a new fsynced report without replacing an existing destination."""
    path = Path(path).absolute()
    parent = ov.ensure_no_links(path.parent)
    ov.require(parent.is_dir() and path.name not in {"", ".", ".."}, "existing report parent required")
    raw = ov.canonical(report) + b"\n"
    ov.require(len(raw) <= MAX_REPORT_BYTES, "rehearsal report exceeds bound")
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".trust-rehearsal-" + uuid.uuid4().hex
    owned_identity = None
    published = False
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            info = os.fstat(stream.fileno())
            owned_identity = (info.st_dev, info.st_ino)
        os.link(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        published = True
        os.fsync(directory)
    except BaseException:
        if published:
            current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            if (current.st_dev, current.st_ino) == owned_identity:
                os.unlink(path.name, dir_fd=directory)
        raise
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)
    return ov.digest(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="new report file; parent must already exist")
    args = parser.parse_args(argv)
    try:
        report = rehearse()
        digest = write_report(args.output, report)
    except (OSError, ValueError, RuntimeError):
        print("trust rehearsal failed; no operational trust or device state changed", file=sys.stderr)
        return 2
    print(json.dumps({"status": "passed", "kind": report["kind"], "report_sha256": digest,
                      "disposable_keys_and_packages_removed": True, "operational_trust_established": False}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
