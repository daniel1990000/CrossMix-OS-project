# SPDX-License-Identifier: MIT
"""Host-only composition of the actual principal, relay and embedded runner.

Every process uses one independently specified synthetic tree. Hardware/model
objects are injected; capability transport, peer credentials, signed authority
records, source ownership, and the actual kernel completion are exercised.
"""
from dataclasses import replace
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from bridge.process_source import process_start
from bridge.resident import SERVER_ENV
from test_experimental_runtime import make_fixture_configuration, prepare_fixture_tree


def launch_bytes(root, principal_pid, principal_start, mode):
    argv = (sys.executable, str(Path(__file__).resolve()), "source", str(root),
            str(principal_pid), principal_start, mode)
    return ("#!/bin/sh\nexec " + " ".join(shlex.quote(value) for value in argv) + "\n").encode()


def budgets(mode):
    return {"view_seconds": 10, "return_seconds": 0.15} if mode == "slow_cleanup" else {}


def source(config, mode):
    from bridge import process_source
    from bridge.resident import _exchange
    from psp_shell.embedded import EmbeddedDependencies, EmbeddedRunner
    from psp_shell.health import FrontendHealth
    from psp_shell.runtime import ContractError
    from test_embedded import EmbeddedTests, FakeBackend

    process_source.configured_runtime = lambda: config
    fixture = EmbeddedTests(methodName="runTest")
    fixture.setUp()
    session = config.experimental_session
    context = replace(fixture.context, sd_root=config.sd_root, state_dir=config.state_dir,
        profile=config.profile, inventory=config.inventory(), preferences=config.preferences(),
        experimental_session=session)
    health = FrontendHealth(config.state_dir)
    state = health.record()
    health.request("project", state["generation"])
    dependencies = EmbeddedDependencies(renderer_factory=fixture.renderer_factory,
        backend_factory=FakeBackend,
        settings_factory=lambda *_: (_ for _ in ()).throw(AssertionError("SettingsStore write")))
    runner = EmbeddedRunner(context, health=health, dependencies=dependencies)
    try:
        with fixture.provider_patch():
            if mode == "view":
                original_present = context.display.present
                attempted = []
                def present():
                    original_present()
                    if not attempted:
                        attempted.append(True)
                        try:
                            _exchange(config, "experimental-check", ["return"])
                        except ContractError:
                            pass
                        else:
                            raise AssertionError("release skipped bounded cleanup")
                context.display.present = present
                result = runner.run(max_frames=2, scripted_actions=("confirm", "back"))
                assert result.reason == "classic" and result.real_game_launches == 0
                assert session.phase == "released"
                # Even a valid capability cannot repeat a consumed phase or
                # route a shared-service mutator around the frontend policy.
                for operation, arguments in (("experimental-check", ["return"]),
                                             ("bluetooth-apply", [])):
                    try:
                        _exchange(config, operation, arguments)
                    except ContractError:
                        pass
                    else:
                        raise AssertionError("resident accepted stale/mutating request")
            elif mode == "mutator":
                try:
                    runner.run(max_frames=4, scripted_actions=("confirm", "favorite"))
                except ContractError:
                    pass
                else:
                    raise AssertionError("favorite write was permitted")
                assert session.phase == "blocked"
                assert not runner.release_for_fallback()
            elif mode == "staged":
                def staged():
                    config.staged_command.write_text("owner staged bytes\n")
                original = context.display.present
                context.display.present = lambda: (original(), staged())[-1]
                try:
                    runner.run(max_frames=1)
                except ContractError:
                    pass
                else:
                    raise AssertionError("staged command allowed release")
                assert config.staged_command.read_text() == "owner staged bytes\n"
                assert session.phase == "blocked"
            elif mode == "slow_cleanup":
                original_close = fixture.renderer_factory.close
                def close(renderer):
                    original_close(renderer)
                    time.sleep(0.35)
                fixture.renderer_factory.close = close
                try:
                    runner.run(max_frames=1)
                except ContractError:
                    pass
                else:
                    raise AssertionError("overdue renderer cleanup reported release")
                assert session.phase != "released"
            else:
                raise AssertionError("unknown fixture mode")
        assert "existing-device-run-game" not in fixture.events
        assert "validate-existing-action" not in fixture.events
        (config.sd_root.parent / "source-result.json").write_text(json.dumps({
            "phase": session.phase, "events": fixture.events, "mode": mode}))
    finally:
        session.close()
        fixture.doCleanups()


def driver(root, mode):
    from bridge.resident import PrincipalLease
    principal_pid, principal_start = os.getpid(), process_start(os.getpid())
    overrides = {"App/PyUI/launch.sh": launch_bytes(root, principal_pid, principal_start, mode)}
    prepare_fixture_tree(root, overrides)
    config = make_fixture_configuration(root, principal_pid=principal_pid,
        principal_start=principal_start, role_name="driver", overrides=overrides, **budgets(mode))
    environment = dict(os.environ)
    args = (str(root), str(principal_pid), principal_start, mode)
    def command(role):
        return [sys.executable, str(Path(__file__).resolve()), role, *args]
    server = subprocess.Popen(command("resident"), env=environment, stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        environment[SERVER_ENV] = str(server.pid)
        ready = subprocess.run(command("ready"), env=environment, capture_output=True, text=True, timeout=8)
        assert ready.returncode == 0, ready.stdout + ready.stderr
        result = subprocess.run(command("principal"), env=environment, capture_output=True, text=True, timeout=12)
        if not (root.parent / "source-result.json").exists():
            raise AssertionError(result.stdout + result.stderr)
        lease = PrincipalLease(config, (principal_pid, principal_start))
        record = lease.read(config.experimental_session.record_name)
        outcome = json.loads((root.parent / "source-result.json").read_text())
        assert record["source_pid"] != record["helper_pid"]
        assert outcome["mode"] == mode
        if mode == "view":
            assert result.returncode == 0, result.stdout + result.stderr
            assert json.loads(result.stdout) == {"exit_status": 0, "children_reaped": 1}
            assert record["phase"] == "released" and lease.global_state()["phase"] == "idle"
            assert record["return_deadline"] <= record["return_started_monotonic"] + config.experimental_session.return_seconds
            assert outcome["phase"] == "released"
            assert outcome["events"].count("attach-existing-renderer") == 1
            assert outcome["events"].count("close-project-renderer") == 1
            replay = subprocess.run(command("principal"), env=environment, capture_output=True, text=True, timeout=8)
            assert replay.returncode != 0 and "EXPERIMENTAL_REPLAY" in replay.stderr, replay.stderr
            assert lease.global_state()["phase"] == "idle"
        else:
            assert result.returncode != 0, result.stdout
            assert record["phase"] != "released" and lease.global_state()["phase"] == "source-running"
            assert outcome["phase"] != "released"
            if mode == "staged":
                assert config.staged_command.read_text() == "owner staged bytes\n"
        print(json.dumps({"mode": mode, "phase": record["phase"], "lifetime": lease.global_state()["phase"]}))
    finally:
        if server.poll() is None:
            drain = subprocess.run(command("drain"), env=environment, capture_output=True, text=True, timeout=8)
            assert drain.returncode == 0, drain.stdout + drain.stderr
        server.wait(timeout=8)
        diagnostics = server.stderr.read().decode("utf-8", errors="replace")
        server.stderr.close()
        config.experimental_session.close()
        assert server.returncode == 0, diagnostics


def main():
    role, root, *arguments = sys.argv[1:]
    root = Path(root).absolute()
    if role == "driver":
        driver(root, arguments[0])
        return
    principal_pid, principal_start, mode = int(arguments[0]), arguments[1], arguments[2]
    if role == "drain":
        # Maintenance drains do not admit a UI and must remain available when
        # a failed source left staged bytes. The real relay still authenticates
        # this direct helper's PID, ancestry and existing private capability.
        from types import SimpleNamespace
        from bridge.resident import request_drain
        request_drain(SimpleNamespace(state_dir=root.parent / "experimental-state",
            private_runtime=root.parent / "experimental-private-runtime"), int(os.environ[SERVER_ENV]))
        return
    overrides = {"App/PyUI/launch.sh": launch_bytes(root, principal_pid, principal_start, mode)}
    config = make_fixture_configuration(root, principal_pid=principal_pid,
        principal_start=principal_start, role_name=role, overrides=overrides, **budgets(mode))
    try:
        if role == "resident":
            from bridge.resident import ResidentServer
            ResidentServer(config).serve()
        elif role == "ready":
            from bridge.resident import wait_ready
            wait_ready(config, int(os.environ[SERVER_ENV]))
        elif role == "principal":
            from bridge.principal import PrincipalBoundary
            result = PrincipalBoundary(config).run_pyui()
            print(json.dumps({"exit_status": result.exit_status, "children_reaped": result.children_reaped}))
        elif role == "source":
            source(config, mode)
        else:
            raise AssertionError("unknown process role")
    finally:
        config.experimental_session.close()


if __name__ == "__main__":
    main()
