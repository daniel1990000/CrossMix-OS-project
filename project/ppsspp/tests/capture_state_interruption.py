# SPDX-License-Identifier: MIT
"""Retain narrow native-function interruption diagnostics outside Git.

Run with PPSSPP_SOURCE_ROOT and PYTHONPATH=project:project/ppsspp/tests.
The unmodified patched-function harness uses explicit serializer/platform
fixtures and test-only syscall stop points. This does not execute PPSSPPSDL,
qualify a profile or simulate filesystem power-loss durability.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time

from test_state_session_patch import HERE, StateSessionSourceTests, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic_ns()
    records = []
    StateSessionSourceTests.setUpClass()
    try:
        case = StateSessionSourceTests()
        for point in ("state-before-rename", "completion-before-rename", "completion-after-rename",
                      "result-partial-write", "result-before-rename"):
            for same_slot in (False, True):
                record_started = time.monotonic_ns()
                record = case.interrupt(point, same_slot=same_slot, retain=output / "raw")
                record["elapsed_ns"] = time.monotonic_ns() - record_started
                records.append(record)
        shutil.copy2(case.binary, output / "state-session-fixture")
        shutil.copy2(case.work / "state-session.cpp", output / "state-session.cpp")
        files = ("test_state_session_patch.py", "state_session_main.cpp.in", "state_evidence_acceptance.cpp.in", "capture_state_interruption.py")
        report = {"schema": 1, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                  "kind": "native-function-host-fixture-interruption-diagnostic",
                  "upstream_commit": "d357e6a32934800d3d80b49f910a603e1b069751",
                  "whole_emulator": False, "production_profile_constructed": False,
                  "filesystem_power_loss_simulated": False,
                  "prior_completion_preservation_acceptance": "UNMET",
                  "finding": "Interrupted publication can lose prior completion receipt; same-slot replacement can invalidate prior state path/hash. Future receipt remains rejected.",
                  "input_files": {name: sha(HERE / name) for name in files},
                  "compiled_fixture_sha256": sha(output / "state-session-fixture"),
                  "compiled_source_sha256": sha(output / "state-session.cpp"),
                  "elapsed_ns": time.monotonic_ns() - started, "observations": records}
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    finally:
        StateSessionSourceTests.doClassCleanups()


if __name__ == "__main__":
    main()
