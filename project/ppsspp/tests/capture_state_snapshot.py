# SPDX-License-Identifier: MIT
"""Retain optional 0006 native-function fixture evidence outside Git."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import shutil
import time

from test_state_snapshot_patch import HERE, LOCK, POINTS, ROOT, SnapshotSourceTests
from test_state_session_patch import sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic_ns()
    records = []
    SnapshotSourceTests.setUpClass()
    try:
        case = SnapshotSourceTests()
        scenarios = ["success"]
        scenarios += ["kill-" + slot + "-" + point for point in POINTS for slot in ("same-slot", "separate-slot")]
        scenarios += ["fail-" + failure for failure in ("snapshot-write", "snapshot-corrupt", "source-change", "snapshot-fsync",
            "snapshot-directory-fsync", "result-rename", "completion-rename", "count-cap", "byte-cap", "entry-symlink",
            "entry-hardlink", "directory-mode")]
        for scenario in scenarios:
            record_started = time.monotonic_ns()
            record = case.scenario(scenario, retain=output / "raw")
            record["elapsed_ns"] = time.monotonic_ns() - record_started
            # Validate every retained raw byte against its original acquisition.
            for path, expected in record["artifacts"].items():
                retained = output / "raw" / scenario / path
                if sha(retained) != expected["sha256"] or retained.stat().st_size != expected["size"]:
                    raise AssertionError("Retained snapshot evidence differs: " + str(retained))
            record["retained_raw_verified"] = True
            records.append(record)
        shutil.copy2(case.binary, output / "state-snapshot-fixture")
        shutil.copy2(case.work / "state-snapshot.cpp", output / "state-snapshot.cpp")
        lock = json.loads(LOCK.read_text())
        report = {"schema": 1, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "kind": "optional0006-native-function-host-fixture-interruption", "whole_emulator": False,
            "production_profile_constructed": False, "filesystem_power_loss_simulated": False,
            "prior_completion_preservation_acceptance": "PASS_NATIVE_FUNCTION_FIXTURE_SCOPE",
            "legacy_mutable_receipts_protected": False, "upstream_commit": lock["upstream_commit"],
            "patch_sha256": sha(ROOT / lock["patch"]["path"]), "lock_sha256": sha(LOCK),
            "compiled_fixture_sha256": sha(output / "state-snapshot-fixture"),
            "compiled_source_sha256": sha(output / "state-snapshot.cpp"),
            "harness_inputs": {name: sha(HERE / name) for name in ("test_state_snapshot_patch.py", "state_snapshot_main.cpp.in",
                "test_state_session_patch.py", "state_evidence_acceptance.cpp.in", "capture_state_snapshot.py")},
            "elapsed_ns": time.monotonic_ns() - started, "observations": records}
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    finally:
        SnapshotSourceTests.doClassCleanups()


if __name__ == "__main__":
    main()
