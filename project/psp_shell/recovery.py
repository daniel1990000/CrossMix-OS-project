# SPDX-License-Identifier: MIT
"""Present fresh readback from the existing backup verifier.

Payload selection is an injected operator decision, never a path accepted from
the UI or an inferred save directory. Byte consistency does not prove complete
save coverage, independent storage or physical recovery.
"""
from __future__ import annotations

from datetime import datetime, timezone
import copy
from collections import OrderedDict
from pathlib import Path
import threading
from types import MappingProxyType
import uuid


RECOVERY_GUIDE = (
    "Use the existing recovery_payload.py tools with stopped, offline source trees. "
    "Verify selected card-files, saves and internal-files backups separately. "
    "The restore command copies a verified payload into a NEW expendable directory; "
    "it refuses an existing destination. Inspect that rehearsal before following "
    "the device runbook for spare-card or internal-file recovery. Overlay Undo, "
    "whole-card recovery and firmware recovery are separate procedures. "
    "A matching readback alone does not prove complete save coverage, independent "
    "storage or a successful physical restore."
)


def unavailable_status(reason="No backup payloads have been selected for verification."):
    return {"status": "unavailable", "verified_at_utc": None, "scope": [],
            "reason": reason, "readbacks": [], "physical_restore_tested": False,
            "independent_media_verified": False,
            "supported_actions": [
                {"id": "recheck", "label": "Verify backup again", "available": False,
                 "description": "Select existing backup payloads through the trusted recovery setup first."},
                {"id": "recovery_guide", "label": "Recovery instructions", "available": True,
                 "description": RECOVERY_GUIDE},
                {"id": "support_export", "label": "Export support report", "available": True,
                 "description": "Export the existing redacted interface diagnostics."}]}


class BackupStatusAdapter:
    """Read selected existing payloads; never start a copy or restore from UI."""

    def __init__(self, payloads):
        if (not isinstance(payloads, dict) or set(payloads) - {"card-files", "saves", "internal-files"}
                or any(not isinstance(value, (str, Path)) for value in payloads.values())):
            raise ValueError("Backup selection requires fixed scope-to-payload paths")
        self.payloads = MappingProxyType({key: Path(value).absolute() for key, value in payloads.items()})

    def status(self):
        result = unavailable_status()
        if not self.payloads:
            return result
        # Both modules are the existing recovery tools, packaged without a new
        # restore authority. Every status call checks actual retained bytes.
        from tools.recovery_payload import inspect_payload
        readbacks = []
        for scope, path in sorted(self.payloads.items()):
            try:
                manifest, receipts, fresh = inspect_payload(path)
                if manifest.get("scope") != scope or fresh.get("all_trees_match") is not True:
                    raise ValueError("Selected scope does not match the verified payload")
                readbacks.append({"scope": scope, "status": "verified",
                                  "manifest_sha256": receipts["manifest_sha256"],
                                  "verified_at_utc": datetime.now(timezone.utc).isoformat(),
                                  "bytes": manifest["source_tree"]["bytes"]})
            except (OSError, ValueError, TypeError, KeyError):
                # Do not expose private payload/source paths in diagnostics.
                readbacks.append({"scope": scope, "status": "unavailable", "verified_at_utc": None,
                                  "reason": "Payload is missing, incomplete, changed or does not match its selected scope."})
        verified = [row for row in readbacks if row["status"] == "verified"]
        result.update(status="verified" if len(verified) == len(readbacks) else "partial" if verified else "unavailable",
                      verified_at_utc=min((row["verified_at_utc"] for row in verified), default=None),
                      scope=[row["scope"] for row in verified], readbacks=readbacks,
                      reason=("Fresh payload bytes match their manifests for the selected scopes. "
                              "Coverage, independent storage and physical recovery still require review."
                              if len(verified) == len(readbacks) else
                              "Some selected backup payloads could not be verified. Review each scope before recovery."))
        result["supported_actions"][0].update(available=True, description="Read existing payloads again without changing them.")
        return result


class _VerificationCancelled(Exception):
    pass


class BackupHistoryAdapter:
    """Nonblocking presentation of one explicitly selected external catalog.

    Only the read-only verifier runs in a worker; its completion writes a
    catalog receipt, never payload data. Quiesce before a native handoff. A
    cancellation request is cooperative between files/hash chunks and does
    not promise a deadline for an unresponsive kernel/filesystem operation.
    """

    def __init__(self, catalog_path, *, forbidden_roots=()):
        from .backup_catalog import BackupCatalog
        self.catalog = BackupCatalog(catalog_path, forbidden_roots=forbidden_roots)
        self._lock = threading.RLock()
        self._jobs = OrderedDict()
        self._thread = None
        self._cancel = None
        self._active = None
        self._closed = False
        self._paused = False

    def history(self):
        from .backup_catalog import public_entry
        value = self.catalog.read()
        return {"schema": 1, "generation": value["generation"],
                "entries": [public_entry(row) for row in reversed(value["entries"])],
                "available": self.catalog.path.exists(),
                "reason": "Checks shown here are historical. Verify a selected backup again before recovery." if value["entries"] else
                          "No backups are registered. Use the backup catalog command to register an existing offline payload."}

    def status(self):
        result = unavailable_status()
        history = self.history()
        result.update(history_available=True, catalog_generation=history["generation"],
                      entry_count=len(history["entries"]), status="history" if history["entries"] else "unavailable",
                      reason=history["reason"])
        result["supported_actions"].insert(0, {"id": "history", "label": "Backup history", "available": True,
            "description": "Inspect named offline backups and their historical checks."})
        # status() never hashes storage; explicit selection starts verification.
        return result

    def detail(self, entry_id):
        from .backup_catalog import public_entry
        row, generation = self.catalog.entry(entry_id)
        return dict(public_entry(row), generation=generation, physical_restore_tested=False,
                    independent_media_verified=False)

    def rename(self, entry_id, label, expected_generation, note=None):
        self.catalog.rename(entry_id, label, expected_generation, note)
        return self.detail(entry_id)

    def remove(self, entry_id, expected_generation):
        return self.catalog.remove(entry_id, expected_generation)

    def verify(self, entry_id, expected_generation):
        from .backup_catalog import require
        entry, generation = self.catalog.entry(entry_id)
        require(type(expected_generation) is int and generation == expected_generation,
                "CATALOG_CHANGED", "Refresh the backup selection before verifying it.")
        with self._lock:
            # A timed-out handoff leaves the UI in place. Once its cancelled
            # worker really ends, a later explicit verification may resume;
            # close() remains irreversible.
            if self._paused and (self._thread is None or not self._thread.is_alive()):
                self._paused = False
            require(not self._closed and not self._paused, "BACKUP_BUSY", "Backup verification is closed or pausing for a handoff.")
            require(self._thread is None or not self._thread.is_alive(), "BACKUP_BUSY", "Another backup verification is still running.")
            job_id = uuid.uuid4().hex
            self._cancel = threading.Event()
            self._active = job_id
            self._jobs[job_id] = {"job_id": job_id, "entry_id": entry_id, "generation": generation,
                                  "state": "running", "phase": "starting", "bytes_checked": 0, "files_checked": 0}
            while len(self._jobs) > 8:
                self._jobs.popitem(last=False)
            self._thread = threading.Thread(target=self._verify, args=(job_id, entry, generation, self._cancel),
                                            name="offline-backup-verification", daemon=True)
            self._thread.start()
            return copy.deepcopy(self._jobs[job_id])

    def _verify(self, job_id, entry, generation, cancelled):
        from .backup_catalog import BackupCatalogError, _path, now_utc, require
        from tools.recovery_payload import inspect_payload

        def progress(phase, byte_count, file_count):
            if cancelled.is_set():
                raise _VerificationCancelled()
            with self._lock:
                job = self._jobs[job_id]
                job.update(phase=phase, bytes_checked=max(job["bytes_checked"], byte_count),
                           files_checked=max(job["files_checked"], file_count))

        try:
            _path(entry["payload_path"])
            manifest, digests, fresh = inspect_payload(entry["payload_path"], progress=progress)
            progress("complete", manifest["source_tree"]["bytes"], len([row for row in manifest["source_tree"]["entries"] if row["type"] == "file"]))
            require(digests == entry["digests"] and manifest["scope"] == entry["scope"] and fresh["all_trees_match"],
                    "PAYLOAD_IDENTITY_CHANGED", "The retained payload identity changed.")
            status, reason = "verified", "Selected payload bytes match their registered identity. Physical recovery and coverage remain unverified."
        except _VerificationCancelled:
            with self._lock:
                self._jobs[job_id].update(state="cancelled", phase="cancelled", reason="Verification cancelled; no new check was recorded.")
            return
        except (OSError, ValueError, TypeError, KeyError):
            status, reason = "unavailable", "The payload is missing, changed, incomplete or could not be read. Its original data was not changed."
        except Exception:
            with self._lock:
                self._jobs[job_id].update(state="unavailable", phase="complete",
                    reason="Verification could not complete. No successful check was recorded.")
            return
        try:
            # Once receipt publication starts it is a tiny metadata transaction,
            # not a cancellable hash. Do not hold the UI lock during filesystem
            # writes, and never acknowledge a cancellation after this boundary.
            with self._lock:
                if cancelled.is_set():
                    self._jobs[job_id].update(state="cancelled", phase="cancelled", reason="Verification cancelled; no new check was recorded.")
                    return
                self._jobs[job_id].update(phase="recording", cancellable=False)
                checked = now_utc()
            result = self.catalog.record_check(entry, generation, status, checked, reason)
            with self._lock:
                self._jobs[job_id].update(state=status, phase="complete", checked_at_utc=checked, reason=reason,
                                          catalog_generation=result["generation"])
        except (BackupCatalogError, OSError, ValueError) as error:
            with self._lock:
                self._jobs[job_id].update(state="superseded", phase="complete",
                    reason="The catalog changed or the check could not be recorded. Refresh and verify again.")
        except Exception:
            # Catalog write failures are not evidence of a successful check.
            with self._lock:
                self._jobs[job_id].update(state="unavailable", phase="complete",
                    reason="The verification result could not be retained. Review catalog storage before trying again.")

    def job(self, job_id):
        from .backup_catalog import require
        with self._lock:
            require(isinstance(job_id, str) and job_id in self._jobs, "BACKUP_JOB_NOT_FOUND", "This verification job is no longer available.")
            return copy.deepcopy(self._jobs[job_id])

    def cancel(self, job_id):
        with self._lock:
            result = self.job(job_id)
            if result["state"] == "running" and result.get("cancellable", True) and job_id == self._active:
                self._cancel.set()
                self._jobs[job_id]["cancel_requested"] = True
            return self.job(job_id)

    def quiesce(self, timeout=5):
        from .backup_catalog import require
        with self._lock:
            self._paused = True
            thread = self._thread
            if thread is not None and thread.is_alive():
                self._cancel.set()
        if thread is not None:
            thread.join(timeout)
            require(not thread.is_alive(), "BACKUP_BUSY", "Backup verification has not stopped; wait before handing off the interface.")
        with self._lock:
            self._paused = False

    def close(self):
        with self._lock:
            self._closed = True
        self.quiesce()
