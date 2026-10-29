#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline signed original Python extensions for spruceOS 4.5.4/TG5040.

Python 3 and the system libsodium are the only runtime dependencies. This is
host tooling. Device activation remains gated on runtime/source-use evidence.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import ctypes.util
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import unicodedata

SCHEMA = 1
MAX_ARCHIVE = 256 * 1024 * 1024
MAX_TOTAL = 192 * 1024 * 1024
MAX_FILE = 32 * 1024 * 1024
MAX_MANIFEST = 2 * 1024 * 1024
MAX_FILES = 4096
RESERVE_BYTES = 16 * 1024 * 1024
PLAN_SOURCE_DATE_EPOCH = 1792659237
SPRUCE_COMMIT = "d45ff8dfe5756147522b04ae5863d17a90e88b54"
PYUI_TREE = "4d0bdb3111d9226fbacbea6c89d65e540620e21e"
PAYLOAD_ROOTS = {"app", "assets", "metadata", "notices"}
ENTRYPOINT = "app/psp_shell/__main__.py"
FIXTURE_MARKER = b"spruce-psp-host-fixture-v1\n"
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
BASELINE = re.compile(r"[0-9a-f]{40}\Z")
FORBIDDEN_NAMES = {".git", ".env", "id_rsa", "id_ed25519", "secrets"}


class OverlayError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise OverlayError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git_blob_digest(path):
    path = Path(path)
    h = hashlib.sha1()
    h.update(("blob " + str(path.stat().st_size) + "\0").encode("ascii"))
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def decode(data):
    require(len(data) <= MAX_MANIFEST, "JSON exceeds size limit")
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates,
                          parse_constant=lambda x: (_ for _ in ()).throw(OverlayError("invalid JSON constant")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise OverlayError("invalid JSON") from exc


def read_json(path):
    with open(path, "rb") as handle:
        data = handle.read(MAX_MANIFEST + 1)
    value = decode(data)
    require(isinstance(value, dict), "JSON object required")
    return value


def identifier(value, label="identifier"):
    require(isinstance(value, str) and IDENTIFIER.fullmatch(value), "invalid " + label)
    return value


def relative_path(value):
    require(isinstance(value, str) and 0 < len(value.encode("utf-8")) <= 200, "invalid payload path length")
    require("\\" not in value and "\x00" not in value and ":" not in value, "non-portable payload path")
    require(not any(ord(c) < 32 or ord(c) == 127 for c in value), "control character in payload path")
    parts = value.split("/")
    require(all(x and x not in {".", ".."} for x in parts), "unsafe payload path")
    require(not PurePosixPath(value).is_absolute(), "absolute payload path")
    require(all(not x.endswith((" ", ".")) for x in parts), "unsafe FAT path")
    require(unicodedata.normalize("NFC", value) == value, "payload paths must use NFC Unicode normalization")
    reserved = {"con", "prn", "aux", "nul"} | {"com" + str(x) for x in range(1, 10)} | {"lpt" + str(x) for x in range(1, 10)}
    require(all(x.split(".", 1)[0].casefold() not in reserved for x in parts), "reserved FAT/Windows payload name")
    require(all(x.casefold() not in FORBIDDEN_NAMES for x in parts), "secret or repository metadata in payload")
    require(not any(x.casefold().endswith((".key", ".pem")) for x in parts), "private-key-like payload path")
    return value


class Sodium:
    """Bind the documented detached Ed25519 API, never a Python crypto implementation."""
    def __init__(self):
        name = ctypes.util.find_library("sodium")
        require(name is not None, "libsodium is required (for example libsodium23 on Debian)")
        self.lib = ctypes.CDLL(name)
        self.lib.sodium_init.restype = ctypes.c_int
        require(self.lib.sodium_init() >= 0, "libsodium initialization failed")
        self.lib.crypto_sign_seed_keypair.argtypes = [ctypes.c_void_p] * 3
        self.lib.crypto_sign_seed_keypair.restype = ctypes.c_int
        self.lib.crypto_sign_detached.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                                 ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_void_p]
        self.lib.crypto_sign_detached.restype = ctypes.c_int
        self.lib.crypto_sign_verify_detached.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                                        ctypes.c_ulonglong, ctypes.c_void_p]
        self.lib.crypto_sign_verify_detached.restype = ctypes.c_int

    def keypair(self):
        public = ctypes.create_string_buffer(32)
        secret = ctypes.create_string_buffer(64)
        seed = ctypes.create_string_buffer(os.urandom(32), 32)
        require(self.lib.crypto_sign_seed_keypair(public, secret, seed) == 0, "key generation failed")
        return public.raw, secret.raw

    def sign(self, data, secret):
        require(len(secret) == 64, "Ed25519 secret key must be 64 raw bytes")
        out = ctypes.create_string_buffer(64)
        length = ctypes.c_ulonglong()
        require(self.lib.crypto_sign_detached(out, ctypes.byref(length), data, len(data), secret) == 0,
                "Ed25519 signing failed")
        require(length.value == 64, "unexpected signature length")
        return out.raw

    def verify(self, data, signature, public):
        require(len(public) == 32 and len(signature) == 64, "invalid Ed25519 key/signature length")
        require(self.lib.crypto_sign_verify_detached(signature, data, len(data), public) == 0,
                "manifest signature rejected")


def load_key(path, length):
    info = Path(path).lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size == length, "key must be a regular raw-byte file")
    return Path(path).read_bytes()


def load_trust_store(public_path, registry_path=None, signing=False):
    """An optional *external*, reviewed registry adds rotation and revocation.

    The primary public key remains explicit. Retired keys can verify older
    releases; revoked keys cannot. Never obtain this registry from a package.
    """
    primary = load_key(public_path, 32)
    if registry_path is None:
        return primary
    registry = read_json(registry_path)
    require(registry.get("schema") == 1 and isinstance(registry.get("keys"), list), "invalid trust registry")
    require(0 < len(registry["keys"]) <= 32, "invalid trust registry key count")
    seen, trusted, statuses = set(), {}, {}
    for item in registry["keys"]:
        require(isinstance(item, dict), "invalid trust key")
        key_id = item.get("id")
        require(isinstance(key_id, str) and SHA256.fullmatch(key_id) and key_id not in seen, "invalid/duplicate trust key id")
        require(item.get("status") in {"active", "retired", "revoked"}, "invalid trust key status")
        require(type(item.get("introduced_epoch")) is int and item["introduced_epoch"] >= 0, "key introduction epoch required")
        seen.add(key_id)
        statuses[key_id] = item["status"]
        if item["status"] != "revoked":
            key_path = item.get("public_key")
            require(isinstance(key_path, str), "public key path required")
            path = Path(key_path)
            if not path.is_absolute():
                path = Path(registry_path).absolute().parent / path
            public = load_key(path, 32)
            require(digest(public) == key_id, "registry public-key hash mismatch")
            trusted[key_id] = public
    require(digest(primary) in trusted, "primary key is missing or revoked in trust registry")
    require(not signing or statuses[digest(primary)] == "active", "only active keys may sign new packages")
    return trusted


def trusted_public(manifest_bytes, trust):
    if isinstance(trust, bytes):
        return trust
    candidate = decode(manifest_bytes)
    require(isinstance(candidate, dict), "manifest must be an object")
    key_id = candidate.get("key_id")
    require(isinstance(key_id, str) and key_id in trust, "manifest key is unknown or revoked")
    return trust[key_id]


def validate_profile(profile):
    require(isinstance(profile, dict), "profile must be an object")
    require(profile.get("schema") == SCHEMA, "unsupported profile schema")
    identifier(profile.get("id"), "profile id")
    require(profile.get("model") == "trimui-smart-pro", "only original TrimUI Smart Pro is allowed")
    require(profile.get("architecture") == "aarch64", "only original Smart Pro AArch64 is allowed")
    require(profile.get("execution_environment") in {"device", "host-fixture"}, "explicit execution environment required")
    versions = profile.get("firmware_versions")
    require(isinstance(versions, list) and 0 < len(versions) <= 16 and
            all(isinstance(x, str) and 0 < len(x) <= 96 for x in versions), "explicit firmware allowlist required")
    require(profile.get("base_commit") == SPRUCE_COMMIT and profile.get("pyui_git_tree") == PYUI_TREE,
            "only the pinned spruceOS/PyUI snapshot is supported")
    for gate in ("hardware_qualified", "runtime_verified", "source_use_verified"):
        require(type(profile.get(gate)) is bool, "profile must state " + gate)
    contracts = profile.get("baseline_files")
    require(isinstance(contracts, dict) and 0 < len(contracts) <= 128, "baseline contract hashes required")
    for path, hash_value in contracts.items():
        relative_path(path)
        require(path.startswith(("spruce/", "App/", "Emu/", "trimui/", ".tmp_update/", "base/")),
                "invalid baseline contract root")
        require(isinstance(hash_value, str) and (SHA256.fullmatch(hash_value) or BASELINE.fullmatch(hash_value)),
                "invalid baseline contract hash")
    return profile


def validate_manifest(manifest):
    require(isinstance(manifest, dict), "manifest must be an object")
    require(manifest.get("schema") == SCHEMA, "unsupported package schema")
    identifier(manifest.get("release_id"), "release id")
    require(manifest.get("kind") == "python-extension", "only scoped Python extensions are accepted")
    require(manifest.get("license") in {"MIT-project-code-only", "GPL-2.0-only AND MIT AND OFL-1.1"},
            "explicit supported project licence scope required")
    require(isinstance(manifest.get("key_id"), str) and SHA256.fullmatch(manifest["key_id"]), "invalid key id")
    for key in ("security_epoch", "data_schema_epoch", "source_date_epoch"):
        require(type(manifest.get(key)) is int and 0 <= manifest[key] <= 2**53, "invalid " + key)
    validate_profile(manifest.get("profile", {}))
    files = manifest.get("files")
    require(isinstance(files, list) and 0 < len(files) <= MAX_FILES, "invalid manifest file count")
    seen, seen_case, total = set(), set(), 0
    for item in files:
        require(isinstance(item, dict) and set(item) == {"path", "size", "sha256", "mode"}, "invalid file record")
        path = relative_path(item["path"])
        require(path.split("/", 1)[0] in PAYLOAD_ROOTS, "payload must stay in project app/assets/metadata/notices")
        require(not path.casefold().endswith((".so", ".elf", ".exe", ".awimg")), "base/emulator/firmware binaries are excluded")
        require(path not in seen and path.casefold() not in seen_case, "duplicate or case-colliding payload path")
        require(type(item["size"]) is int and 0 <= item["size"] <= MAX_FILE, "file exceeds limit")
        require(type(item["mode"]) is int and item["mode"] in {0o644, 0o755}, "unsupported file permissions")
        require(isinstance(item["sha256"], str) and SHA256.fullmatch(item["sha256"]), "invalid payload hash")
        seen.add(path)
        seen_case.add(path.casefold())
        total += item["size"]
    retropass = any(path.startswith(("app/retropass/", "notices/RetroPass-source/")) for path in seen)
    require(manifest.get("license") == ("GPL-2.0-only AND MIT AND OFL-1.1" if retropass else "MIT-project-code-only"),
            "manifest licence scope differs from payload")
    if retropass:
        require({"notices/RetroPass-GPL-2.0.txt", "notices/RetroPass-NOTICE.txt",
                 "app/retropass/source-lock.json", "notices/RetroPass-source/LICENSE.txt",
                 "notices/RetroPass-source/AUTHORS.md"}.issubset(seen),
                "RetroPass corresponding source and licence notices missing")
    require(total <= MAX_TOTAL, "package expands beyond size limit")
    for path in seen:
        require(not any(str(parent) in seen_case for parent in PurePosixPath(path.casefold()).parents
                        if str(parent) != "."), "file is also a parent directory")
    require([x["path"] for x in files] == sorted(seen), "manifest file ordering is not deterministic")
    require(ENTRYPOINT in seen, "original Python presentation entrypoint missing")
    return manifest


class VerifiedArchive:
    """Hold one open archive FD from signature verification through extraction."""
    def __init__(self, path, public):
        self.handle = open(path, "rb")
        try:
            require(stat.S_ISREG(os.fstat(self.handle.fileno()).st_mode), "archive is not a regular file")
            require(os.fstat(self.handle.fileno()).st_size <= MAX_ARCHIVE, "archive exceeds size limit")
            self._check_raw_headers()
            self.archive = tarfile.open(fileobj=self.handle, mode="r:")
            members, seen = {}, set()
            for member in self.archive:
                require(len(members) < MAX_FILES + 2, "archive has too many entries")
                relative_path(member.name)
                require(member.name not in seen and member.name.casefold() not in {x.casefold() for x in seen},
                        "duplicate archive entry")
                require(member.type == tarfile.REGTYPE and not member.linkname and not member.pax_headers,
                        "archive contains a link, special file or extended header")
                require(member.mode in {0o644, 0o755} and member.uid == 0 and member.gid == 0,
                        "archive metadata is not normalized")
                limit = MAX_MANIFEST if member.name == "manifest.json" else MAX_FILE
                require(0 <= member.size <= limit, "archive member exceeds limit")
                members[member.name] = member
                seen.add(member.name)
            require("manifest.json" in members and "manifest.sig" in members, "signed manifest missing")
            require(members["manifest.sig"].size == 64, "invalid signature size")
            self.manifest_bytes = self.archive.extractfile(members["manifest.json"]).read(MAX_MANIFEST + 1)
            self.signature = self.archive.extractfile(members["manifest.sig"]).read(65)
            public = trusted_public(self.manifest_bytes, public)
            Sodium().verify(self.manifest_bytes, self.signature, public)
            self.manifest = validate_manifest(decode(self.manifest_bytes))
            require(self.manifest["key_id"] == digest(public), "manifest key id does not match trusted key")
            expected = {"manifest.json", "manifest.sig"} | {"payload/" + x["path"] for x in self.manifest["files"]}
            require(set(members) == expected, "archive and manifest file inventory differ")
            for item in self.manifest["files"]:
                member = members["payload/" + item["path"]]
                require(member.size == item["size"] and member.mode == item["mode"], "payload metadata mismatch")
                h = hashlib.sha256()
                with self.archive.extractfile(member) as stream:
                    prefix = stream.read(20)
                    h.update(prefix)
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(block)
                require(h.hexdigest() == item["sha256"], "payload hash rejected: " + item["path"])
                require(not prefix.startswith(b"\x7fELF"), "native binaries are excluded from this scoped extension")
            self.members = members
        except BaseException:
            self.handle.close()
            raise

    def _check_raw_headers(self):
        """Reject hidden GNU/PAX headers as well as sparse/compressed archives."""
        length = os.fstat(self.handle.fileno()).st_size
        require(length % 512 == 0, "truncated tar archive")
        offset, entries = 0, 0
        while offset < length:
            self.handle.seek(offset)
            header = self.handle.read(512)
            if header == bytes(512):
                require(self.handle.read(512) == bytes(512), "tar terminator incomplete")
                for padding in iter(lambda: self.handle.read(1024 * 1024), b""):
                    require(not any(padding), "nonzero trailing archive data")
                self.handle.seek(0)
                return
            require(header[257:263] == b"ustar\x00", "only normalized USTAR archives are accepted")
            require(header[156:157] == b"0", "extended, link, sparse or special tar entry rejected")
            field = header[124:136].strip(b"\x00 ")
            require(field and all(48 <= x <= 55 for x in field), "invalid tar size encoding")
            size = int(field, 8)
            require(size <= MAX_FILE, "tar member exceeds file limit")
            entries += 1
            require(entries <= MAX_FILES + 2, "archive has too many raw entries")
            offset += 512 + ((size + 511) // 512) * 512
            require(offset <= length, "truncated tar member")
        raise OverlayError("tar terminator missing")

    def close(self):
        self.archive.close()
        self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def extract_to(self, destination):
        # No tar extraction API is called. Names/types/hash/size were already verified.
        for item in self.manifest["files"]:
            output = destination / item["path"]
            output.parent.mkdir(parents=True, exist_ok=True)
            with self.archive.extractfile(self.members["payload/" + item["path"]]) as stream:
                with open(output, "xb") as handle:
                    shutil.copyfileobj(stream, handle, 1024 * 1024)
                    handle.flush()
                    os.fsync(handle.fileno())
            output.chmod(item["mode"])
        atomic_write(destination / "manifest.json", self.manifest_bytes)
        atomic_write(destination / "manifest.sig", self.signature)


def fsync_directory(path):
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        # A filesystem with no directory-sync support must not be called power-loss safe.
        if exc.errno not in {22, 95}:
            raise


def atomic_write(path, data):
    ensure_no_links(path.parent)
    require(not path.is_symlink(), "refusing symlink destination")
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ensure_no_links(path):
    path = Path(path).absolute()
    for component in [path, *path.parents]:
        if component.exists() or component.is_symlink():
            require(not component.is_symlink(), "symlink in managed path: " + str(component))
            require(component.is_dir(), "non-directory in managed path: " + str(component))
    return path


def managed_root(card, create=False):
    card = ensure_no_links(Path(card))
    require(card.is_dir(), "card directory does not exist")
    root = card / "App" / "PSPMode"
    ensure_no_links(root)
    if create:
        root.mkdir(parents=True, exist_ok=True)
        ensure_no_links(root / "releases")
        (root / "releases").mkdir(exist_ok=True)
        ensure_no_links(root / "state")
        (root / "state").mkdir(exist_ok=True)
    return root


@contextlib.contextmanager
def locked(root):
    ensure_no_links(root)
    lock = root / ".package-lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise OverlayError("package operation already locked; inspect .package-lock before manual recovery") from exc
    try:
        yield
    finally:
        lock.rmdir()


def record_with_checksum(value):
    result = dict(value)
    result["checksum"] = digest(canonical(value))
    return result


def read_record(path):
    require(stat.S_ISREG(path.lstat().st_mode), "record must be a regular file")
    value = read_json(path)
    checksum = value.pop("checksum", None)
    require(isinstance(checksum, str) and checksum == digest(canonical(value)), "record checksum rejected")
    return value


def write_record(path, value):
    atomic_write(path, canonical(record_with_checksum(value)) + b"\n")


def current_record(root):
    path = root / "current.json"
    if not path.exists() and not path.is_symlink():
        return {"schema": 1, "generation": 0, "current_release": None, "previous_release": None}
    require(not path.is_symlink(), "symlink selector")
    return validate_selector(read_record(path))


def validate_selector(value):
    require(isinstance(value, dict), "selector must be an object")
    require(set(value) == {"schema", "generation", "current_release", "previous_release"}, "invalid selector fields")
    require(value["schema"] == 1 and type(value["generation"]) is int and value["generation"] >= 0,
            "invalid selector generation")
    for key in ("current_release", "previous_release"):
        if value[key] is not None:
            identifier(value[key], "selector release")
    return value


def verify_release(directory, public):
    ensure_no_links(directory)
    require(directory.is_dir(), "release does not exist")
    for reserved in ("manifest.json", "manifest.sig"):
        info = (directory / reserved).lstat()
        require(stat.S_ISREG(info.st_mode), "release manifest is not a regular file")
        require(info.st_size <= (MAX_MANIFEST if reserved == "manifest.json" else 64), "installed manifest/signature too large")
    manifest_bytes = (directory / "manifest.json").read_bytes()
    signature = (directory / "manifest.sig").read_bytes()
    public = trusted_public(manifest_bytes, public)
    Sodium().verify(manifest_bytes, signature, public)
    manifest = validate_manifest(decode(manifest_bytes))
    require(manifest["key_id"] == digest(public), "release key id rejected")
    expected = {x["path"] for x in manifest["files"]} | {"manifest.json", "manifest.sig"}
    actual = set()
    for path in directory.rglob("*"):
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), "link or special file in release")
        if stat.S_ISREG(info.st_mode):
            actual.add(path.relative_to(directory).as_posix())
    require(actual == expected, "installed release inventory differs from manifest")
    for item in manifest["files"]:
        path = directory / item["path"]
        require(path.stat().st_size == item["size"] and file_digest(path) == item["sha256"],
                "installed release hash rejected: " + item["path"])
        with open(path, "rb") as handle:
            require(handle.read(4) != b"\x7fELF", "native binary found in Python-only release")
    return manifest


def check_compatibility(manifest, profile, inventory, card, fixture=False, activating=False):
    validate_profile(profile)
    require(canonical(profile) == canonical(manifest["profile"]), "package profile differs from selected profile")
    if fixture:
        require(profile["execution_environment"] == "host-fixture", "--fixture cannot bypass a device profile")
        marker = Path(card) / ".spruce-host-fixture"
        require(marker.is_file() and not marker.is_symlink() and marker.read_bytes() == FIXTURE_MARKER,
                "explicit host-fixture card marker required")
        require(inventory.get("kind") == "host-fixture-inventory", "host-fixture inventory required")
    else:
        require(profile["execution_environment"] == "device", "host fixture requires explicit --fixture")
        require(inventory.get("kind") == "read-only-device-inventory", "real device inventory required")
        require(inventory.get("profile_id") == profile["id"] and inventory.get("source_profile_verified") is True,
                "installed spruce source profile is not verified")
        if activating:
            require(all(profile[x] for x in ("hardware_qualified", "runtime_verified", "source_use_verified")),
                    "device activation refused: runtime, hardware profile and source-use gates are unverified")
            evidence = inventory.get("qualification", {})
            require(all(evidence.get(x) is True for x in ("classic_fallback", "internal_restore", "source_use_cleared")),
                    "device qualification evidence is incomplete")
    device = inventory.get("device", {})
    require(device.get("model") == profile["model"], "model mismatch or unknown device model")
    require(device.get("architecture") == profile["architecture"], "architecture mismatch or unknown device architecture")
    require(device.get("firmware") in profile["firmware_versions"], "firmware mismatch or unknown firmware")
    require(device.get("base_commit") == profile["base_commit"], "spruceOS source baseline mismatch or unknown")
    require(device.get("pyui_git_tree") == profile["pyui_git_tree"], "PyUI source snapshot mismatch or unknown")
    for name, expected in profile["baseline_files"].items():
        path = Path(card) / name
        ensure_no_links(path.parent)
        require(path.is_file() and not path.is_symlink(), "spruce baseline contract missing: " + name)
        actual = file_digest(path) if len(expected) == 64 else git_blob_digest(path)
        require(actual == expected, "spruce baseline contract changed: " + name)


def create_archive(source, output, secret_path, public_path, profile, release_id, kind,
                   source_date_epoch=PLAN_SOURCE_DATE_EPOCH, security_epoch=0, data_schema_epoch=0):
    source = ensure_no_links(Path(source))
    require(source.is_dir(), "payload source must be a directory")
    output = Path(output).absolute()
    require(not output.exists(), "output already exists")
    secret_file = Path(secret_path).resolve()
    require(source != secret_file and source not in secret_file.parents, "private key must stay outside payload source")
    require(not any((parent / ".git").exists() for parent in secret_file.parents), "private key must stay outside repositories")
    public, secret = load_key(public_path, 32), load_key(secret_path, 64)
    records = []
    for path in sorted(source.rglob("*"), key=lambda candidate: candidate.relative_to(source).as_posix()):
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), "payload links/special files forbidden")
        if stat.S_ISDIR(info.st_mode):
            continue
        name = relative_path(path.relative_to(source).as_posix())
        require(info.st_size <= MAX_FILE, "payload file exceeds limit")
        records.append({"path": name, "size": info.st_size, "sha256": file_digest(path),
                        "mode": 0o755 if info.st_mode & 0o111 else 0o644})
    manifest = validate_manifest({"schema": 1, "release_id": release_id, "kind": kind,
                                  "source_date_epoch": source_date_epoch, "security_epoch": security_epoch,
                                  "data_schema_epoch": data_schema_epoch, "key_id": digest(public),
                                  "license": ("GPL-2.0-only AND MIT AND OFL-1.1" if any(
                                      row["path"].startswith(("app/retropass/", "notices/RetroPass-source/"))
                                      for row in records) else "MIT-project-code-only"),
                                  "profile": validate_profile(profile),
                                  "files": records})
    raw = canonical(manifest) + b"\n"
    signature = Sodium().sign(raw, secret)
    Sodium().verify(raw, signature, public)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".overlay-", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            with tarfile.open(fileobj=handle, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                def add(name, data, mode):
                    item = tarfile.TarInfo(name)
                    item.size, item.mode, item.mtime = len(data), mode, source_date_epoch
                    item.uid = item.gid = 0
                    item.uname = item.gname = ""
                    archive.addfile(item, io.BytesIO(data))
                add("manifest.json", raw, 0o644)
                add("manifest.sig", signature, 0o644)
                for item in records:
                    data = (source / item["path"]).read_bytes()
                    require(len(data) == item["size"] and digest(data) == item["sha256"], "payload changed during creation")
                    add("payload/" + item["path"], data, item["mode"])
            handle.flush()
            os.fsync(handle.fileno())
        with VerifiedArchive(temporary, public):
            pass
        # O_EXCL works on FAT/exFAT too; a partial copy is rejected by verify.
        output_fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(output_fd, "wb") as result, open(temporary, "rb") as prepared:
            shutil.copyfileobj(prepared, result, 1024 * 1024)
            result.flush()
            os.fsync(result.fileno())
        fsync_directory(output.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return manifest


def stage_archive(archive_path, public, card, profile, inventory, fixture=False):
    # Complete authentication and hash validation before any managed directory is created.
    with VerifiedArchive(archive_path, public) as archive:
        manifest = archive.manifest
        check_compatibility(manifest, profile, inventory, card, fixture)
        needed = sum(x["size"] for x in manifest["files"]) + len(archive.manifest_bytes) + RESERVE_BYTES
        require(shutil.disk_usage(card).free >= needed, "not enough free space (includes recovery reserve)")
        root = managed_root(card, create=True)
        with locked(root):
            destination = root / "releases" / manifest["release_id"]
            require(not destination.exists() and not destination.is_symlink(), "release already exists; releases are immutable")
            temporary = Path(tempfile.mkdtemp(prefix=".staging-", dir=root / "releases"))
            try:
                archive.extract_to(temporary)
                verify_release(temporary, public)
                os.rename(temporary, destination)
                fsync_directory(destination.parent)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        return manifest


def activate_release(card, release_id, public, profile, inventory, fixture=False,
                     allow_downgrade=False):
    identifier(release_id, "release id")
    root = managed_root(card)
    with locked(root):
        state = root / "state"
        ensure_no_links(state)
        require(not (state / "activation.pending.json").exists(), "unfinished activation exists; rollback first")
        manifest = verify_release(root / "releases" / release_id, public)
        check_compatibility(manifest, profile, inventory, card, fixture, activating=True)
        require(shutil.disk_usage(card).free >= RESERVE_BYTES, "not enough free space for activation/recovery")
        before = current_record(state)
        require(before["current_release"] != release_id, "release is already selected")
        if before["current_release"]:
            prior = verify_release(root / "releases" / before["current_release"], public)
            downgrade = any(manifest[key] < prior[key] for key in ("security_epoch", "data_schema_epoch", "source_date_epoch"))
            require(not downgrade or allow_downgrade, "security/data-schema downgrade requires explicit --allow-downgrade")
        pending = {"schema": 1, "phase": "prepared", "release_id": release_id, "before": before,
                   "manifest_sha256": file_digest(root / "releases" / release_id / "manifest.json")}
        write_record(state / "activation.pending.json", pending)
        if before["current_release"] is not None:
            write_record(state / "current.last-good.json", before)
        after = {"schema": 1, "generation": before["generation"] + 1, "current_release": release_id,
                 "previous_release": before["current_release"]}
        write_record(state / "current.json", after)
        pending["phase"] = "selected-awaiting-health"
        write_record(state / "activation.pending.json", pending)
        return after


def confirm_health(card, public, evidence):
    root = managed_root(card)
    with locked(root):
        state = root / "state"
        ensure_no_links(state)
        pending = read_record(state / "activation.pending.json")
        current = current_record(state)
        release = current["current_release"]
        require(release == pending.get("release_id"), "current selector does not match activation")
        manifest = verify_release(root / "releases" / release, public)
        require(evidence.get("schema") == 1, "unsupported health receipt schema")
        require(file_digest(root / "releases" / release / "manifest.json") == pending["manifest_sha256"],
                "pending activation manifest changed")
        require(evidence.get("release_id") == release and evidence.get("manifest_sha256") == pending["manifest_sha256"],
                "health evidence belongs to a different release")
        checks = evidence.get("checks", {})
        require(all(checks.get(name) is True for name in ("first_frame", "input", "settings", "classic_fallback", "clean_exit")),
                "health evidence incomplete")
        require(evidence.get("profile_id") == manifest["profile"]["id"], "health evidence profile mismatch")
        require(isinstance(evidence.get("evidence_reference"), str) and 0 < len(evidence["evidence_reference"]) <= 512,
                "health evidence reference required")
        atomic_write(state / "package-health.last-good.json", canonical(evidence) + b"\n")
        write_record(state / "current.last-good.json", current)
        (state / "activation.pending.json").unlink()
        fsync_directory(state)
        return current


def rollback(card, public):
    root = managed_root(card)
    with locked(root):
        # Safe-mode marker is independent of graphics and remains until explicitly removed.
        state = root / "state"
        ensure_no_links(state)
        atomic_write(state / "force-classic", b"Offline rollback requested. Keep classic spruce until reviewed.\n")
        pending_path = state / "activation.pending.json"
        damaged_current = False
        try:
            before = current_record(state)
        except (OverlayError, OSError):
            damaged_current = True
            if pending_path.exists():
                before = validate_selector(read_record(pending_path).get("before", {}))
            else:
                before = validate_selector(read_record(state / "current.last-good.json"))
        if pending_path.exists():
            pending = read_record(pending_path)
            prior = pending.get("before")
            validate_selector(prior)
            target = prior.get("current_release")
        else:
            target = before["current_release"] if damaged_current else before["previous_release"]
        if target is not None:
            identifier(target, "rollback release")
            verify_release(root / "releases" / target, public)
        after = {"schema": 1, "generation": before["generation"] + 1,
                 "current_release": target, "previous_release": None}
        write_record(state / "current.json", after)
        if pending_path.exists():
            pending_path.unlink()
        fsync_directory(state)
        return after


def keygen(secret_path, public_path):
    secret_path, public_path = Path(secret_path).absolute(), Path(public_path).absolute()
    require(secret_path != public_path and not secret_path.exists() and not public_path.exists(), "key output already exists")
    for path in (secret_path, public_path):
        require(not any((parent / ".git").exists() for parent in path.parents), "signing key outputs must be outside repositories")
        require(path.parent.is_dir(), "key output parent must already exist")
    public, secret = Sodium().keypair()
    for path, value in ((secret_path, secret), (public_path, public)):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    return {"key_id": digest(public), "public_key": str(public_path), "private_key": str(secret_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("keygen", help="create local test keys outside repositories; use a managed signer for releases")
    p.add_argument("--private-key", required=True)
    p.add_argument("--public-key", required=True)
    p = sub.add_parser("create")
    p.add_argument("--source", required=True, help="prepared original app/assets/metadata/notices payload")
    p.add_argument("--output", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--public-key", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--release", required=True)
    p.add_argument("--kind", choices=("python-extension",), default="python-extension")
    p.add_argument("--source-date-epoch", type=int, default=int(os.environ.get("SOURCE_DATE_EPOCH", PLAN_SOURCE_DATE_EPOCH)))
    p.add_argument("--security-epoch", type=int, default=0)
    p.add_argument("--data-schema-epoch", type=int, default=0)
    p = sub.add_parser("verify")
    p.add_argument("archive")
    p.add_argument("--public-key", required=True)
    p = sub.add_parser("stage")
    p.add_argument("archive")
    for option in ("card", "public-key", "profile", "inventory"):
        p.add_argument("--" + option, required=True)
    p.add_argument("--fixture", action="store_true", help="only for a marked host sandbox and fixture profile")
    p = sub.add_parser("activate")
    p.add_argument("--release", required=True)
    for option in ("card", "public-key", "profile", "inventory"):
        p.add_argument("--" + option, required=True)
    p.add_argument("--fixture", action="store_true", help="cannot override device qualification gates")
    p.add_argument("--allow-downgrade", action="store_true")
    p = sub.add_parser("confirm-health")
    p.add_argument("--card", required=True)
    p.add_argument("--public-key", required=True)
    p.add_argument("--evidence", required=True)
    p = sub.add_parser("rollback")
    p.add_argument("--card", required=True)
    p.add_argument("--public-key", required=True)
    for child in sub.choices.values():
        if child.prog.split()[-1] != "keygen":
            child.add_argument("--trust-store", help="external reviewed active/retired/revoked key registry")
    args = parser.parse_args(argv)
    try:
        if args.command == "keygen":
            result = keygen(args.private_key, args.public_key)
        elif args.command == "create":
            load_trust_store(args.public_key, args.trust_store, signing=True)
            result = create_archive(args.source, args.output, args.private_key, args.public_key,
                                    read_json(args.profile), args.release, args.kind, args.source_date_epoch,
                                    args.security_epoch, args.data_schema_epoch)
        else:
            public = load_trust_store(args.public_key, args.trust_store)
            if args.command == "verify":
                with VerifiedArchive(args.archive, public) as archive:
                    result = archive.manifest
            elif args.command == "stage":
                result = stage_archive(args.archive, public, args.card, read_json(args.profile),
                                       read_json(args.inventory), args.fixture)
            elif args.command == "activate":
                result = activate_release(args.card, args.release, public, read_json(args.profile),
                                          read_json(args.inventory), args.fixture, args.allow_downgrade)
            elif args.command == "confirm-health":
                result = confirm_health(args.card, public, read_json(args.evidence))
            else:
                result = rollback(args.card, public)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OverlayError, OSError, tarfile.TarError, ctypes.ArgumentError, KeyError, TypeError) as exc:
        print("overlay: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
