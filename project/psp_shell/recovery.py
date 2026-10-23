# SPDX-License-Identifier: MIT
"""Present fresh readback from the existing backup verifier.

Payload selection is an injected operator decision, never a path accepted from
the UI or an inferred save directory. Byte consistency does not prove complete
save coverage, independent storage or physical recovery.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType


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
