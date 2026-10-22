# SPDX-License-Identifier: MIT
"""Explicit synthetic services for composed host acceptance, never device use.

The source command function, principal/subreaper, state authority, capability
store and Resume adapter are real. SDL/hardware, emulator serialization and
config copyback are named fixtures. Positive profile fields here are assumptions
inside an isolated temporary card and establish no device qualification.
"""
from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

MARKER = b"trimui-composed-host-flow-only-v1\n"

SYNTHETIC_ENGINE = r'''#!__PYTHON__
import hashlib, json, os, sys, time
from pathlib import Path
from psp_shell.state_evidence import _decode_packet, encode_packet, UPSTREAM, FORMAT
root = Path(__file__).resolve().parents[3]
assert (root / '.host-flow-fixture').read_bytes() == b'trimui-composed-host-flow-only-v1\n'
assert not root.is_relative_to(Path('/mnt/SDCARD'))
assert 'TRIMUI_PROJECT_RESIDENT_CAPABILITY' not in os.environ
assert 'TRIMUI_PROJECT_RESIDENT_SERVER' not in os.environ
request = Path(os.environ['TRIMUI_PROJECT_STATE_REQUEST'])
assert request.is_relative_to(root / 'private/transport')
assert request.parent.stat().st_mode & 0o777 == 0o700
fields = _decode_packet(request.read_bytes(), b'TPSE1Q\n', 15)
assert '--project-state-session=' + str(request) in sys.argv
assert sys.argv[1] == fields[6]
mode = fields[10]
if mode == 'resume':
    state = Path(fields[11])
    assert os.environ['TRIMUI_PROJECT_RESUME_STATE'] == str(state)
    assert '--state=' + str(state) in sys.argv
    assert hashlib.sha256(state.read_bytes()).hexdigest() == fields[12]
else:
    assert os.environ['TRIMUI_PROJECT_RESUME_STATE'] == ''
    assert not any(arg.startswith('--state=') for arg in sys.argv)
    state = root / 'card/Saves/fixture-state/engine-owned-slot.ppst'
    state.write_bytes(b'Explicit synthetic serializer bytes; not a PSP state.\n')
active = root / 'engine-active'
active.write_text('synthetic writer still owns this session')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
result = list(fields[:6]) + ['load' if mode == 'resume' else 'save', '1', 'success', 'synthetic completion',
    'ULUS12345', '1.00', 'ULUS12345_1.00', fields[6], sha(__file__), sha(fields[6]), sha(state),
    str(Path(__file__).stat().st_size), str(Path(fields[6]).stat().st_size), str(state.stat().st_size),
    str(state), fields[14] if mode == 'resume' else '2', UPSTREAM, 'trimui-slot-evidence-v1',
    'v1.20.3-composed-fixture', 'x86_64', FORMAT]
packet = encode_packet(b'TPSE1R\n', result)
for name in ('load-completed' if mode == 'resume' else 'save-completed', 'result'):
    with (request.parent / name).open('xb') as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(packet)
        output.flush()
        os.fsync(output.fileno())
(root / ('engine-' + mode + '.json')).write_text(json.dumps({'mode': mode, 'request': str(request),
    'resume_state': os.environ['TRIMUI_PROJECT_RESUME_STATE'], 'arguments': sys.argv[1:]}))
child = os.fork()
if child == 0:
    os.setsid()
    grandchild = os.fork()
    if grandchild:
        os._exit(0)
    time.sleep(0.05)
    active.unlink()
    (root / ('engine-descendant-' + mode)).write_text('exited after the main synthetic engine')
    os._exit(0)
os._exit(0)
'''


def main(argv=None):
    args = argv or sys.argv[1:]
    if len(args) != 2 or args[1] not in {"source", "pyui", "command", "inspect", "resident", "resident-ready", "resident-drain", "resident-worker"}:
        raise ValueError("This module is only a composed host-test service")
    root = Path(args[0]).resolve(strict=True)
    if root.is_relative_to(Path("/mnt/SDCARD")) or (root / ".host-flow-fixture").read_bytes() != MARKER:
        raise ValueError("A separate explicit host fixture is required")
    if args[1] == "resident-worker":
        for name in ("TRIMUI_PROJECT_STATE_REQUEST", "TRIMUI_PROJECT_RESUME_STATE",
                     "TRIMUI_PROJECT_RESIDENT_CAPABILITY", "TRIMUI_PROJECT_RESIDENT_SERVER"):
            assert name not in os.environ
        count = root / "resident-count"
        sequence = int(count.read_text()) + 1 if count.exists() else 1
        count.write_text(str(sequence))
        active = root / ("resident-active-" + str(sequence))
        active.write_text("explicit synthetic shared-service descendant")
        worker = os.getpid()
        child = os.fork()
        if child == 0:
            os.setsid()
            deadline = time.monotonic() + 30
            while os.getppid() == worker:
                assert time.monotonic() < deadline
                time.sleep(0.01)
            (root / ("resident-parent-" + str(sequence))).write_text(str(os.getppid()))
            while not (root / "resident-release").exists():
                assert time.monotonic() < deadline
                time.sleep(0.01)
            active.unlink()
            (root / ("resident-descendant-" + str(sequence))).write_text("fixture descendant exited naturally")
            os._exit(0)
        os._exit(0)
    card = root / "card"
    app = card / "App/PSPMode/integration/app"
    sys.path.insert(0, str(app))
    from bridge import principal, process_source
    from bridge.bootstrap import ForegroundIdentity, PRINCIPAL_PATH
    from bridge.process_source import ProcessSourceConfiguration
    from psp_shell.health import FrontendHealth
    from psp_shell.runtime import POWER_OFF_ROUTE, SPRUCE_COMMIT
    from psp_shell.state_evidence import (PrincipalStateSessionAuthority, QualifiedStateProfile,
        StateCapabilityStore, VerifiedLoadCompletion, WriterStoppedEvidence)
    assert Path(principal.__file__).is_relative_to(app)
    assert Path(process_source.__file__).is_relative_to(app)
    sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    state_dir = root / "health"
    health = FrontendHealth(state_dir)
    engine = card / "Emu/PSP/PPSSPPSDL_TrimUI"
    game = card / "Roms/PSP/Fixture ü ; data.iso"
    principal_hash = sha(card / PRINCIPAL_PATH)
    expected = {PRINCIPAL_PATH: principal_hash}
    profile = {"id": "host-fixture-composed", "execution_environment": "host-fixture",
        "source_commit": SPRUCE_COMMIT, "firmware_version": "1.1.1", "required_hashes": expected,
        "source_use_verified": True, "runtime_verified": True, "hardware_qualified": True,
        "process_exit_qualified": True}
    inventory = lambda: {"model": "TG5040", "platform": "SmartPro", "architecture": "aarch64",
        "firmware_version": "1.1.1", "source_commit": SPRUCE_COMMIT, "live": False,
        "hashes": {PRINCIPAL_PATH: sha(card / PRINCIPAL_PATH)}}
    config = ProcessSourceConfiguration(profile, inventory,
        lambda: {"enableButtonWatchers": False, "poweroffCmd": POWER_OFF_ROUTE},
        state_dir=state_dir, sd_root=card, staged_command=root / "cmd_to_run.sh",
        private_runtime=root / "runtime", execution_environment="host-fixture")
    if args[1] == "resident":
        from bridge.resident import ResidentServer
        ResidentServer(config).serve()
        return 0
    if args[1] == "resident-ready":
        from bridge.resident import SERVER_ENV, wait_ready
        wait_ready(config, int(os.environ[SERVER_ENV]))
        print(json.dumps({"resident_ready": True}))
        return 0
    if args[1] == "resident-drain":
        from bridge.resident import SERVER_ENV, request_drain
        request_drain(config, int(os.environ[SERVER_ENV]))
        print(json.dumps({"resident_drain_requested": True}))
        return 0
    state_profile = QualifiedStateProfile("host-fixture-state", "PPSSPP", "synthetic-ppsspp", engine, sha(engine),
        card, (card / "Saves/fixture-state",), ("synthetic-engine", "synthetic-copyback"), principal_hash,
        architecture="x86_64", hardware_qualified=True, writer_inventory_qualified=True,
        state_save_load_qualified=True, native_state_launch_qualified=True,
        config_hashes=((str(card / "Saves/fixture-state/native.ini"), sha(card / "Saves/fixture-state/native.ini")),))
    store = StateCapabilityStore(root / "private/capabilities", boot_id=health.boot_id)
    def writers(foreground, profile):
        return WriterStoppedEvidence(foreground, profile.writer_ids, "host-fixture:writers-after-ECHILD",
                                     lambda: not (root / "engine-active").exists())
    authority = PrincipalStateSessionAuthority(store=store, private_root=root / "private/transport",
                                              profiles={"PSP": state_profile}, observe_writers=writers)
    config = replace(config, command_environment=authority.command_environment,
                     completion_observer=authority.completion_observer,
                     resume_evidence=authority.resume_evidence, mode_actions=authority.source_mode_actions)
    if args[1] == "source":
        # Fixed reviewed bootstrap supplied in memory by this explicit fixture;
        # no saved JSON, package signer or selector chooses executable callbacks.
        process_source.configured_runtime = lambda: config
        # Execute the actual staged source mutator. The fixed configured radio
        # route delegates through the live relay before reaching its subprocess
        # fallback. Its shell implementation is an explicit host service fixture.
        radio_source = card / "App/PyUI/main-ui/devices/device_common.py"
        radio_class = next(item for item in ast.parse(radio_source.read_text()).body
                           if isinstance(item, ast.ClassDef) and item.name == "DeviceCommon")
        radio = next(item for item in radio_class.body if isinstance(item, ast.FunctionDef) and item.name == "_wifi_cmd")
        radio.decorator_list = []
        radio_module = ast.Module(body=[radio], type_ignores=[])
        ast.fix_missing_locations(radio_module)
        radio_namespace = {"PyUiConfig": SimpleNamespace(get_wifi_cmd=lambda: "/mnt/SDCARD/spruce/scripts/bin/spruce_wifi")}
        exec(compile(radio_module, str(radio_source), "exec"), radio_namespace)
        assert radio_namespace["_wifi_cmd"](None, "apply") == ""
        assert list(root.glob("resident-active-*"))
        source = card / "App/PyUI/main-ui/devices/miyoo_trim_common.py"
        module = ast.parse(source.read_text())
        cls = next(item for item in module.body if isinstance(item, ast.ClassDef) and item.name == "MiyooTrimCommon")
        methods = [item for item in cls.body if isinstance(item, ast.FunctionDef) and item.name in {"run_game", "write_cmd_to_run"}]
        assert len(methods) == 2
        for method in methods:
            method.decorator_list = []
        marker = root / "display-released"
        def exit_source():
            child = os.fork()
            if child == 0:
                os.setsid()
                grandchild = os.fork()
                if grandchild:
                    os._exit(0)
                time.sleep(0.05)
                (root / "source-descendant-exited").write_text("kernel exit observed")
                os._exit(0)
            os._exit(0)
        device = SimpleNamespace(perform_startup_tasks=lambda: None, watch_audio_route=lambda: None,
                                 fix_sleep_sound_bug=lambda: None, exit_pyui=exit_source)
        namespace = {"os": os, "shlex": shlex, "subprocess": subprocess, "RomInfo": object,
            "Theme": SimpleNamespace(check_and_create_ra_assets=lambda: None),
            "Device": SimpleNamespace(get_device=lambda: device),
            "Display": SimpleNamespace(deinit_display=lambda: marker.write_text("source display released"))}
        tree = ast.Module(body=methods, type_ignores=[])
        ast.fix_missing_locations(tree)
        exec(compile(tree, str(source), "exec"), namespace)
        namespace["MiyooTrimCommon"] = SimpleNamespace(write_cmd_to_run=namespace["write_cmd_to_run"])
        device.run_game = lambda model: namespace["run_game"](device, model)
        tasks = process_source.begin_process_source_tasks(device, lambda: None)
        tasks._startup.thread.join(5)
        tasks._managers.thread.join(5)
        assert tasks.quiescent()
        config_model = SimpleNamespace(get_emu_folder=lambda: str(card / "Emu/PSP"),
            get_launch=lambda: "../../spruce/scripts/emu/standard_launch.sh")
        model = SimpleNamespace(rom_file_path=str(game), game_system=SimpleNamespace(system_name="PSP", game_system_config=config_model))
        # Offer the explicit Resume action only after the authenticated store
        # supplies a typed capability to this fresh source process.
        evidence = config.resume_evidence()
        health.begin_foreground(uuid.uuid4().hex)
        tasks.stop_background_tasks()
        tasks.release_input()
        if evidence:
            assert len(evidence) == 1
            callback = config.mode_actions(device)["PPSSPP"]["resume"]
            callback(model, next(iter(evidence.values())))
        else:
            device.run_game(model)
        raise AssertionError("The existing source handoff did not exit its process")
    boundary = principal.PrincipalBoundary(config)
    if args[1] == "pyui":
        value = boundary.run_pyui()
        assert value.children_reaped >= 3
        assert (root / "source-descendant-exited").exists()
        print(json.dumps({"operation": "pyui", "children_reaped": value.children_reaped,
                          "import_root": str(app), "foreground": health.foreground_identity()}))
    elif args[1] == "command":
        value, completion = boundary.run_command()
        assert value.children_reaped >= 3 and completion is not None
        assert authority.last_error is None, authority.last_error
        assert not (root / "engine-active").exists()
        assert not (root / "cmd_to_run.sh").exists()
        assert health.foreground_identity() is None
        print(json.dumps({"operation": "command", "children_reaped": value.children_reaped,
                          "states": store.game_ids(), "kernel_receipt": completion.verification_id}))
    else:
        ids = store.game_ids()
        assert len(ids) == 1
        saved = store.load(ids[0], state_profile, writers)
        loaded = store.load(ids[0], state_profile, writers, acknowledgement=True)
        assert type(loaded) is VerifiedLoadCompletion
        assert saved.state_path == loaded.state.state_path
        assert saved.state_sha256 == loaded.state.state_sha256
        assert health.foreground_identity() is None
        print(json.dumps({"saved_capability": True, "load_acknowledgement": True,
                          "state_sha256": saved.state_sha256, "foreground_clear": True}))
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
