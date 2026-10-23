#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prove possession of an independently expected recovered Ed25519 key.

This tool neither exports keys nor claims that a key came from retained storage.
The verifier must select a fresh challenge and expected fingerprint separately.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "packaging"))
import overlay as ov

if __package__:
    from .recovery_preflight import directory_fd, fingerprint
    from .trust_rehearsal import write_report
else:
    from recovery_preflight import directory_fd, fingerprint
    from trust_rehearsal import write_report

DOMAIN = b"SmartPro retained signing key recovery v1\x00"
REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
GATES = {"operational_trust_established": False, "retained_storage_provenance_verified": False,
         "independent_recovery_access_verified": False, "production_key_designated": False,
         "hardware_tested": False}
MAX_DOCUMENT = 16 * 1024


def read_file(value, maximum, *, private=False):
    """Read one stable bounded regular file through no-follow directory handles."""
    path = Path(value).absolute()
    ov.require(".." not in path.parts, "parent traversal refused")
    if private:
        ov.require(not any((p / ".git").exists() for p in path.parents),
                   "private recovery keys must stay outside repositories")
    parent = directory_fd(path.parent)
    try:
        if private:
            info = os.fstat(parent)
            ov.require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0,
                       "private key directory must be owned and owner-only")
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=parent)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            ov.require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
                       "bounded regular file required")
            if private:
                ov.require(before.st_uid == os.getuid() and before.st_nlink == 1 and
                           stat.S_IMODE(before.st_mode) in (0o400, 0o600),
                           "private key must be owned, unshared and owner-readable only")
            raw = stream.read(maximum + 1)
            named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            ov.require(len(raw) <= maximum and fingerprint(before) ==
                       fingerprint(os.fstat(stream.fileno())) == fingerprint(named),
                       "file changed during readback")
        current_parent = directory_fd(path.parent)
        try:
            observed, current = os.fstat(parent), os.fstat(current_parent)
            ov.require((observed.st_dev, observed.st_ino) == (current.st_dev, current.st_ino),
                       "input directory pathname changed")
        finally:
            os.close(current_parent)
        return raw
    finally:
        os.close(parent)


def checked_challenge(value):
    fields = {"schema", "kind", "nonce_hex", "expected_fingerprint", "retained_envelope_sha256",
              "custody_reference", "created_at_utc"}
    ov.require(isinstance(value, dict) and set(value) == fields and type(value["schema"]) is int and
               value["schema"] == 1 and value["kind"] == "signing-key-recovery-challenge",
               "invalid recovery challenge")
    for name in ("nonce_hex", "expected_fingerprint", "retained_envelope_sha256"):
        ov.require(isinstance(value[name], str) and ov.SHA256.fullmatch(value[name]),
                   "invalid challenge digest or nonce")
    ov.require(isinstance(value["custody_reference"], str) and
               REFERENCE.fullmatch(value["custody_reference"]), "opaque custody reference required")
    try:
        stamp = datetime.strptime(value["created_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError) as error:
        raise ov.OverlayError("invalid challenge timestamp") from error
    ov.require(stamp.year >= 2026, "invalid challenge timestamp")
    return value


def challenge(expected_fingerprint, retained_envelope_sha256, custody_reference):
    return checked_challenge({"schema": 1, "kind": "signing-key-recovery-challenge",
                              "nonce_hex": os.urandom(32).hex(),
                              "expected_fingerprint": expected_fingerprint,
                              "retained_envelope_sha256": retained_envelope_sha256,
                              "custody_reference": custody_reference,
                              "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})


def prove(private_key, public_key, challenge_file, expected_challenge_sha256):
    raw = read_file(challenge_file, MAX_DOCUMENT)
    ov.require(ov.digest(raw) == expected_challenge_sha256, "independent challenge checksum differs")
    request = checked_challenge(ov.decode(raw))
    public = read_file(public_key, 32)
    ov.require(len(public) == 32 and ov.digest(public) == request["expected_fingerprint"],
               "independent public-key fingerprint differs")
    secret = read_file(private_key, 64, private=True)
    ov.require(len(secret) == 64, "64-byte Ed25519 private key required")
    sodium = ov.Sodium()
    signature = sodium.sign(DOMAIN + ov.canonical(request), secret)
    # A corrupt secret/public pair must not receive a successful possession claim.
    sodium.verify(DOMAIN + ov.canonical(request), signature, public)
    report = {"schema": 1, "kind": "signing-key-recovery-possession-proof", "challenge": request,
              "challenge_file_sha256": expected_challenge_sha256, "public_key_hex": public.hex(),
              "signature_hex": signature.hex(), "recovered_key_matches_expected": True, **GATES}
    verify(report, public_key=public_key, expected_challenge_sha256=expected_challenge_sha256,
           expected_fingerprint=request["expected_fingerprint"])
    return report


def verify(report, *, public_key, expected_challenge_sha256, expected_fingerprint):
    fields = {"schema", "kind", "challenge", "challenge_file_sha256", "public_key_hex",
              "signature_hex", "recovered_key_matches_expected", *GATES}
    ov.require(isinstance(report, dict) and set(report) == fields and type(report["schema"]) is int and
               report["schema"] == 1 and report["kind"] == "signing-key-recovery-possession-proof" and
               report["recovered_key_matches_expected"] is True and
               all(report.get(name) is False for name in GATES), "invalid possession-proof scope")
    request = checked_challenge(report["challenge"])
    ov.require(ov.SHA256.fullmatch(expected_challenge_sha256 or "") and
               report["challenge_file_sha256"] == expected_challenge_sha256 and
               ov.digest(ov.canonical(request) + b"\n") == expected_challenge_sha256,
               "independent challenge checksum differs")
    public = read_file(public_key, 32)
    ov.require(len(public) == 32 and ov.digest(public) == expected_fingerprint ==
               request["expected_fingerprint"] and report["public_key_hex"] == public.hex(),
               "independent public-key fingerprint differs")
    ov.require(isinstance(report["signature_hex"], str) and
               re.fullmatch(r"[0-9a-f]{128}", report["signature_hex"]), "invalid signature encoding")
    ov.Sodium().verify(DOMAIN + ov.canonical(request), bytes.fromhex(report["signature_hex"]), public)
    return {"status": "passed", "recovered_key_matches_expected": True,
            "challenge_file_sha256": expected_challenge_sha256, "public_key_fingerprint": expected_fingerprint,
            **GATES}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("challenge")
    make.add_argument("--expected-fingerprint", required=True)
    make.add_argument("--retained-envelope-sha256", required=True)
    make.add_argument("--custody-reference", required=True)
    make.add_argument("--output", required=True, type=Path)
    proof = commands.add_parser("prove")
    proof.add_argument("--private-key", required=True, type=Path)
    proof.add_argument("--public-key", required=True, type=Path)
    proof.add_argument("--challenge-file", required=True, type=Path)
    proof.add_argument("--expected-challenge-sha256", required=True)
    proof.add_argument("--output", required=True, type=Path)
    check = commands.add_parser("verify")
    check.add_argument("--proof", required=True, type=Path)
    check.add_argument("--public-key", required=True, type=Path)
    check.add_argument("--expected-challenge-sha256", required=True)
    check.add_argument("--expected-fingerprint", required=True)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    try:
        if command == "verify":
            report = ov.decode(read_file(args.pop("proof"), MAX_DOCUMENT))
            result = verify(report, **args)
        else:
            output = args.pop("output")
            report = challenge(**args) if command == "challenge" else prove(**args)
            result = {"status": "passed", "kind": report["kind"], "report_sha256": write_report(output, report),
                      "operational_trust_established": False}
    except (OSError, ValueError, RuntimeError):
        # Do not echo key paths, raw bytes or library exception arguments.
        print("key recovery proof refused; no key exported or trust designation changed", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
