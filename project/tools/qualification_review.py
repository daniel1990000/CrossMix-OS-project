#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Review existing operator casebooks; produce proposals, never qualification.

Structured observations are bounded JSON notes in device_acceptance's existing
append-only attempt chain. Raw artifacts remain private external files. No
device, source, game, profile or executable is opened for activation.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import device_acceptance as recorder

PROJECT = TOOLS.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from bridge.principal_integration import REQUIRED_PROJECT_MODULES, SOURCE_BLOBS
from psp_shell.runtime import SPRUCE_COMMIT

DEFAULT_PLAN = PROJECT / "evidence/device-acceptance-plan.json"
PYUI_TREE = "4d0bdb3111d9226fbacbea6c89d65e540620e21e"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
BOOT = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
MAX_RAW_BYTES = 512 * 1024 * 1024
MAX_TOTAL_RAW_BYTES = 4 * 1024 * 1024 * 1024
MAX_FILES = 4096
PROVENANCES = {"physical_operator", "host_fixture", "static_snapshot"}
TEST_CASES = {"cold_boot": "boot", "appearance_switch": "appearance",
              "launch_quit": "launch_return", "sleep_wake": "power_sleep",
              "state_resume": "save_resume", "native_engine": "native_controls"}
GENERIC_SCOPES = {
    "restore": {"card_restore", "overlay_restore", "internal_restore", "retained_readback"},
    "boot": {"early_failure_recovery"},
    "input": {"built_in_input", "external_input", "held_keys"},
    "library": {"library_identity", "favorites_recents", "advanced_routes"},
    "launch_return": {"launch_failure", "foreground_ownership", "resource_return"},
    "save_resume": {"battery_save", "stopped_writers", "save_readback"},
    "native_controls": {"native_controls", "gameplay_unchanged", "per_game_overrides"},
    "appearance": {"physical_panel", "accessibility", "visual_exceptions"},
    "settings": {"settings_authority", "settings_undo", "writer_ownership"},
    "power_sleep": {"low_battery", "poweroff_authority"},
    "usb": {"usb_unmount", "usb_return", "usb_staging_failure"},
    "storage_updates": {"storage_faults", "update_rollback", "newer_save_preservation"},
    "ports": {"port_launch_exit", "port_input", "port_save", "port_performance", "port_uninstall"},
}
TEST_SCOPES = {
    "cold_boot": {"cold_boot"}, "appearance_switch": {"appearance_switch"},
    "launch_quit": {"launch_quit", "foreground_ownership"}, "sleep_wake": {"sleep_wake"},
    "state_resume": {"state_write_completed", "state_load_ack", "replay_rejection", "reboot_fallback", "config_changes"},
    "native_engine": {"corresponding_source", "native_appearance", "native_performance", "native_recovery", "save_compatibility"},
}
RAW_SCOPES = set().union(*GENERIC_SCOPES.values(), *TEST_SCOPES.values(),
                        {"candidate_package", "candidate_source_inventory", "candidate_descriptor", "reviewer_statement"})


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), "invalid " + label + " fields")


def relative(value):
    require(type(value) is str and 0 < len(value) <= 192 and "\\" not in value and
            not PurePosixPath(value).is_absolute() and
            all(part not in {"", ".", ".."} for part in value.split("/")) and
            not any(ord(char) < 32 for char in value), "invalid private evidence path")
    return value


def optional_hash(value, pattern=DIGEST):
    return value is None or type(value) is str and pattern.fullmatch(value) is not None


def stamp(value):
    require(type(value) is str and 0 < len(value) <= 40, "invalid observation time")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None and result.utcoffset().total_seconds() == 0,
            "observation times must explicitly use UTC")
    return result


def required_installed_paths():
    return set(SOURCE_BLOBS) | {"App/PSPMode/integration/" + name for name in REQUIRED_PROJECT_MODULES}


def template(session):
    """Declare unknowns from the retained expected profile; do not infer a build."""
    with recorder.locked(session) as locked:
        identity, profile = recorder.manifest(locked)
        return {"schema": 1, "kind": "tg5040-qualification-review-scope", "session_id": identity["session_id"],
                "profile_sha256": identity["profile_sha256"],
                "candidate": {"frontend_commit": None, "source_inventory_sha256": None,
                              "release_descriptor_sha256": None, "package_sha256": None,
                              "signer_sha256": None, "base_commit": profile.get("base_commit"),
                              "pyui_tree": profile.get("pyui_git_tree"),
                              "installed_files": {name: None for name in sorted(required_installed_paths())}},
                "device": {"model": "TG5040", "firmware": None, "filesystem": None},
                "runtimes": [
                    {"id": "ppsspp", "engine": "ppsspp", "kind": "installed_engine",
                     "installed_path": "Emu/PSP/PPSSPPSDL_TrimUI", "binary_sha256": None,
                     "source_commit": None, "source_archive_sha256": None, "state_resume": False},
                    {"id": "retroarch", "engine": "retroarch", "kind": "installed_engine",
                     "installed_path": "RetroArch/ra64.universal", "binary_sha256": None,
                     "source_commit": None, "source_archive_sha256": None, "state_resume": False}],
                "identity_evidence": [], "save_policy": {},
                "excluded_features": {"native_candidates": "Installed engines retained for the core pilot.",
                                      "state_resume": "Enhanced state Resume is outside the core pilot.",
                                      "ports": "No showcase port selected for this candidate."},
                "omitted_runtimes": []}


def raw_reference(value):
    exact(value, ("path", "sha256", "scope"), "raw evidence")
    relative(value["path"])
    require(type(value["sha256"]) is str and DIGEST.fullmatch(value["sha256"]) is not None and
            type(value["scope"]) is str and value["scope"] in RAW_SCOPES, "invalid raw evidence identity/scope")


def validate_scope(value):
    exact(value, ("schema", "kind", "session_id", "profile_sha256", "candidate", "device", "runtimes",
                  "identity_evidence", "save_policy", "excluded_features", "omitted_runtimes"), "review scope")
    require(type(value["schema"]) is int and value["schema"] == 1 and
            value["kind"] == "tg5040-qualification-review-scope" and
            type(value["session_id"]) is str and re.fullmatch(r"[0-9a-f]{32}", value["session_id"]) and
            type(value["profile_sha256"]) is str and DIGEST.fullmatch(value["profile_sha256"]), "invalid review scope identity")
    candidate = value["candidate"]
    exact(candidate, ("frontend_commit", "source_inventory_sha256", "release_descriptor_sha256", "package_sha256",
                      "signer_sha256", "base_commit", "pyui_tree", "installed_files"), "candidate")
    require(optional_hash(candidate["frontend_commit"], COMMIT) and candidate["base_commit"] == SPRUCE_COMMIT and
            candidate["pyui_tree"] == PYUI_TREE and
            all(optional_hash(candidate[name]) for name in ("source_inventory_sha256", "release_descriptor_sha256",
                                                           "package_sha256", "signer_sha256")), "invalid or unpinned candidate identity")
    files = candidate["installed_files"]
    require(type(files) is dict and len(files) <= MAX_FILES, "invalid installed candidate inventory")
    for name, expected in files.items():
        relative(name)
        require(optional_hash(expected), "invalid installed file digest")
    exact(value["device"], ("model", "firmware", "filesystem"), "device scope")
    require(value["device"]["model"] == "TG5040" and all(item is None or type(item) is str and
            0 < len(item) <= 64 and not any(ord(c) < 32 for c in item)
            for item in (value["device"]["firmware"], value["device"]["filesystem"])), "invalid target identity")
    require(type(value["runtimes"]) is list and 0 < len(value["runtimes"]) <= 4, "select one to four explicit runtimes")
    names = set()
    for runtime in value["runtimes"]:
        exact(runtime, ("id", "engine", "kind", "installed_path", "binary_sha256", "source_commit",
                        "source_archive_sha256", "state_resume"), "runtime")
        require(type(runtime["id"]) is str and IDENTIFIER.fullmatch(runtime["id"]) and
                runtime["id"] not in names and runtime["id"] not in {"core", "classic", "psp", "classic_to_psp", "psp_to_classic"},
                "invalid or duplicate runtime context")
        names.add(runtime["id"])
        require(runtime["engine"] in {"ppsspp", "retroarch", "port"} and
                runtime["kind"] in {"installed_engine", "native_candidate", "port"} and
                (runtime["engine"] == "port") == (runtime["kind"] == "port") and
                optional_hash(runtime["binary_sha256"]) and optional_hash(runtime["source_commit"], COMMIT) and
                optional_hash(runtime["source_archive_sha256"]) and type(runtime["state_resume"]) is bool and
                not (runtime["kind"] == "port" and runtime["state_resume"]), "invalid runtime capability/identity")
        relative(runtime["installed_path"])
        require(runtime["installed_path"].split("/")[0] not in {"Roms", "Saves", "BIOS"}, "runtime inventory cannot select owner data")
    require(any(item["kind"] != "port" for item in value["runtimes"]), "a complete core casebook needs a selected emulator")
    require(type(value["identity_evidence"]) is list and len(value["identity_evidence"]) <= 3, "invalid candidate evidence")
    for item in value["identity_evidence"]:
        raw_reference(item)
        require(item["scope"] in {"candidate_package", "candidate_source_inventory", "candidate_descriptor"}, "invalid candidate evidence role")
    require(type(value["save_policy"]) is dict and len(value["save_policy"]) <= 64, "invalid selected-save policy")
    for name, policy in value["save_policy"].items():
        recorder.save_name(name)
        require(policy in {"unchanged", "gameplay_change_expected"}, "invalid selected-save policy")
    exclusions = value["excluded_features"]
    expected = {name for name, selected in (
        ("native_candidates", any(item["kind"] == "native_candidate" for item in value["runtimes"])),
        ("state_resume", any(item["state_resume"] for item in value["runtimes"])),
        ("ports", any(item["kind"] == "port" for item in value["runtimes"]))) if not selected}
    require(type(exclusions) is dict and set(exclusions) == expected and all(type(reason) is str and
            0 < len(reason.strip()) <= 256 for reason in exclusions.values()), "selected and excluded feature scopes disagree")
    require(type(value["omitted_runtimes"]) is list and len(value["omitted_runtimes"]) <= 16, "invalid omitted runtime scope")
    for item in value["omitted_runtimes"]:
        exact(item, ("id", "status", "reason"), "omitted runtime")
        require(type(item["id"]) is str and IDENTIFIER.fullmatch(item["id"]) and item["id"] not in names and
                item["status"] in {"excluded", "unsupported"} and type(item["reason"]) is str and
                0 < len(item["reason"].strip()) <= 256, "invalid omitted runtime")
        names.add(item["id"])
    return value


def scope_digest(scope):
    return recorder.digest(recorder.encoded(validate_scope(scope)))


def validate_observation(value, case, scope):
    exact(value, ("schema", "kind", "scope_sha256", "provenance", "test", "context", "cycle", "boot_id",
                  "started_at", "ended_at", "runtime_sha256", "runtime_source_commit", "raw", "state", "retest_of"), "observation")
    require(type(value["schema"]) is int and value["schema"] == 1 and
            value["kind"] == "qualification-observation" and value["scope_sha256"] == scope_digest(scope), "observation belongs to another candidate/scope")
    require(value["provenance"] in PROVENANCES and value["test"] in {*TEST_CASES, "case"} and
            (value["test"] == "case" or TEST_CASES[value["test"]] == case) and
            type(value["cycle"]) is int and 1 <= value["cycle"] <= 100 and
            type(value["boot_id"]) is str and BOOT.fullmatch(value["boot_id"]) and
            optional_hash(value["runtime_sha256"]) and optional_hash(value["runtime_source_commit"], COMMIT) and
            optional_hash(value["retest_of"]), "invalid observation cycle/provenance")
    require(stamp(value["started_at"]) < stamp(value["ended_at"]), "observation interval must have positive duration")
    runtimes = {item["id"]: item for item in scope["runtimes"]}
    context = value["context"]
    require(type(context) is str and context in {"core", "classic", "psp", "classic_to_psp", "psp_to_classic", *runtimes}, "unknown observation context")
    if context in runtimes:
        runtime = runtimes[context]
        require(value["runtime_sha256"] == runtime["binary_sha256"] and
                value["runtime_source_commit"] == runtime["source_commit"], "runtime/source identity differs from selected scope")
    else:
        require(value["runtime_sha256"] is None and value["runtime_source_commit"] is None, "UI context cannot claim a runtime identity")
    require(type(value["raw"]) is list and 0 < len(value["raw"]) <= 8, "observation needs bounded selected raw artifacts")
    seen = set()
    for item in value["raw"]:
        raw_reference(item)
        key = (item["path"], item["scope"])
        require(key not in seen, "duplicate raw evidence role")
        seen.add(key)
    if value["test"] == "state_resume":
        require(context in runtimes and runtimes[context]["state_resume"], "state Resume is not selected for this runtime")
        exact(value["state"], ("game_sha256", "state_sha256", "slot", "save_boot_id", "load_boot_id"), "state identity")
        state = value["state"]
        require(all(type(state[name]) is str and DIGEST.fullmatch(state[name]) for name in ("game_sha256", "state_sha256")) and
                type(state["slot"]) is int and 0 <= state["slot"] <= 9 and
                state["save_boot_id"] == state["load_boot_id"] == value["boot_id"], "state proof is not same-boot or lacks exact game/state identity")
    else:
        require(value["state"] is None, "non-state case cannot supply state authority")
    note = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    require(len(note) <= 2048, "structured observation exceeds the existing recorder note limit")
    return note


def _artifact(root, item, *, budget=None):
    raw_reference(item)
    directory = recorder.directory_fd(root)
    descriptor = None
    try:
        root_identity = os.fstat(directory)
        for part in PurePosixPath(item["path"]).parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        name = PurePosixPath(item["path"]).name
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_RAW_BYTES, "raw artifact is empty, special or over budget")
        if budget is not None:
            require(before.st_size <= budget[0], "selected evidence exceeds the aggregate hash budget")
            budget[0] -= before.st_size
        hashed, count = hashlib.sha256(), 0
        while count <= before.st_size:
            block = os.read(descriptor, min(65536, before.st_size + 1 - count))
            if not block:
                break
            count += len(block)
            hashed.update(block)
        after = os.fstat(descriptor)
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        require(count == before.st_size and all(getattr(before, key) == getattr(after, key) == getattr(named, key)
                for key in keys), "raw artifact changed while hashing")
        require(hashed.hexdigest() == item["sha256"], "raw artifact digest differs")
        check = recorder.directory_fd(root)
        try:
            current = os.fstat(check)
            require((current.st_dev, current.st_ino) == (root_identity.st_dev, root_identity.st_ino), "raw evidence root changed")
            for part in PurePosixPath(item["path"]).parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=check)
                os.close(check)
                check = child
            current_file = os.stat(name, dir_fd=check, follow_symlinks=False)
            require(all(getattr(before, key) == getattr(current_file, key) for key in keys),
                    "named raw artifact changed during hashing")
        finally:
            os.close(check)
        return count
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


def record_observation(session, scope, case, status, observation, evidence_root):
    """Append to the existing recorder; never create a parallel case history."""
    validate_scope(scope)
    require(case in recorder.CASES and status in {"pass", "fail", "blocked"}, "invalid recorder case/status")
    note = validate_observation(observation, case, scope)
    budget = [MAX_TOTAL_RAW_BYTES]
    for item in observation["raw"]:
        _artifact(evidence_root, item, budget=budget)
    with recorder.locked(session) as locked:
        identity, _ = recorder.manifest(locked)
        require(identity["session_id"] == scope["session_id"] and identity["profile_sha256"] == scope["profile_sha256"], "scope belongs to another session/profile")
    return recorder.record(session, case, status, note)


def source_inventory_identity(evidence_root, reference, candidate):
    """Reuse packaging's release-source.json contract and canonical list digest.

    The inventory digest differs from the SHA-256 of the retained JSON file.
    Both identities are checked; changing one cannot relabel the other.
    """
    value, hashed = recorder.read_json(Path(evidence_root) / relative(reference["path"]))
    require(hashed == reference["sha256"], "source record changed after raw verification")
    exact(value, ("schema", "descriptor_sha256", "frontend", "source_inventory", "source_inventory_sha256"), "release-source record")
    exact(value["frontend"], ("commit", "working_tree_modified"), "frontend identity")
    require(type(value["schema"]) is int and value["schema"] == 1 and
            value["descriptor_sha256"] == candidate["release_descriptor_sha256"] and
            value["frontend"]["commit"] == candidate["frontend_commit"] and value["frontend"]["working_tree_modified"] is False,
            "release-source frontend/descriptor identity differs or source is modified")
    rows = value["source_inventory"]
    require(type(rows) is list and 0 < len(rows) <= MAX_FILES, "invalid original-source inventory")
    files = {}
    for item in rows:
        exact(item, ("path", "size", "sha256"), "source inventory row")
        relative(item["path"])
        require(item["path"] not in files and type(item["size"]) is int and 0 <= item["size"] <= MAX_RAW_BYTES and
                type(item["sha256"]) is str and DIGEST.fullmatch(item["sha256"]), "invalid or duplicate source inventory identity")
        files[item["path"]] = item["sha256"]
    require([item["path"] for item in rows] == sorted(files), "source inventory must retain packaging's sorted order")
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    digest = hashlib.sha256(canonical).hexdigest()
    require(value["source_inventory_sha256"] == candidate["source_inventory_sha256"] == digest,
            "canonical source inventory digest differs")
    require(files.get("packaging/current-release.json") == candidate["release_descriptor_sha256"],
            "original source inventory omits its selected release descriptor")
    prefix = "App/PSPMode/integration/app/"
    for name, expected in candidate["installed_files"].items():
        if name.startswith(prefix):
            require(files.get(name.removeprefix(prefix)) == expected, "installed original module differs from matching source inventory")
    return digest


def _requirements(scope):
    rows = []
    for case in recorder.CASES:
        if case in {"save_resume", "native_controls", "ports"}:
            contexts = [item["id"] for item in scope["runtimes"] if (item["kind"] == "port") == (case == "ports")]
        elif case == "input":
            contexts = ["classic", "psp"]
        else:
            contexts = ["core"]
        rows.extend((case, "case", context, 1, GENERIC_SCOPES[case]) for context in contexts)
    rows.extend(("boot", "cold_boot", context, 1, TEST_SCOPES["cold_boot"]) for context in ("classic", "psp"))
    rows.extend(("appearance", "appearance_switch", context, 10, TEST_SCOPES["appearance_switch"])
                for context in ("classic_to_psp", "psp_to_classic"))
    rows.extend(("launch_return", "launch_quit", item["id"], 20, TEST_SCOPES["launch_quit"]) for item in scope["runtimes"])
    rows.extend(("power_sleep", "sleep_wake", context, 10, TEST_SCOPES["sleep_wake"])
                for context in ["classic", "psp", *(item["id"] for item in scope["runtimes"])])
    for item in scope["runtimes"]:
        if item["kind"] == "native_candidate":
            rows.append(("native_controls", "native_engine", item["id"], 1, TEST_SCOPES["native_engine"]))
        if item["state_resume"]:
            rows.append(("save_resume", "state_resume", item["id"], 1, TEST_SCOPES["state_resume"]))
    return rows


def observation_template(scope, case, test, context, cycle=1):
    """Prepare an incomplete recorder note; placeholders are not observations."""
    validate_scope(scope)
    require(type(cycle) is int and 1 <= cycle <= 100, "invalid planned cycle")
    row = next((item for item in _requirements(scope) if item[:3] == (case, test, context)), None)
    require(row is not None, "planned observation is outside the selected casebook")
    runtime = next((item for item in scope["runtimes"] if item["id"] == context), None)
    return {"schema": 1, "kind": "qualification-observation", "scope_sha256": scope_digest(scope),
            "provenance": None, "test": test, "context": context, "cycle": cycle, "boot_id": None,
            "started_at": None, "ended_at": None,
            "runtime_sha256": runtime["binary_sha256"] if runtime else None,
            "runtime_source_commit": runtime["source_commit"] if runtime else None,
            "raw": [{"path": None, "sha256": None, "scope": role} for role in sorted(row[4])],
            "state": ({"game_sha256": None, "state_sha256": None, "slot": None,
                       "save_boot_id": None, "load_boot_id": None} if test == "state_resume" else None),
            "retest_of": None}


def _session_values(session):
    summary = recorder.report(session)
    with recorder.locked(session) as locked:
        identity, profile = recorder.manifest(locked)
        snapshots = {}
        for phase, expected in summary["snapshot_sha256"].items():
            value, hashed = recorder.snapshot_value(locked, identity, phase)
            require(hashed == expected, "acceptance snapshot changed during review")
            snapshots[phase] = value
        attempts = {}
        for case in recorder.CASES:
            rows = recorder.attempts(locked, identity, case)
            require(len(rows) == summary["cases"][case]["attempts"], "acceptance attempts changed during review")
            attempts[case] = rows
        return identity, profile, summary, snapshots, attempts


def review(session, scope, evidence_root, *, plan=DEFAULT_PLAN, reviewer=None):
    """Check recorded claims and artifacts; every resulting verdict is a proposal."""
    validate_scope(scope)
    plan_value, plan_hash = recorder.read_json(plan)
    require(type(plan_value.get("schema")) is int and plan_value.get("schema") == 1 and plan_value.get("kind") == "device-acceptance-review" and
            set(plan_value.get("cases", {})) == set(recorder.CASES) and
            plan_value.get("hardware_qualified") is False and plan_value.get("automatic_activation") is False,
            "acceptance plan case set or non-activation contract differs")
    identity, profile, summary, snapshots, attempts = _session_values(session)
    require(identity["session_id"] == scope["session_id"] and identity["profile_sha256"] == scope["profile_sha256"], "review scope belongs to another session/profile")
    issues = []
    def issue(code, **details):
        issues.append(dict(code=code, **details))
    candidate = scope["candidate"]
    for name in ("frontend_commit", "source_inventory_sha256", "release_descriptor_sha256", "package_sha256", "signer_sha256"):
        if candidate[name] is None:
            issue("missing_candidate_identity", field=name)
    required_files = required_installed_paths() | {item["installed_path"] for item in scope["runtimes"]}
    if not required_files.issubset(candidate["installed_files"]):
        issue("incomplete_expected_installed_inventory", count=len(required_files - set(candidate["installed_files"])))
    if any(value is None for value in candidate["installed_files"].values()):
        issue("unknown_expected_installed_hashes")
    for runtime in scope["runtimes"]:
        if runtime["binary_sha256"] is None or runtime["source_commit"] is None:
            issue("missing_runtime_identity", context=runtime["id"])
        if candidate["installed_files"].get(runtime["installed_path"]) != runtime["binary_sha256"]:
            issue("runtime_expected_inventory_mismatch", context=runtime["id"])
        if runtime["kind"] == "native_candidate" and runtime["source_archive_sha256"] is None:
            issue("missing_native_corresponding_source", context=runtime["id"])
    if any(scope["device"][name] is None for name in ("firmware", "filesystem")):
        issue("missing_device_support_matrix")
    physical_snapshots = len(snapshots) == 2
    if not summary["snapshots_complete"]:
        issue("missing_before_after_snapshots")
    for phase, snapshot in snapshots.items():
        observed = snapshot.get("inventory", {}).get("device", {})
        context = snapshot["capture_context"]
        physical_snapshots = physical_snapshots and context["root"]["path"] == "/" and context["sd_root"]["path"] == "/mnt/SDCARD"
        if (observed.get("model") != "trimui-smart-pro" or observed.get("architecture") != "aarch64" or
                observed.get("firmware") != scope["device"]["firmware"] or observed.get("base_commit") != candidate["base_commit"] or
                observed.get("pyui_git_tree") != candidate["pyui_tree"]):
            issue("observed_device_or_source_identity_mismatch", phase=phase)
        mounts = snapshot.get("inventory", {}).get("mounts", [])
        if not any(item.get("mountpoint") == "/mnt/SDCARD" and item.get("filesystem") == scope["device"]["filesystem"] for item in mounts):
            issue("observed_filesystem_missing_or_mismatched", phase=phase)
        actual = {item.get("path"): item.get("sha256") for item in snapshot.get("inventory", {}).get("baseline_contracts", [])}
        if any(expected is None or actual.get(name) != expected for name, expected in candidate["installed_files"].items()):
            issue("observed_candidate_inventory_incomplete_or_changed", phase=phase)
    save_summary = {"selected": 0, "missing": 0, "expected_gameplay_changes": 0, "unexpected_changes": 0,
                    "native_readback_review_required": True}
    if summary.get("save_comparison"):
        selected = {item["path"] for item in summary["save_comparison"]}
        save_summary["selected"] = len(selected)
        if selected != set(scope["save_policy"]):
            issue("selected_save_policy_missing_or_mismatched")
        for item in summary["save_comparison"]:
            if item.get("missing") is True:
                save_summary["missing"] += 1
                issue("selected_battery_save_missing")
            elif item.get("unchanged") is not True:
                if scope["save_policy"].get(item["path"]) == "gameplay_change_expected":
                    save_summary["expected_gameplay_changes"] += 1
                else:
                    save_summary["unexpected_changes"] += 1
                    issue("unexpected_battery_save_change")
            elif scope["save_policy"].get(item["path"]) == "gameplay_change_expected":
                issue("expected_gameplay_save_change_not_observed")
    else:
        issue("no_selected_battery_save_readback")
    budget, raw_cache, raw_failed = [MAX_TOTAL_RAW_BYTES], {}, set()
    def artifact(item):
        key = (item["path"], item["sha256"])
        require(key not in raw_failed, "previously inconsistent raw artifact")
        if key not in raw_cache:
            try:
                _artifact(evidence_root, item, budget=budget)
            except (OSError, ValueError):
                raw_failed.add(key)
                raise
            raw_cache[key] = item
    identity_refs = {}
    for item in scope["identity_evidence"]:
        try:
            artifact(item)
            require(item["scope"] not in identity_refs, "duplicate candidate evidence role")
            identity_refs[item["scope"]] = (source_inventory_identity(evidence_root, item, candidate)
                                             if item["scope"] == "candidate_source_inventory" else item["sha256"])
        except (OSError, ValueError):
            issue("candidate_raw_evidence_missing_or_changed", role=item["scope"])
    for role, name in (("candidate_package", "package_sha256"), ("candidate_source_inventory", "source_inventory_sha256"),
                       ("candidate_descriptor", "release_descriptor_sha256")):
        if identity_refs.get(role) != candidate[name] or candidate[name] is None:
            issue("candidate_artifact_identity_mismatch", role=role)
    expected_rows = _requirements(scope)
    required_keys = {(case, test, context): (minimum, roles) for case, test, context, minimum, roles in expected_rows}
    latest, history = {}, []
    for case, rows in attempts.items():
        for row, hashed in rows:
            try:
                observation = json.loads(row["note"], object_pairs_hook=recorder.unique_object,
                                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite note")))
                validate_observation(observation, case, scope)
                key = (case, observation["test"], observation["context"])
                require(key in required_keys, "observation is outside the selected casebook")
                cycle_key = (*key, observation["cycle"])
                prior = latest.get(cycle_key)
                require(observation["retest_of"] == (prior[2] if prior else None), "cycle replay/retest reference differs")
                roles = {item["scope"] for item in observation["raw"]}
                require(required_keys[key][1].issubset(roles), "required raw evidence scopes are missing")
                if case == "restore":
                    require(len({item["sha256"] for item in observation["raw"] if item["scope"] in
                            {"card_restore", "overlay_restore", "internal_restore"}}) == 3,
                            "card, overlay and internal restore need separate observed artifacts")
                if observation["test"] == "native_engine":
                    runtime = next(item for item in scope["runtimes"] if item["id"] == observation["context"])
                    require(any(item["scope"] == "corresponding_source" and item["sha256"] == runtime["source_archive_sha256"]
                                for item in observation["raw"]), "native corresponding-source artifact differs")
                for item in observation["raw"]:
                    artifact(item)
                latest[cycle_key] = (row, observation, hashed)
                history.append({"case": case, "test": key[1], "context": key[2], "cycle": cycle_key[3],
                                "status": row["status"], "attempt_sha256": hashed})
            except (OSError, ValueError, TypeError, KeyError, RecursionError):
                issue("incomplete_or_inconsistent_attempt", case=case, attempt_sha256=hashed)
    results, counts = {}, []
    all_physical = True
    for case in recorder.CASES:
        relevant = [item for item in expected_rows if item[0] == case]
        if not relevant:
            results[case] = {"status": "excluded", "operator_status": summary["cases"][case]["status"],
                             "reason": scope["excluded_features"].get("ports", "No selected optional context.")}
            continue
        complete = True
        failed = False
        for _, test, context, minimum, _ in relevant:
            cells = sorted(((key[3], value) for key, value in latest.items() if key[:3] == (case, test, context)), key=lambda item: item[0])
            passed = [item for item in cells if item[1][0]["status"] == "pass"]
            valid_indices = [item[0] for item in cells]
            contiguous = valid_indices == list(range(1, len(valid_indices) + 1))
            ok = len(passed) >= minimum and len(passed) == len(cells) and contiguous
            if not ok:
                complete = False
                issue("missing_or_failed_context_cycles", case=case, test=test, context=context,
                      required=minimum, passed=len(passed), attempted=len(cells), contiguous=contiguous)
            failed = failed or any(item[1][0]["status"] == "fail" for item in cells)
            all_physical = all_physical and all(item[1][1]["provenance"] == "physical_operator" for item in passed)
            counts.append({"case": case, "test": test, "context": context, "required": minimum,
                           "passed": len(passed), "attempted": len(cells), "complete": ok})
        results[case] = {"status": "pass" if complete else "fail" if failed else "incomplete",
                         "operator_status": summary["cases"][case]["status"], "attempts": summary["cases"][case]["attempts"]}
    cold = [value for key, value in latest.items() if key[1] == "cold_boot" and value[0]["status"] == "pass"]
    if len(cold) < 10 or len({value[1]["boot_id"] for value in cold}) != len(cold):
        issue("cold_boot_total_or_unique_boot_ids_missing", required=10, passed=len(cold))
        results["boot"]["status"] = "incomplete"
    for test in TEST_CASES:
        cells = sorted((value[1] for key, value in latest.items() if key[1] == test and value[0]["status"] == "pass"),
                       key=lambda value: stamp(value["started_at"]))
        if any(stamp(left["ended_at"]) > stamp(right["started_at"]) for left, right in zip(cells, cells[1:])):
            issue("overlapping_cycle_intervals", test=test)
            results[TEST_CASES[test]]["status"] = "incomplete"
    # Raw files are checked again after the casebook scan, rather than reusing a
    # stale successful hash when an artifact changed during review.
    recheck_budget = [MAX_TOTAL_RAW_BYTES]
    for item in raw_cache.values():
        try:
            _artifact(evidence_root, item, budget=recheck_budget)
        except (OSError, ValueError):
            issue("raw_evidence_changed_during_review", sha256=item["sha256"])
    after_summary = recorder.report(session)
    if after_summary != summary:
        issue("acceptance_session_changed_during_review")
    casebook_sha256 = recorder.digest(recorder.encoded({"session_id": identity["session_id"],
        "profile_sha256": identity["profile_sha256"], "scope_sha256": scope_digest(scope),
        "snapshot_sha256": summary["snapshot_sha256"],
        "attempts": {case: [hashed for _, hashed in rows] for case, rows in attempts.items()}}))
    review_scopes = ["core"] + ["native:" + item["id"] for item in scope["runtimes"] if item["kind"] == "native_candidate"] + [
        "resume:" + item["id"] for item in scope["runtimes"] if item["state_resume"]] + [
        "port:" + item["id"] for item in scope["runtimes"] if item["kind"] == "port"]
    reviewer_result = {"status": "not_supplied", "required_scopes": review_scopes, "authenticated": False,
                       "qualification_granted": False}
    if reviewer is not None:
        exact(reviewer, ("schema", "kind", "scope_sha256", "casebook_sha256", "reviewer_sha256", "independent", "scopes", "decision", "evidence"), "reviewer statement")
        require(type(reviewer["schema"]) is int and reviewer["schema"] == 1 and reviewer["kind"] == "qualification-reviewer-scope" and
                reviewer["scope_sha256"] == scope_digest(scope) and type(reviewer["reviewer_sha256"]) is str and
                DIGEST.fullmatch(reviewer["reviewer_sha256"]) and type(reviewer["casebook_sha256"]) is str and
                DIGEST.fullmatch(reviewer["casebook_sha256"]) and type(reviewer["independent"]) is bool and
                type(reviewer["scopes"]) is list and len(set(reviewer["scopes"])) == len(reviewer["scopes"]) and
                set(reviewer["scopes"]).issubset(review_scopes) and reviewer["decision"] in {"accept", "reject", "needs_work"}, "invalid declared reviewer scope")
        raw_reference(reviewer["evidence"])
        require(reviewer["evidence"]["scope"] == "reviewer_statement", "invalid reviewer evidence role")
        try:
            _artifact(evidence_root, reviewer["evidence"])
            reviewer_result.update(status="operator_supplied_statement" if reviewer["casebook_sha256"] == casebook_sha256 else "stale_casebook_statement",
                                   casebook_binding_matches=reviewer["casebook_sha256"] == casebook_sha256,
                                   declared_scopes=reviewer["scopes"],
                                   all_scopes_declared=set(reviewer["scopes"]) == set(review_scopes),
                                   independent_claim=reviewer["independent"], declared_decision=reviewer["decision"],
                                   evidence_sha256=reviewer["evidence"]["sha256"])
        except (OSError, ValueError):
            reviewer_result["status"] = "missing_or_changed_statement"
    complete = not issues
    return recorder.checksummed({"schema": 1, "kind": "qualification-review-proposal", "session_id": identity["session_id"],
        "scope_sha256": scope_digest(scope), "plan_sha256": plan_hash, "casebook_sha256": casebook_sha256,
        "status": "incomplete" if not complete else "host_or_static_evidence_only" if not all_physical or not physical_snapshots else "ready_for_independent_review",
        "evidence_structurally_complete": complete, "physical_operator_claims_complete": complete and all_physical and physical_snapshots,
        "cases": results, "context_cycles": counts, "cold_boot_total": len(cold), "save_readback": save_summary,
        "issues": issues, "retained_attempt_history": history, "raw_artifacts_checked": len(raw_cache),
        "excluded_features": scope["excluded_features"], "omitted_runtimes": scope["omitted_runtimes"],
        "independent_review": reviewer_result, "hardware_qualified": False, "runtime_verified": False,
        "source_use_verified": False, "distribution_cleared": False, "automatic_activation": False,
        "production_configuration_generated": False, "review_required": True,
        "limits": ["Hashes, timestamps and operator labels are consistency checks, not authenticated physical observations.",
                   "Candidate inventories must include transitive imports and independently reviewed build correspondence.",
                   "Raw save/load, recovery, performance and licence meaning require independent human review.",
                   "A reviewer JSON statement, complete casebook or report cannot enable any runtime/profile gate."]})


def publish(output, value, forbidden_roots=()):
    output = recorder.no_links(output)
    for root in (*forbidden_roots, PROJECT.parent):
        root = recorder.no_links(root).resolve(strict=True)
        require(output != root and root not in output.parents, "keep private review outputs outside the session, evidence and repository")
    # Exclusive publication intentionally leaves uncertain output on failure;
    # cleanup must never unlink a concurrently replaced operator-owned file.
    hashed = recorder.put_new(output, value)
    _, actual = recorder.read_json(output)
    require(actual == hashed, "review output changed during publication")
    return {"sha256": hashed, "hardware_qualified": False, "automatic_activation": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("template")
    prepare.add_argument("--session", required=True)
    prepare.add_argument("--output", required=True)
    add = commands.add_parser("record")
    add.add_argument("--session", required=True)
    add.add_argument("--scope", required=True)
    add.add_argument("--evidence-root", required=True)
    add.add_argument("--observation", required=True)
    add.add_argument("--case", choices=tuple(recorder.CASES), required=True)
    add.add_argument("--status", choices=("pass", "fail", "blocked"), required=True)
    observation = commands.add_parser("observation-template")
    observation.add_argument("--session", required=True)
    observation.add_argument("--scope", required=True)
    observation.add_argument("--case", choices=tuple(recorder.CASES), required=True)
    observation.add_argument("--test", choices=(*TEST_CASES, "case"), required=True)
    observation.add_argument("--context", required=True)
    observation.add_argument("--cycle", type=int, default=1)
    observation.add_argument("--output", required=True)
    check = commands.add_parser("review")
    check.add_argument("--session", required=True)
    check.add_argument("--scope", required=True)
    check.add_argument("--evidence-root", required=True)
    check.add_argument("--plan", default=str(DEFAULT_PLAN))
    check.add_argument("--reviewer")
    check.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            value = template(args.session)
            print(json.dumps(publish(args.output, value, (args.session,)), sort_keys=True))
        elif args.command == "observation-template":
            scope, _ = recorder.read_json(args.scope)
            value = observation_template(scope, args.case, args.test, args.context, args.cycle)
            with recorder.locked(args.session) as locked:
                identity, _ = recorder.manifest(locked)
                require(identity["session_id"] == scope["session_id"] and identity["profile_sha256"] == scope["profile_sha256"],
                        "observation template scope belongs to another session/profile")
            print(json.dumps(publish(args.output, value, (args.session,)), sort_keys=True))
        else:
            scope, _ = recorder.read_json(args.scope)
            if args.command == "record":
                observation, _ = recorder.read_json(args.observation)
                value = record_observation(args.session, scope, args.case, args.status, observation, args.evidence_root)
                print(json.dumps({"attempt_sha256": recorder.digest(recorder.encoded(value)), "hardware_qualified": False}, sort_keys=True))
            else:
                reviewer = recorder.read_json(args.reviewer)[0] if args.reviewer else None
                value = review(args.session, scope, args.evidence_root, plan=args.plan, reviewer=reviewer)
                receipt = publish(args.output, value, (args.session, args.evidence_root))
                print(json.dumps({**receipt, "status": value["status"], "issues": len(value["issues"])}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        print("qualification-review: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
