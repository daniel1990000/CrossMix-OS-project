# SPDX-License-Identifier: MIT
"""Dedicated host-only process for real principal→source harness→capability IPC.

Every true qualification flag and stopped-writer callback here is an explicit
fixture. Source staging, sealed script execution, subreaper completion, native
state functions/export and authenticated fresh-process transfer are real code.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace
import uuid

from bridge.bootstrap import ForegroundIdentity
from bridge.principal import PrincipalBoundary
import bridge.process_source as source
from bridge.process_source import ProcessSourceConfiguration
from psp_shell.health import FrontendHealth
from psp_shell.runtime import POWER_OFF_ROUTE, SPRUCE_COMMIT
from psp_shell.state_evidence import (PrincipalStateSessionAuthority, QualifiedStateProfile, StateCapabilityStore,
                                      VerifiedLoadCompletion, WriterStoppedEvidence)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    role, configured_root, operation = sys.argv[1:]
    root = Path(configured_root)
    card = root / "card"
    state_dir = root / "health"
    principal_sha = sha(card / "spruce/scripts/principal.sh")
    required = {"spruce/scripts/principal.sh": principal_sha}
    runtime_profile = {"id": "host-fixture-state-roundtrip", "execution_environment": "host-fixture",
        "source_commit": SPRUCE_COMMIT, "firmware_version": "1.1.1", "required_hashes": required,
        "source_use_verified": True, "runtime_verified": True, "hardware_qualified": True, "process_exit_qualified": True}
    inventory = {"live": False, "model": "TG5040", "platform": "SmartPro", "architecture": "aarch64",
        "source_commit": SPRUCE_COMMIT, "firmware_version": "1.1.1", "hashes": required}
    preferences = {"enableButtonWatchers": False, "poweroffCmd": POWER_OFF_ROUTE}
    state_profile = QualifiedStateProfile("host-fixture-state", "PPSSPP", "fixture-engine", card / "engine", sha(card / "engine"),
        card, (card / "states",), ("fixture-engine",), principal_sha,
        architecture="aarch64" if __import__("platform").machine() == "aarch64" else "x86_64", hardware_qualified=True,
        writer_inventory_qualified=True, state_save_load_qualified=True, native_state_launch_qualified=True,
        config_hashes=((str(card / "ppsspp.ini"), sha(card / "ppsspp.ini")),))
    store = StateCapabilityStore(root / "capabilities")
    writers = lambda foreground, profile: WriterStoppedEvidence(foreground, profile.writer_ids, "host-fixture-writers", lambda: True)
    authority = PrincipalStateSessionAuthority(store=store, private_root=root, profiles={"PSP": state_profile}, observe_writers=writers)
    config = ProcessSourceConfiguration(runtime_profile, lambda: inventory, lambda: preferences, state_dir=state_dir, sd_root=card,
        staged_command=root / "command.sh", private_runtime=root / "runtime", command_environment=authority.command_environment,
        completion_observer=authority.completion_observer, resume_evidence=authority.resume_evidence,
        mode_actions=authority.source_mode_actions, execution_environment="host-fixture")
    if role == "stage":
        FrontendHealth(state_dir).begin_foreground(uuid.uuid4().hex)
        source._source_tasks = SimpleNamespace(config=config, _phase="prepared", _input_prepared=True,
            source_game={"system_id": "PSP", "rom_relative": "Roms/PSP/game.iso"}, state_intent=None)
        source.configured_runtime = lambda: config
        if operation.startswith("resume"):
            records = authority.resume_evidence()
            assert len(records) == 1
            record = next(iter(records.values()))
            source.capture_state_resume_intent(state_path=str(record.state_path), state_sha256=record.state_sha256, slot=record.slot)
        command = shlex.quote(str(card / "engine")) + " " + operation + " " + shlex.quote(str(card)) + ' "$TRIMUI_PROJECT_STATE_REQUEST"\n'
        assert source.stage_existing_command(command)
        store.close()
        return
    health = FrontendHealth(state_dir)
    launcher = card / "App/PyUI/launch.sh"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/bin/sh\nexec " + shlex.join([sys.executable, __file__, "stage", str(root), operation]) + "\n")
    launcher.chmod(0o700)
    boundary = PrincipalBoundary(config)
    source_tree = boundary.run_pyui()
    assert source_tree.children_reaped >= 1
    tree, completion = boundary.run_command()
    assert completion is not None and completion.spruce_return().foreground_ended
    assert health.foreground_identity() is None
    assert authority.last_error == ("STATE_OPERATION_FAILED" if "failure" in operation else None), authority.last_error
    records = authority.resume_evidence()
    assert len(records) == 1
    record = next(iter(records.values()))
    if operation == "resume":
        ack = store.load(record.identity.game_id, state_profile, writers, acknowledgement=True)
        assert type(ack) is VerifiedLoadCompletion
        assert ack.state.state_sha256 == record.state_sha256
    print(json.dumps({"operation": operation, "records": len(records), "foreground_clear": True,
                      "children_reaped": tree.children_reaped, "checkpoint": record.recorded_at_utc,
                      "state_sha256": record.state_sha256}))
    store.close()


if __name__ == "__main__":
    main()
