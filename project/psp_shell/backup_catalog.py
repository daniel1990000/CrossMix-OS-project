# SPDX-License-Identifier: MIT
"""Names for existing offline recovery payloads, never an emulator save owner.

Only catalog metadata is writable. Payload inspection and new-directory restore
remain owned by the existing recovery tools. Historical checks are not proof
that the retained bytes still match, that all saves were included or that a
physical restore has succeeded.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import stat
import unicodedata
import uuid

from .settings import (MAX_FILE, MAX_GENERATION, SettingsError, _Transactions,
                       _directory, _encoded, _json_bytes, _locked, _read)


MAX_ENTRIES = 1000
SCOPES = {"card-files", "saves", "internal-files"}
DIGESTS = {"complete_sha256", "manifest_sha256", "readback_sha256"}


class BackupCatalogError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def require(condition, code, message):
    if not condition:
        raise BackupCatalogError(code, message)


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value, *, maximum, optional=False):
    require(isinstance(value, str), "INVALID_CATALOG", "A catalog label or note must be text.")
    value = unicodedata.normalize("NFC", value).strip()
    require((optional or bool(value)) and len(value) <= maximum and
            len(value.encode("utf-8")) <= maximum * 4 and
            not any(unicodedata.category(c).startswith("C") for c in value),
            "INVALID_CATALOG", "A catalog label or note is empty, too long or contains controls.")
    return value


def _path(value, *, check_links=True):
    require(isinstance(value, (str, Path)), "UNSAFE_CATALOG_PATH", "An explicit external path is required.")
    path = Path(value).absolute()
    require(".." not in path.parts and len(os.fsencode(path)) <= 4096 and
            not any(ord(c) < 32 or ord(c) == 127 for c in str(path)),
            "UNSAFE_CATALOG_PATH", "The catalog or payload path is invalid.")
    if check_links:
        for item in (*reversed(path.parents), path):
            require(not item.is_symlink(), "UNSAFE_CATALOG_PATH", "Catalog and payload paths cannot use symlinks.")
    return path


def _uuid(value):
    require(isinstance(value, str) and bool(re.fullmatch(r"[a-f0-9]{32}", value)),
            "INVALID_CATALOG", "A catalog entry ID is invalid.")
    return value


def _timestamp(value, optional=False):
    if optional and value is None:
        return None
    require(isinstance(value, str) and len(value) <= 40, "INVALID_CATALOG", "A catalog timestamp is invalid.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
                "INVALID_CATALOG", "Catalog timestamps must include UTC.")
    except (TypeError, ValueError, OverflowError) as error:
        raise BackupCatalogError("INVALID_CATALOG", "A catalog timestamp is invalid.") from error
    return value


class BackupCatalog:
    """Bounded external catalog with the existing single-target write journal.

    Constructing or reading this object creates no file or directory. Explicit
    registration/edits/recovery may create the selected catalog's parent and
    private lock/journal siblings, after containment checks.
    """

    def __init__(self, path, *, forbidden_roots=(), fault_hook=None):
        self.path = _path(path)
        self.forbidden_roots = tuple(_path(root) for root in forbidden_roots)
        self.lock_path = self.path.with_name("." + self.path.name + ".lock")
        self.journal_path = self.path.with_name("." + self.path.name + ".transactions")
        self.fault_hook = fault_hook
        self._external()

    def _external(self, payload=None):
        _path(self.path)
        roots = self.forbidden_roots + ((payload,) if payload is not None else ())
        for root in roots:
            require(not self.path.parent.is_relative_to(root), "UNSAFE_CATALOG_PATH",
                    "Catalog metadata must be outside inspected cards and backup payloads.")
        # A catalog placed inside an existing payload is invalid even before
        # there are registered entries from which to derive its location.
        for parent in self.path.parents:
            require(not ((parent / "manifest.json").exists() and
                         ((parent / "COMPLETE.json").exists() or (parent / "INCOMPLETE.json").exists())),
                    "UNSAFE_CATALOG_PATH", "Catalog metadata cannot be stored inside a backup payload.")

    def _validate(self, value):
        require(isinstance(value, dict) and set(value) == {"schema", "kind", "generation", "entries"} and
                type(value.get("schema")) is int and value["schema"] == 1 and value.get("kind") == "offline-backup-catalog" and
                type(value.get("generation")) is int and 0 <= value["generation"] <= MAX_GENERATION and
                isinstance(value.get("entries"), list) and len(value["entries"]) <= MAX_ENTRIES,
                "INVALID_CATALOG", "The backup catalog schema or bounds are invalid.")
        identifiers, identities, paths = set(), set(), set()
        fields = {"entry_id", "label", "note", "payload_path", "scope", "registered_at_utc",
                  "captured_at_utc", "digests", "bytes", "last_check", "last_verified_at_utc"}
        for row in value["entries"]:
            require(isinstance(row, dict) and set(row) == fields,
                    "INVALID_CATALOG", "A catalog entry has invalid fields.")
            identifier = _uuid(row["entry_id"])
            require(identifier not in identifiers, "INVALID_CATALOG", "Catalog entry IDs must be unique.")
            identifiers.add(identifier)
            for name, maximum in (("label", 80), ("note", 512)):
                require(row[name] == clean_text(row[name], maximum=maximum, optional=name == "note"),
                        "INVALID_CATALOG", "Catalog text must be normalized.")
            # A removed or replaced payload must remain listed for review.
            # Actual filesystem containment is checked again by the verifier.
            path = _path(row["payload_path"], check_links=False)
            require(str(path) == row["payload_path"], "INVALID_CATALOG", "Payload paths must be absolute.")
            self._external(path)
            require(isinstance(row["scope"], str) and row["scope"] in SCOPES and
                    type(row["bytes"]) is int and 0 <= row["bytes"] <= 2 * 1024**4,
                    "INVALID_CATALOG", "The payload scope or byte count is invalid.")
            digests = row["digests"]
            require(isinstance(digests, dict) and set(digests) == DIGESTS and
                    all(isinstance(v, str) and re.fullmatch(r"[a-f0-9]{64}", v) for v in digests.values()),
                    "INVALID_CATALOG", "The payload identity is invalid.")
            identity = tuple(sorted(digests.items()))
            require(identity not in identities and str(path) not in paths,
                    "INVALID_CATALOG", "Duplicate payload identities or locations are invalid.")
            identities.add(identity)
            paths.add(str(path))
            _timestamp(row["registered_at_utc"])
            _timestamp(row["captured_at_utc"])
            _timestamp(row["last_verified_at_utc"], optional=True)
            check = row["last_check"]
            if check is not None:
                require(isinstance(check, dict) and set(check) == {"status", "checked_at_utc", "reason"} and
                        isinstance(check["status"], str) and check["status"] in {"verified", "unavailable"} and isinstance(check["reason"], str) and
                        len(check["reason"]) <= 256,
                        "INVALID_CATALOG", "The historical verification record is invalid.")
                _timestamp(check["checked_at_utc"])
        return value

    def _load(self):
        self._external()
        if self.path.exists():
            info = self.path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                    "UNSAFE_CATALOG_PATH", "The catalog must be a single regular file.")
        raw = _read(self.path, optional=True)
        if raw is None:
            return {"schema": 1, "kind": "offline-backup-catalog", "generation": 0, "entries": []}, None
        require(len(raw) <= MAX_FILE, "INVALID_CATALOG", "The catalog exceeds its byte budget.")
        try:
            return self._validate(_json_bytes(raw)), raw
        except (SettingsError, TypeError, KeyError, OverflowError, RecursionError) as error:
            raise BackupCatalogError("INVALID_CATALOG", "The backup catalog is malformed; its bytes were preserved.") from error

    def _pending(self):
        if not self.journal_path.exists():
            return False
        _path(self.journal_path)
        journals = list(self.journal_path.glob("*.json"))
        require(len(journals) <= 8192, "CATALOG_RECOVERY_REQUIRED", "The catalog journal needs review.")
        for path in journals:
            value = _json_bytes(_read(path))
            require(isinstance(value.get("status"), str), "CATALOG_RECOVERY_REQUIRED", "A catalog journal is malformed and needs review.")
            if value.get("status") not in {"committed", "rolled_back"}:
                return True
        return False

    def read(self):
        require(not self._pending(), "CATALOG_RECOVERY_REQUIRED",
                "A catalog edit was interrupted. Use the catalog recover command before continuing.")
        value, _ = self._load()
        return copy.deepcopy(value)

    @staticmethod
    def _entry(value, entry_id):
        _uuid(entry_id)
        row = next((row for row in value["entries"] if row["entry_id"] == entry_id), None)
        require(row is not None, "BACKUP_NOT_FOUND", "This backup is no longer in the catalog.")
        return row

    def entry(self, entry_id):
        value = self.read()
        return copy.deepcopy(self._entry(value, entry_id)), value["generation"]

    def _transactions(self):
        def validate(value):
            require(value.get("operation") == "backup-catalog-edit" and value.get("resource") == str(self.path) and
                    len(value.get("files", [])) == 1 and value["files"][0]["path"] == str(self.path),
                    "INVALID_CATALOG", "A catalog journal refers to an unrelated target.")
            self._external()
        return _Transactions(self.journal_path, validate, fault_hook=self.fault_hook)

    def _mutate(self, expected_generation, operation):
        require(type(expected_generation) is int and 0 <= expected_generation < MAX_GENERATION,
                "INVALID_GENERATION", "A valid catalog generation is required.")
        self._external()
        _directory(self.path.parent)
        with _locked(self.lock_path):
            transactions = self._transactions()
            try:
                transactions.recover()
            except (TypeError, KeyError, RecursionError) as error:
                raise BackupCatalogError("CATALOG_RECOVERY_REQUIRED", "A catalog journal is malformed and needs review.") from error
            value, before = self._load()
            require(value["generation"] == expected_generation, "CATALOG_CHANGED",
                    "The catalog changed. Refresh before editing or verifying it.")
            result = operation(value)
            if result.get("unchanged"):
                return dict(result, generation=value["generation"])
            value["generation"] += 1
            self._validate(value)
            result = dict(result, generation=value["generation"])
            transaction_id = uuid.uuid4().hex
            transactions.commit(transaction_id, transaction_id, "backup-catalog-edit", str(self.path),
                                [(self.path, before, _encoded(value))], {}, result)
            return result

    def recover(self):
        self._external()
        require(self.journal_path.is_dir(), "CATALOG_RECOVERY_UNAVAILABLE", "There is no catalog journal to recover.")
        with _locked(self.lock_path):
            try:
                self._transactions().recover()
            except (TypeError, KeyError, RecursionError) as error:
                raise BackupCatalogError("CATALOG_RECOVERY_REQUIRED", "A catalog journal is malformed and needs review.") from error
        return self.read()

    def register(self, payload, label, *, note="", expected_generation=None):
        from tools.recovery_payload import inspect_payload
        payload = _path(payload)
        self._external(payload)
        label, note = clean_text(label, maximum=80), clean_text(note, maximum=512, optional=True)
        baseline = self.read()
        generation = baseline["generation"] if expected_generation is None else expected_generation
        manifest, digests, fresh = inspect_payload(payload)
        require(fresh["all_trees_match"] is True, "BACKUP_UNAVAILABLE", "The payload did not pass fresh readback.")
        timestamp = now_utc()
        row = {"entry_id": uuid.uuid4().hex, "label": label, "note": note,
               "payload_path": str(payload), "scope": manifest["scope"], "registered_at_utc": timestamp,
               "captured_at_utc": manifest["captured_at_utc"], "digests": digests,
               "bytes": manifest["source_tree"]["bytes"], "last_verified_at_utc": timestamp,
               "last_check": {"status": "verified", "checked_at_utc": timestamp,
                              "reason": "Payload bytes matched at registration; verify again before recovery."}}
        def add(value):
            for current in value["entries"]:
                if current["digests"] == digests:
                    return {"entry_id": current["entry_id"], "unchanged": True,
                            "same_location": current["payload_path"] == str(payload)}
                require(current["payload_path"] != str(payload), "PAYLOAD_IDENTITY_CHANGED",
                        "A different payload now occupies a registered location. The existing entry was preserved.")
            require(len(value["entries"]) < MAX_ENTRIES, "CATALOG_FULL", "The backup catalog is full.")
            value["entries"].append(row)
            return {"entry_id": row["entry_id"], "unchanged": False}
        return self._mutate(generation, add)

    def rename(self, entry_id, label, expected_generation, note=None):
        label = clean_text(label, maximum=80)
        if note is not None:
            note = clean_text(note, maximum=512, optional=True)
        def edit(value):
            row = self._entry(value, entry_id)
            row["label"] = label
            if note is not None:
                row["note"] = note
            return {"entry_id": entry_id}
        return self._mutate(expected_generation, edit)

    def remove(self, entry_id, expected_generation):
        def edit(value):
            self._entry(value, entry_id)
            value["entries"] = [row for row in value["entries"] if row["entry_id"] != entry_id]
            return {"entry_id": entry_id, "removed": True, "payload_deleted": False}
        return self._mutate(expected_generation, edit)

    def record_check(self, entry, generation, status, checked_at_utc, reason):
        require(status in {"verified", "unavailable"}, "INVALID_CHECK", "Only completed checks can be recorded.")
        _timestamp(checked_at_utc)
        def edit(value):
            row = self._entry(value, entry["entry_id"])
            require(row["digests"] == entry["digests"] and row["payload_path"] == entry["payload_path"],
                    "CATALOG_CHANGED", "This backup selection changed during verification.")
            row["last_check"] = {"status": status, "checked_at_utc": checked_at_utc, "reason": reason}
            if status == "verified":
                row["last_verified_at_utc"] = checked_at_utc
            return {"entry_id": entry["entry_id"]}
        return self._mutate(generation, edit)

    def restore(self, entry_id, output):
        from tools.recovery_payload import inspect_payload, restore
        output = _path(output)
        catalog = self.read()
        entry, generation = copy.deepcopy(self._entry(catalog, entry_id)), catalog["generation"]
        protected = (*self.forbidden_roots, self.journal_path,
                     *(_path(row["payload_path"], check_links=False) for row in catalog["entries"]))
        require(not any(output == root or output.is_relative_to(root) or root.is_relative_to(output)
                        for root in protected), "UNSAFE_RESTORE_OUTPUT",
                "The rehearsal output must be separate from inspected cards, catalog journals and every registered payload.")
        _, digests, _ = inspect_payload(entry["payload_path"])
        require(digests == entry["digests"], "PAYLOAD_IDENTITY_CHANGED", "The retained payload identity changed.")
        current, current_generation = self.entry(entry_id)
        require(generation == current_generation and current == entry,
                "CATALOG_CHANGED", "The backup selection changed before rehearsal.")
        result = restore(entry["payload_path"], output)
        require(result["inputs"] == entry["digests"], "PAYLOAD_IDENTITY_CHANGED",
                "The payload changed before rehearsal. Inspect the new output; no live data was overwritten.")
        return result


def public_entry(row):
    """UI data intentionally excludes private source/payload locations."""
    result = {key: copy.deepcopy(row[key]) for key in ("entry_id", "label", "note", "scope", "bytes",
              "captured_at_utc", "registered_at_utc", "last_check", "last_verified_at_utc")}
    check = row["last_check"]
    result["status"] = ("previously_verified" if check and check["status"] == "verified" else
                        "unavailable" if check else "unchecked")
    return result
