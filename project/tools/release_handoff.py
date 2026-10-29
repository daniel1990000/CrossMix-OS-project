#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare and read back a scoped host release handoff; never publish it.

The caller supplies an independent trust key/fingerprint. Bundled development
keys, checksums, operator statements and custody receipts never grant production
trust, source-use permission or device/native distribution qualification.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import struct
import sys
import tempfile
from urllib.parse import unquote, urlsplit
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "packaging"))
import overlay as ov
from dev_release import SOURCE_FOLDERS, SOURCE_ROOT_FILES, SOURCE_EXTENSIONS
from release_descriptor import original_source_file, validate_retropass_vendor, ORIGINAL_PAYLOAD

if __package__:
    from .recovery_preflight import directory_fd, fingerprint, write_report
    from .support_bundle import sanitize
else:
    from recovery_preflight import directory_fd, fingerprint, write_report
    from support_bundle import sanitize

MAX_ARTIFACT = 64 * 1024 * 1024
MAX_TOTAL = 192 * 1024 * 1024
MAX_JSON = 4 * 1024 * 1024
MAX_FILES = 4096
GATES = {"hardware_qualified": False, "runtime_verified": False, "source_use_verified": False}
STEPS = ("readback", "key-custody", "recovery", "rotation", "revocation")
REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
PEM_PRIVATE = re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{40,}-----END ")


def require(condition, message):
    ov.require(condition, message)


def reference(value):
    require(isinstance(value, str) and REFERENCE.fullmatch(value), "an opaque reviewed evidence reference is required")
    return value


def public_url(value):
    require(isinstance(value, str) and 0 < len(value) <= 2048 and
            all(32 < ord(c) < 127 for c in value), "invalid download URL metadata")
    parsed = urlsplit(value)
    require(parsed.scheme == "https" and parsed.hostname and not parsed.username and
            not parsed.password and not parsed.query and not parsed.fragment and
            parsed.port in (None, 443), "download metadata requires HTTPS without credentials or query tokens")
    host = parsed.hostname
    require(re.fullmatch(r"[A-Za-z0-9.-]+", host) and "." in host and
            not host.lower().endswith((".local", ".localhost", ".internal")), "public download hostname required")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        require(address.is_global, "private download address refused")
    path = unquote(parsed.path)
    require(not any(ord(c) < 32 or ord(c) == 127 for c in path) and
            ".." not in PurePosixPath(path).parts and "\\" not in path, "unsafe download URL path")
    return value


def read_file(path, limit=MAX_JSON):
    path = Path(path).absolute()
    parent = directory_fd(path.parent)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=parent)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit,
                    "input must be a bounded regular file")
            raw = stream.read(limit + 1)
            require(len(raw) == before.st_size and fingerprint(before) == fingerprint(os.fstat(stream.fileno())),
                    "input changed during readback")
            return raw
    finally:
        os.close(parent)


def decode(raw):
    require(len(raw) <= MAX_JSON, "JSON exceeds handoff bound")
    value = ov.decode(raw)
    require(isinstance(value, dict), "JSON object required")
    return value


def outside(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    require(path != root and root not in path.parents, "trust evidence must be independent of the supplied artifact/bundle tree")


def external_trust(public_key, expected_fingerprint, review_reference, root, registry=None):
    reference(review_reference)
    require(isinstance(expected_fingerprint, str) and ov.SHA256.fullmatch(expected_fingerprint),
            "independently expected public-key fingerprint required")
    outside(public_key, root)
    public = read_file(public_key, 32)
    require(len(public) == 32 and ov.digest(public) == expected_fingerprint, "external trust key fingerprint differs")
    registry_raw, statuses = None, {expected_fingerprint: "independently-selected"}
    if registry is not None:
        outside(registry, root)
        registry_raw = read_file(registry)
        record = decode(registry_raw)
        require(record.get("schema") == 1 and isinstance(record.get("keys"), list) and
                0 < len(record["keys"]) <= 32, "invalid external trust registry")
        statuses = {}
        for row in record["keys"]:
            require(isinstance(row, dict) and row.get("id") not in statuses, "duplicate external trust identity")
            statuses[row.get("id")] = row.get("status")
            if row.get("status") != "revoked":
                keypath = Path(row.get("public_key", ""))
                keypath = keypath if keypath.is_absolute() else Path(registry).absolute().parent / keypath
                outside(keypath, root)
                keybytes = read_file(keypath, 32)
                require(len(keybytes) == 32 and ov.digest(keybytes) == row.get("id"), "external registry key changed")
        # Existing authority performs all schema/status/epoch checks and never
        # takes its registry from an archive or from the newly built bundle.
        trust = ov.load_trust_store(public_key, registry)
        require(read_file(registry) == registry_raw and read_file(public_key, 32) == public,
                "external trust changed during inspection")
    else:
        trust = ov.load_trust_store(public_key)
        require(trust == public, "external key changed during inspection")
    return trust, {"primary_fingerprint": expected_fingerprint,
                   "registry_sha256": ov.digest(registry_raw) if registry_raw is not None else None,
                   "review_reference": review_reference, "statuses": statuses,
                   "independence_authenticated_by_tool": False, "production_trust_established": False}


def artifact_names(release):
    ov.identifier(release, "release ID")
    return {"START-HERE.txt", "build-report.json", "release-source.json", "development-verification.pub",
            "host-preview.png", release + ".tar", release + "-host-preview.zip", release + "-original-source.zip"}


def read_artifacts(root, reviewed_checksums, expected_checksums_sha256):
    report = decode(read_file(Path(root) / "build-report.json"))
    names = artifact_names(report.get("release_id"))
    descriptor = directory_fd(root)
    try:
        entries = set()
        with os.scandir(descriptor) as items:
            for item in items:
                require(len(entries) < 16, "artifact directory entry count exceeds scope")
                entries.add(item.name)
        require(entries == names | {"SHA256SUMS"}, "artifact directory differs from reviewed original-only scope")
    finally:
        os.close(descriptor)
    blobs = {name: read_file(Path(root) / name, MAX_ARTIFACT) for name in sorted(names)}
    require(sum(map(len, blobs.values())) <= MAX_TOTAL, "combined artifact byte budget exceeded")
    outside(reviewed_checksums, root)
    require(isinstance(expected_checksums_sha256, str) and ov.SHA256.fullmatch(expected_checksums_sha256),
            "independently expected artifact checksum-index digest required")
    reviewed = read_file(reviewed_checksums)
    require(ov.digest(reviewed) == expected_checksums_sha256 and
            read_file(Path(root) / "SHA256SUMS") == reviewed, "artifact checksums differ from independent review")
    checksums = reviewed.decode("ascii")
    listed = {}
    for line in checksums.splitlines():
        fields = line.split("  ", 1)
        require(len(fields) == 2 and ov.SHA256.fullmatch(fields[0]) and fields[1] in names and
                fields[1] not in listed, "invalid or duplicate artifact checksum entry")
        listed[fields[1]] = fields[0]
    require(set(listed) == names and all(ov.digest(raw) == listed[name] for name, raw in blobs.items()),
            "artifact checksum readback differs")
    return blobs


def zip_contents(raw, prefix):
    # Inspect the fixed EOCD before ZipFile materializes every central-directory
    # record. Checking len(infolist()) afterward is too late for a metadata bomb.
    require(22 <= len(raw) <= MAX_ARTIFACT and raw[-22:-18] == b"PK\x05\x06",
            "ZIP must have a bounded uncommented single-volume directory")
    _, disk, directory_disk, disk_entries, total_entries, directory_size, directory_offset, comment = struct.unpack(
        "<4s4H2LH", raw[-22:])
    require(disk == directory_disk == 0 and disk_entries == total_entries and
            0 < total_entries <= MAX_FILES and directory_size <= MAX_JSON and
            directory_offset + directory_size == len(raw) - 22 and comment == 0,
            "ZIP central-directory entry/byte budget exceeded or ZIP64/multivolume unsupported")
    offset, end = directory_offset, len(raw) - 22
    for _ in range(total_entries):
        require(offset + 46 <= end and raw[offset:offset + 4] == b"PK\x01\x02", "invalid ZIP central-directory record")
        name_size, extra_size, comment_size = struct.unpack_from("<HHH", raw, offset + 28)
        require(0 < name_size <= 200 and extra_size == comment_size == 0,
                "ZIP directory name/extra/comment scope differs from deterministic builder")
        offset += 46 + name_size
        require(offset <= end, "truncated ZIP directory")
    require(offset == end, "ZIP central-directory record count differs")
    result, total, casefolded = {}, 0, set()
    with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
        infos = archive.infolist()
        require(0 < len(infos) <= MAX_FILES, "ZIP entry count exceeds scope")
        for info in infos:
            ov.relative_path(info.filename)
            require(info.filename.startswith(prefix + "/") and not info.is_dir() and
                    info.filename.casefold() not in casefolded and info.filename not in result and
                    info.flag_bits & 1 == 0 and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                    "ZIP path, duplicate, encryption or compression scope refused")
            mode = info.external_attr >> 16
            require(stat.S_IFMT(mode) in (0, stat.S_IFREG) and mode & 0o7000 == 0,
                    "ZIP links/special files or unsafe modes refused")
            require(0 <= info.file_size <= ov.MAX_FILE, "ZIP entry exceeds uncompressed byte bound")
            total += info.file_size
            require(total <= MAX_TOTAL, "ZIP uncompressed total exceeds bound")
            with archive.open(info) as stream:
                data = stream.read(info.file_size + 1)
            require(len(data) == info.file_size, "ZIP entry length differs")
            require(not data.startswith(b"\x7fELF") and not PEM_PRIVATE.search(data),
                    "native binary or private key in original-only artifact")
            relative = info.filename.removeprefix(prefix + "/")
            parts = PurePosixPath(relative).parts
            require(not {x.casefold() for x in parts} & {"roms", "saves", "secrets", "transactions", "migrations", "fixtures"},
                    "owner/private runtime data is outside original artifact scope")
            result[info.filename] = data
            casefolded.add(info.filename.casefold())
    return result


def inspect_artifacts(blobs, trust):
    report = decode(blobs["build-report.json"])
    release = report.get("release_id")
    require(set(blobs) == artifact_names(release), "bundle artifact scope differs")
    snapshot = decode(blobs["release-source.json"])
    selection = report.get("release_selection")
    require(isinstance(selection, dict) and isinstance(selection.get("descriptor"), dict), "release selection missing")
    descriptor = selection["descriptor"]
    require(report.get("schema") == 1 and report.get("status") == "host-development-preview" and
            report.get("device_activation_qualified") is False and report.get("device_gates") == GATES and
            report.get("private_key_packaged") is False and report.get("production_authenticity_claim") is False,
            "handoff accepts only an unqualified original host preview")
    retropass = descriptor.get("delivery") == "retropass-host-preview"
    require(descriptor.get("selected_third_party_payload", []) == (["retropass"] if retropass else []),
            "unreviewed third-party payload scope")
    require(descriptor.get("release_id") == release and descriptor.get("delivery") in {"original-only-host-preview", "retropass-host-preview"} and
            descriptor.get("qualification") == GATES and descriptor.get("selected_native_binaries") == [] and
            descriptor.get("selected_upstream_patches") == [] and descriptor.get("selected_original_payload") in ([
                "psp_shell", "bridge", "profiles", "ppsspp/theme", "assets"], ORIGINAL_PAYLOAD),
            "native/device/derivative release requires separately implemented review")
    references = descriptor.get("optional_native_references", [])
    require(isinstance(references, list) and len(references) <= 32 and all(
        isinstance(row, dict) and row.get("selected") is False and row.get("device_qualified") is False
        for row in references), "optional native references must remain unselected/unqualified")
    require(descriptor.get("base", {}).get("source_commit") == ov.SPRUCE_COMMIT and
            descriptor["base"].get("pyui_git_tree") == ov.PYUI_TREE, "base source identity differs")
    require(snapshot.get("schema") == 1 and snapshot.get("frontend") == selection.get("frontend") and
            snapshot.get("frontend", {}).get("working_tree_modified") is False and
            ov.BASELINE.fullmatch(snapshot["frontend"].get("commit", "")), "clean exact frontend source identity required")
    inventory = snapshot.get("source_inventory")
    require(isinstance(inventory, list) and 0 < len(inventory) <= MAX_FILES, "source inventory missing or oversized")
    require(ov.digest(ov.canonical(inventory)) == snapshot.get("source_inventory_sha256") == selection.get("source_inventory_sha256") and
            snapshot.get("descriptor_sha256") == selection.get("descriptor_sha256"), "source inventory/descriptor identity differs")
    require(all(report.get(key) is True for key in
                ("signature_hash_inventory_verified", "byte_identical_overlay_rebuild_with_same_key", "fixture_stage_activate_rollback")),
            "required host package checks absent")
    require(report.get("smoke", {}).get("executed") is True and
            report["smoke"].get("physical_device_verified") is False and
            report["smoke"].get("real_game_launches") == 0, "host smoke scope missing or inconsistent")

    with tempfile.TemporaryDirectory(prefix="smartpro-handoff-check-") as temporary:
        tarpath = Path(temporary) / "preview.tar"
        tarpath.write_bytes(blobs[release + ".tar"])
        with ov.VerifiedArchive(tarpath, trust) as archive:
            manifest = archive.manifest
            require(manifest.get("release_id") == release and
                    manifest.get("profile", {}).get("execution_environment") == "host-fixture" and
                    all(manifest["profile"].get(key) is False for key in GATES), "signed payload is outside host-fixture scope")
            require(ov.digest(blobs["development-verification.pub"]) == manifest["key_id"] == report.get("development_key_id"),
                    "bundled informational public key or signer report differs")
            payload = {row["path"]: archive.archive.extractfile("payload/" + row["path"]).read(ov.MAX_FILE + 1)
                       for row in manifest["files"]}
            signed = decode(payload.get("metadata/development-release.json", b"{}"))
            require(signed.get("release_selection") == selection and signed.get("device_activation_qualified") is False,
                    "build provenance is not bound to the verified signed metadata")
            manifest_sha256 = ov.digest(archive.manifest_bytes)

    preview = zip_contents(blobs[release + "-host-preview.zip"], "smartpro-host-preview")
    expected_preview = {"smartpro-host-preview/" + name: data for name, data in payload.items()}
    expected_preview["smartpro-host-preview/RUN.txt"] = blobs["START-HERE.txt"]
    require(preview == expected_preview and blobs["START-HERE.txt"].startswith(b"HOST DEVELOPMENT PREVIEW ONLY."),
            "preview ZIP does not match the signed payload and host instructions")
    require(blobs["host-preview.png"].startswith(b"\x89PNG\r\n\x1a\n") and len(blobs["host-preview.png"]) <= 8 * 1024 * 1024,
            "preview screenshot format/size differs")
    sources = zip_contents(blobs[release + "-original-source.zip"], "smartpro-original-source")
    expected_source, folded = {}, set()
    for row in inventory:
        require(isinstance(row, dict), "source inventory row malformed")
        name = ov.relative_path(row.get("path"))
        parts = PurePosixPath(name).parts
        require(name.casefold() not in folded and
                (original_source_file(name) or name == "metadata/spruce-source-lock.json"), "source archive contains an unreviewed source/asset scope")
        key = "smartpro-original-source/" + name
        data = sources.get(key)
        require(data is not None and len(data) == row.get("size") and ov.digest(data) == row.get("sha256"),
                "source archive differs from exact signed source inventory")
        expected_source[key] = data
        folded.add(name.casefold())
    if retropass:
        validate_retropass_vendor(PROJECT, sources)
    else:
        require(not any(name.startswith(("smartpro-original-source/retropass/",
                                         "smartpro-original-source/vendor/retropass/")) for name in sources),
                "legacy original-only descriptor cannot include RetroPass source")
    embedded = "smartpro-original-source/metadata/release-source.json"
    require(decode(sources.get(embedded, b"{}")) == snapshot and set(sources) == set(expected_source) | {embedded},
            "source export contains missing/extra entries or changed provenance")
    require(ov.digest(sources.get("smartpro-original-source/packaging/current-release.json", b"")) == snapshot["descriptor_sha256"],
            "source descriptor bytes differ")
    for source, notice in (("LICENSE", "notices/ORIGINAL-PROJECT-LICENSE.txt"),
                           ("assets/fonts/OFL.txt", "notices/NotoSans-OFL.txt")):
        require(payload.get(notice) == sources.get("smartpro-original-source/" + source) and payload.get(notice),
                "corresponding original/font notice absent or changed")
    require("notices/DEPENDENCIES.txt" in payload and b"SIL OPEN FONT LICENSE" in payload["notices/NotoSans-OFL.txt"],
            "dependency/font notices missing")
    for name, data in payload.items():
        if name.startswith("app/") or name.startswith("assets/"):
            original = name.removeprefix("app/") if name.startswith("app/") else name
            require(sources.get("smartpro-original-source/" + original) == data,
                    "signed runtime code/asset differs from corresponding source inventory")
        elif retropass and name.startswith("notices/RetroPass-source/"):
            original = "vendor/retropass/" + name.removeprefix("notices/RetroPass-source/")
            require(sources.get("smartpro-original-source/" + original) == data,
                    "bundled RetroPass source differs from inventory")
        elif retropass and name in {"notices/RetroPass-NOTICE.txt", "notices/RetroPass-GPL-2.0.txt"}:
            original = ("retropass/NOTICE.txt" if name.endswith("NOTICE.txt") else "vendor/retropass/LICENSE.txt")
            require(sources.get("smartpro-original-source/" + original) == data, "RetroPass notice differs")
        else:
            require(name in {"metadata/development-release.json", "metadata/source-provenance.json", "metadata/original-payload.json",
                             "notices/ORIGINAL-PROJECT-LICENSE.txt", "notices/NotoSans-OFL.txt", "notices/DEPENDENCIES.txt"},
                    "unreviewed metadata or notice in signed payload")
    if retropass:
        for name, data in sources.items():
            prefix = "smartpro-original-source/vendor/retropass/"
            if name.startswith(prefix):
                require(payload.get("notices/RetroPass-source/" + name.removeprefix(prefix)) == data,
                        "corresponding complete RetroPass source missing")
        require(payload.get("notices/RetroPass-NOTICE.txt") and payload.get("notices/RetroPass-GPL-2.0.txt"),
                "RetroPass licence notices missing")
    require(report.get("payload_files") == len(payload), "payload file count differs from build evidence")
    return {"release_id": release, "frontend": snapshot["frontend"],
            "source_inventory_sha256": snapshot["source_inventory_sha256"],
            "source_files": len(inventory), "payload_files": len(payload),
            "package_signer_fingerprint": manifest["key_id"], "manifest_sha256": manifest_sha256,
            "base_commit": ov.SPRUCE_COMMIT, "pyui_git_tree": ov.PYUI_TREE,
            "selected_native_binaries": [], "selected_upstream_patches": [],
            "device_gates": GATES.copy(), "distribution_cleared": False,
            "device_ready": False, "original_only": not retropass,
            **({"third_party_source": {"retropass": "GPL-2.0-only"}} if retropass else {})}


def instructions(release, retropass=False):
    text = ("# Host review handoff\n\n"
            "This bundle is a computer preview and source-review deliverable. It is not an SD image or a device install.\n"
            "No installed emulator, firmware, commercial game data, owner saves or private keys are supplied.\n\n"
            "Install/update: extract artifacts/" + release + "-host-preview.zip into a NEW host directory.\n"
            "Follow its RUN.txt using an isolated Python environment; keep mutable state outside the payload.\n"
            "An update is another new directory. The source ZIP contains only the explicitly inventoried original source and notices.\n\n"
            "Rollback: stop the host preview and use the previous untouched preview directory.\n"
            "The signed overlay can be staged only against an explicitly marked host fixture with the existing overlay verifier.\n"
            "No command here installs on /mnt/SDCARD, changes rootfs, restores a physical card or clears runtime gates.\n"
            "Keep D02 whole-card/internal restoration separate from host overlay rollback.\n\n"
            "Known limits: all original-device acceptance remains unrun; no physical performance, battery, Resume or recovery result.\n"
            "Native PPSSPP/RetroArch replacements, native ports and upstream derivative patches are excluded.\n"
            "R05/R06 permissions and operational trust custody remain separate owner-reviewed work.\n\n"
            "Trust: retain index.json's SHA-256 independently, then use release_handoff.py verify with an external reviewed key/fingerprint.\n"
            "The public key in artifacts is informational; selecting a key supplied by its own package establishes no independent trust.\n"
            "The proposed HTTPS download URL is metadata only: availability, longevity and publication are not established.\n\n"
            "Support: support-export.json is a minimal redacted package summary, not device diagnostics.\n"
            "For operator-selected observations use tools/support_bundle.py; review its local output before sharing. No upload is automatic.\n\n"
            "Custody: use custody-receipt for immutable readback, external-custody/recovery references and registry rotation/revocation observations.\n"
            "Receipts are checksummed operator records, not signatures or proof that a private key can be recovered.\n")
    if retropass:
        text = text.replace("only the explicitly inventoried original source and notices",
                            "the inventoried original helpers and complete GPL-2.0-only RetroPass source and adaptations")
        text += "\nRetroPass retains its GPL-2.0-only licence and authors; see notices/RetroPass-NOTICE.txt.\n"
    return text.encode()


def support_matrix(retropass=False):
    return {"schema": 1, "delivery": "retropass-host-review" if retropass else "original-only-host-review", "tested_runtime": "host preview only",
            "intended_hardware": "original TrimUI Smart Pro TG5040", "supported_device_firmware": [],
            "supported_device_filesystems": [], "physical_areas_run": 0,
            "included_engines": [], "included_ports": [], "device_install_supported": False,
            "device_gates": GATES.copy(), "distribution_cleared": False,
            "source_use_review": ("original project/font and pinned GPL-2.0-only RetroPass notices and complete corresponding source"
                                  if retropass else "original project/font notices only; upstream derivative and native rights remain separate")}


def _new_private_directory(parent, name):
    os.mkdir(name, 0o700, dir_fd=parent)
    created = os.stat(name, dir_fd=parent, follow_symlinks=False)
    require(stat.S_ISDIR(created.st_mode) and stat.S_IMODE(created.st_mode) == 0o700 and
            created.st_uid == os.getuid(), "new handoff directory is not private and owned")
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        opened = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        require(fingerprint(created) == fingerprint(opened) == fingerprint(named),
                "new handoff directory changed between creation and open")
        with os.scandir(descriptor) as entries:
            require(next(entries, None) is None, "new handoff directory must be empty before writing")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _publish_directory(output, files, roots):
    output = Path(output).absolute()
    require(output.name and all(output != Path(root).absolute() and Path(root).absolute() not in output.parents
                                for root in roots), "handoff output must be outside inputs")
    parent = directory_fd(output.parent)
    temporary = ".handoff-" + secrets.token_hex(16)
    descriptors = {}
    staging_identity = None
    try:
        try:
            os.stat(output.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ov.OverlayError("handoff output already exists")
        descriptors[()] = _new_private_directory(parent, temporary)
        info = os.fstat(descriptors[()])
        staging_identity = (info.st_dev, info.st_ino)
        for name, raw in sorted(files.items()):
            ov.relative_path(name)
            parts = PurePosixPath(name).parts
            for length in range(1, len(parts)):
                prefix = parts[:length]
                if prefix not in descriptors:
                    descriptors[prefix] = _new_private_directory(descriptors[prefix[:-1]], prefix[-1])
            descriptor = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 0o600, dir_fd=descriptors[parts[:-1]])
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        for prefix, descriptor in sorted(descriptors.items(), key=lambda item: len(item[0]), reverse=True):
            os.fsync(descriptor)
        # Linux renameat2 refuses an existing destination atomically. A check
        # followed by rename could replace a concurrently created empty folder.
        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, "renameat2", None)
        require(rename is not None, "atomic no-replace directory publication unavailable")
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(parent, os.fsencode(temporary), parent, os.fsencode(output.name), 1) != 0:
            raise OSError(ctypes.get_errno(), "atomic no-replace publication failed")
        installed = os.stat(output.name, dir_fd=parent, follow_symlinks=False)
        require((installed.st_dev, installed.st_ino) == staging_identity,
                "handoff directory identity changed during publication")
        os.fsync(parent)
    finally:
        # Retain ALL uncertain staging/output after any failure. A prior stat
        # followed by rmtree(name) would still delete a swapped-in directory.
        # No recursive pathname cleanup belongs to this publication boundary.
        for descriptor in descriptors.values():
            os.close(descriptor)
        os.close(parent)


def prepare(artifacts, output, *, public_key, expected_fingerprint, trust_reference, stable_url,
            reviewed_checksums, expected_checksums_sha256, registry=None):
    url = public_url(stable_url)
    trust, trust_summary = external_trust(public_key, expected_fingerprint, trust_reference, artifacts, registry)
    blobs = read_artifacts(artifacts, reviewed_checksums, expected_checksums_sha256)
    candidate = inspect_artifacts(blobs, trust)
    trust_summary["package_signer_fingerprint"] = candidate["package_signer_fingerprint"]
    files = {"artifacts/" + name: raw for name, raw in blobs.items()}
    files["README.md"] = instructions(candidate["release_id"], not candidate["original_only"])
    files["support-matrix.json"] = ov.canonical(support_matrix(not candidate["original_only"])) + b"\n"
    files["trust-review.json"] = ov.canonical(trust_summary) + b"\n"
    files["custody-checklist.json"] = ov.canonical({
        "schema": 1, "steps": [{"step": step, "status": "pending"} for step in STEPS],
        "operational_trust_established": False, "receipts_are_operator_evidence_not_qualification": True}) + b"\n"
    files["support-export.json"] = ov.canonical({"schema": 1, "kind": "local-redacted-support",
        "automatic_upload": False, "review_before_sharing": True,
        "entries": [{"role": "release-handoff", "data": sanitize(candidate)}]}) + b"\n"
    index = {"schema": 1, "kind": "retropass-release-review-handoff" if not candidate["original_only"] else "original-only-release-review-handoff", "candidate": candidate,
             "reviewed_artifact_checksum_index_sha256": expected_checksums_sha256,
             "proposed_download_url": url, "download_availability_verified": False, "published": False,
             "external_index_digest_required": True, "independent_trust_required": True,
             "production_trust_established": False, "device_ready": False,
             "files": [{"path": name, "bytes": len(raw), "sha256": ov.digest(raw)} for name, raw in sorted(files.items())]}
    files["index.json"] = ov.canonical(index) + b"\n"
    roots = [artifacts, public_key, reviewed_checksums] + ([registry] if registry is not None else [])
    _publish_directory(output, files, roots)
    # Read the actual published directory, not only the previously prepared
    # buffers. A swapped source directory or changed installed byte cannot
    # receive a successful handoff receipt.
    verify(output, expected_index=ov.digest(files["index.json"]), public_key=public_key,
           expected_fingerprint=expected_fingerprint, trust_reference=trust_reference, registry=registry)
    return {"status": "prepared-retropass-review" if not candidate["original_only"] else "prepared-original-only-review", "index_sha256": ov.digest(files["index.json"]),
            "release_id": candidate["release_id"], "files": len(files), "published": False, "device_ready": False}


def load_bundle(bundle, expected_index):
    bundle = Path(bundle).absolute()
    require(isinstance(expected_index, str) and ov.SHA256.fullmatch(expected_index), "independent expected index digest required")
    raw = read_file(Path(bundle) / "index.json")
    require(ov.digest(raw) == expected_index, "handoff index differs from independent expected digest")
    index = decode(raw)
    require(index.get("schema") == 1 and index.get("kind") in {"original-only-release-review-handoff", "retropass-release-review-handoff"} and
            index.get("device_ready") is False and index.get("production_trust_established") is False and
            index.get("published") is False and index.get("download_availability_verified") is False,
            "handoff cannot grant device, publication or operational trust")
    candidate = index.get("candidate", {})
    require(isinstance(candidate, dict) and candidate.get("device_ready") is False and
            candidate.get("distribution_cleared") is False and candidate.get("device_gates") == GATES and
            candidate.get("selected_native_binaries") == [] and candidate.get("selected_upstream_patches") == [],
            "handoff candidate cannot grant native/device distribution")
    public_url(index.get("proposed_download_url"))
    release = index.get("candidate", {}).get("release_id")
    allowed = {"artifacts/" + name for name in artifact_names(release)} | {
        "README.md", "support-matrix.json", "trust-review.json", "custody-checklist.json", "support-export.json"}
    rows = index.get("files")
    require(isinstance(rows, list) and 0 < len(rows) <= 32, "invalid handoff file count")
    files, total = {}, 0
    for row in rows:
        require(isinstance(row, dict), "invalid handoff file record")
        name = ov.relative_path(row.get("path"))
        require(name in allowed and name not in files and type(row.get("bytes")) is int and 0 <= row["bytes"] <= MAX_ARTIFACT and
                ov.SHA256.fullmatch(row.get("sha256", "")), "invalid or duplicate handoff identity")
        data = read_file(Path(bundle) / name, MAX_ARTIFACT)
        require(len(data) == row["bytes"] and ov.digest(data) == row["sha256"], "handoff content readback differs")
        files[name] = data
        total += len(data)
        require(total <= MAX_TOTAL, "handoff byte budget exceeded")
    require(set(files) == allowed, "handoff file scope incomplete")
    for directory, expected in ((bundle, {name for name in allowed if "/" not in name} | {"artifacts", "index.json"}),
                                (bundle / "artifacts", artifact_names(release))):
        descriptor = directory_fd(directory)
        try:
            observed = set()
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    require(len(observed) < 32, "handoff directory exceeds entry bound")
                    observed.add(entry.name)
            require(observed == expected, "handoff contains unindexed entries")
        finally:
            os.close(descriptor)
    return index, files


def verify(bundle, *, expected_index, public_key, expected_fingerprint, trust_reference, registry=None):
    index, files = load_bundle(bundle, expected_index)
    trust, _ = external_trust(public_key, expected_fingerprint, trust_reference, bundle, registry)
    blobs = {name.removeprefix("artifacts/"): data for name, data in files.items() if name.startswith("artifacts/")}
    candidate = inspect_artifacts(blobs, trust)
    require(candidate == index.get("candidate") and
            decode(files.get("support-matrix.json", b"{}")) == support_matrix(not candidate["original_only"]) and
            files.get("README.md") == instructions(candidate["release_id"], not candidate["original_only"]), "handoff scope/instructions or candidate changed")
    return {"status": "verified-retropass-review" if not candidate["original_only"] else "verified-original-only-review", "index_sha256": expected_index,
            "candidate": candidate, "production_trust_established": False, "published": False}


def custody_receipt(bundle, output, *, step, evidence_reference, expected_index, public_key,
                    expected_fingerprint, trust_reference, registry=None, previous=None):
    require(step in STEPS, "unknown custody checklist step")
    reference(evidence_reference)
    index, files = load_bundle(bundle, expected_index)
    trust, summary = external_trust(public_key, expected_fingerprint, trust_reference, bundle, registry)
    signer = index.get("candidate", {}).get("package_signer_fingerprint")
    if step == "revocation":
        require(registry is not None and summary["statuses"].get(signer) == "revoked", "actual external registry must revoke this package signer")
        blobs = {name.removeprefix("artifacts/"): data for name, data in files.items() if name.startswith("artifacts/")}
        public = blobs["development-verification.pub"]
        require(len(public) == 32 and ov.digest(public) == signer, "revocation package signer identity differs")
        # The diagnostic key is bound to the independently reviewed index. It
        # checks package integrity only; it must never replace external trust
        # for activation. Otherwise any unknown-key or corrupted archive could
        # be credited as an observation of this exact signer's revocation.
        candidate = inspect_artifacts(blobs, public)
        require(candidate == index["candidate"] and
                decode(files["support-matrix.json"]) == support_matrix(not candidate["original_only"]) and
                files["README.md"] == instructions(candidate["release_id"], not candidate["original_only"]),
                "revocation handoff scope/instructions or candidate changed")
        release = index["candidate"]["release_id"]
        with tempfile.TemporaryDirectory(prefix="smartpro-revocation-check-") as name:
            path = Path(name) / "preview.tar"
            path.write_bytes(files["artifacts/" + release + ".tar"])
            try:
                with ov.VerifiedArchive(path, trust):
                    pass
            except ov.OverlayError as error:
                require("unknown or revoked" in str(error), "revocation observation failed for another reason")
            else:
                raise ov.OverlayError("revoked package was unexpectedly accepted")
        result = "external-registry-rejects-exact-package"
    else:
        verify(bundle, expected_index=expected_index, public_key=public_key, expected_fingerprint=expected_fingerprint,
               trust_reference=trust_reference, registry=registry)
        if step == "rotation":
            require(registry is not None and signer != expected_fingerprint and
                    summary["statuses"].get(signer) == "retired" and
                    summary["statuses"].get(expected_fingerprint) == "active", "actual retired-to-active external registry transition required")
            result = "retired-package-verified-through-new-primary"
        else:
            result = "exact-bundle-readback-verified" if step == "readback" else "operator-reference-retained-not-independently-proven"
    prior_digest = None
    if previous is not None:
        prior_raw = read_file(previous)
        prior = decode(prior_raw)
        require(prior.get("kind") == "release-handoff-custody-observation" and
                prior.get("index_sha256") == expected_index and prior.get("production_trust_established") is False,
                "prior receipt belongs to another bundle or claims unsupported trust")
        prior_digest = ov.digest(prior_raw)
    receipt = {"schema": 1, "kind": "release-handoff-custody-observation", "index_sha256": expected_index,
               "step": step, "result": result, "evidence_reference": evidence_reference,
               "trust_review_reference": trust_reference, "primary_fingerprint": expected_fingerprint,
               "package_signer_fingerprint": signer, "registry_sha256": summary["registry_sha256"],
               "previous_receipt_sha256": prior_digest, "production_trust_established": False,
               "actual_private_key_custody_verified": False, "actual_key_recovery_verified": False,
               "operator_statement_authentication": "not-signed-by-this-tool"}
    write_report(output, receipt, [Path(bundle).absolute()] + ([Path(previous).absolute()] if previous is not None else []))
    return {"status": result, "receipt_sha256": ov.digest(read_file(output)),
            "production_trust_established": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "verify", "custody-receipt"):
        command = commands.add_parser(name)
        command.add_argument("--public-key", required=True, type=Path)
        command.add_argument("--expected-fingerprint", required=True)
        command.add_argument("--trust-reference", required=True)
        command.add_argument("--registry", type=Path)
        if name == "prepare":
            command.add_argument("--artifacts", required=True, type=Path)
            command.add_argument("--output", required=True, type=Path)
            command.add_argument("--stable-url", required=True)
            command.add_argument("--reviewed-checksums", required=True, type=Path)
            command.add_argument("--expected-checksums-sha256", required=True)
        else:
            command.add_argument("--bundle", required=True, type=Path)
            command.add_argument("--expected-index", required=True)
        if name == "custody-receipt":
            command.add_argument("--output", required=True, type=Path)
            command.add_argument("--step", required=True, choices=STEPS)
            command.add_argument("--evidence-reference", required=True)
            command.add_argument("--previous", type=Path)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    try:
        function = {"prepare": prepare, "verify": verify, "custody-receipt": custody_receipt}[command]
        print(json.dumps(function(**args), sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError):
        print("release handoff refused: changed, unsupported or unreviewed inputs", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
