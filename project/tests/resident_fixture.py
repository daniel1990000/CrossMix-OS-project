"""Isolated acceptance driver. All scripts/data live in the named host fixture.

The actual pinned Bluetooth apply/watch shell and transformed PyUI worker run;
only hardware commands, absolute fixture paths, and device observations are
substituted. No fixture establishes installed/runtime/device qualification.
"""
import ast
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

from test_principal_integration import fixture_configuration
from bridge.process_source import process_start
from bridge.resident import SERVER_ENV


def _script(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw)
    path.chmod(0o700)


def source_worker(root, common):
    import threading
    from types import SimpleNamespace
    from bridge import process_source, resident
    from psp_shell.health import FrontendHealth
    config = fixture_configuration(root)
    process_source.configured_runtime = lambda: config
    tree = ast.parse(common.read_text())
    names = {"enable_bluetooth", "_apply_bluetooth", "_bluetooth_apply_worker", "_bluetooth_cmd"}
    methods = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in names]
    for method in methods:
        method.decorator_list = []
    namespace = {"threading": threading, "subprocess": subprocess, "os": os,
        "PyUiConfig": SimpleNamespace(get_bluetooth_cmd=lambda: "/mnt/SDCARD/spruce/scripts/bin/spruce_bluetooth"),
        "PyUiLogger": SimpleNamespace(get_logger=lambda: SimpleNamespace(error=lambda _: None))}
    exec(compile(ast.Module(body=methods, type_ignores=[]), "<actual transformed Bluetooth workers>", "exec"), namespace)
    device = type("ActualWorkerFixture", (), {n: namespace[n] for n in names})()
    device.system_config = SimpleNamespace(set_bluetooth=lambda value: (root / "setting").write_text(str(value)))
    device._bt_apply_lock, device._bt_apply_running, device._bt_apply_again = threading.Lock(), False, False
    device._bluetooth_status = SimpleNamespace(force_refresh=lambda: None)
    device.refresh_audio_route = lambda: None
    device.perform_startup_tasks, device.watch_audio_route = lambda: None, lambda: None
    tasks = process_source.begin_process_source_tasks(device, lambda: None)
    tasks._startup.thread.join(); tasks._managers.thread.join()
    device.enable_bluetooth()
    deadline = time.monotonic() + 5
    while device._bt_apply_running and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not device._bt_apply_running, "actual source worker did not finish"
    assert (root / "bt-on").exists()

    # Replay/stale/shape/disconnect attempts never launch another operation.
    capability = json.loads(os.environ[resident.CAPABILITY_ENV])
    lease = resident.PrincipalLease(config, tuple(capability["principal"]))
    scope = capability["scope"]
    value = {"helper_pid": scope["pid"], "sequence": 1, "operation": "bluetooth-apply", "arguments": [], "stdin": None}
    with resident._connect(lease, capability["server_pid"]) as connection:
        resident._send(connection, {**value, "mac": resident._mac(bytes.fromhex(scope["key"]), value)})
        assert resident._receive(connection) == {"blocked": True}
    value.update(sequence=2, operation="wifi", arguments=["connect"], stdin="s" * 1025)
    with resident._connect(lease, capability["server_pid"]) as connection:
        resident._send(connection, {**value, "mac": resident._mac(bytes.fromhex(scope["key"]), value)})
        assert resident._receive(connection) == {"blocked": True}
    with resident._connect(lease, capability["server_pid"]) as connection:
        connection.sendall(b'{"incomplete":')
        connection.shutdown(__import__("socket").SHUT_WR)
        assert resident._receive(connection) == {"blocked": True}
    assert (root / "up-count").read_text().splitlines() == ["up"]
    path = root / "stale-capability"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(descriptor, os.environ[resident.CAPABILITY_ENV].encode()); os.close(descriptor)
    tasks.stop_background_tasks(); tasks.release_input()
    FrontendHealth(config.state_dir).begin_foreground("host-fixture-radio-game")
    command = ('test -z "${TRIMUI_PROJECT_RESIDENT_CAPABILITY+x}" && '
        'test -z "${TRIMUI_PROJECT_RESIDENT_SERVER+x}" && printf launched > ' + shlex.quote(str(root / "launched")) + "\n")
    process_source.stage_existing_command(command)


def acceptance(root, common, original_bt):
    root.mkdir(parents=True, exist_ok=True)
    config = fixture_configuration(root)
    helpers = root / "helpers.sh"
    helpers.write_text("""log_message() { :; }
device_bluetooth_supported() { return 0; }
device_bluetooth_up() { touch BT_ON; echo up >> UP_COUNT; }
device_bluetooth_down() { rm -f BT_ON; }
device_bt_audio_connected() { :; }
""".replace("BT_ON", shlex.quote(str(root / "bt-on"))).replace("UP_COUNT", shlex.quote(str(root / "up-count"))))
    scripts = config.sd_root / "spruce/scripts"
    scripts.mkdir(parents=True)
    bluetooth = original_bt.read_text().replace(". /mnt/SDCARD/spruce/scripts/helperFunctions.sh", ". " + shlex.quote(str(helpers)))
    for name in ("bluetooth_user_disconnected", "bluetooth_watch.pid", "audio_reinit_needed", "bluetooth_last_failure"):
        bluetooth = bluetooth.replace("/tmp/" + name, str(root / name))
    bluetooth = bluetooth.replace("/mnt/SDCARD/spruce/scripts/asound-setup.sh", str(root / "asound.sh"))
    _script(scripts / "bluetooth.sh", bluetooth)
    _script(root / "asound.sh", "#!/bin/sh\n:\n")
    _script(root / "bin/jq", "#!/bin/sh\ncat " + shlex.quote(str(root / "setting")) + "\n")
    _script(root / "bin/pidof", "#!/bin/sh\ntest -e " + shlex.quote(str(root / "bt-on")) + "\n")
    _script(root / "bin/bluetoothctl", """#!/bin/sh
case "$1" in
devices) echo 'Device 00:11:22:33:44:55 Fixture headset' ;;
info) printf 'Paired: yes\nTrusted: yes\nConnected: yes\nName: Fixture headset\nIcon: audio-headset\n' ;;
esac
exit 0
""")
    worker = root / "worker.py"
    worker.write_text("from pathlib import Path\nfrom resident_fixture import source_worker\nsource_worker(Path(" + repr(str(root)) + "),Path(" + repr(str(common)) + "))\n")
    _script(config.sd_root / "App/PyUI/launch.sh", "#!/bin/sh\nexec " + shlex.quote(sys.executable) + " " + shlex.quote(str(worker)) + "\n")
    environment = dict(os.environ, PATH=str(root / "bin") + os.pathsep + os.environ["PATH"])
    prefix = "from pathlib import Path;from test_principal_integration import fixture_configuration;from bridge.principal import PrincipalBoundary;import sys;config=fixture_configuration(Path(sys.argv[1]));"
    resident_code = prefix + "from bridge.resident import ResidentServer;ResidentServer(config).serve()"
    server = subprocess.Popen([sys.executable, "-c", resident_code, str(root)], env=environment,
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        environment[SERVER_ENV] = str(server.pid)
        ready = prefix + "from bridge.resident import wait_ready;wait_ready(config,int(sys.argv[2]))"
        subprocess.run([sys.executable, "-c", ready, str(root), str(server.pid)], env=environment, check=True, capture_output=True, timeout=7)
        source = subprocess.run([sys.executable, "-c", prefix + "print(PrincipalBoundary(config).run_pyui().children_reaped)", str(root)],
                                env=environment, capture_output=True, text=True, timeout=8)
        assert source.returncode == 0, source.stdout + source.stderr
        assert int(source.stdout.strip()) == 1
        watcher = int((root / "bluetooth_watch.pid").read_text())
        assert process_start(watcher) is not None, "actual Bluetooth watcher was falsely treated as stopped"
        run = subprocess.run([sys.executable, "-c", prefix + "PrincipalBoundary(config).run_command()", str(root)],
                             env=environment, capture_output=True, text=True, timeout=5)
        assert run.returncode == 0, run.stdout + run.stderr
        assert (root / "launched").read_text() == "launched"
        assert process_start(watcher) is not None and server.poll() is None
        from bridge import process_source, resident
        process_source.configured_runtime = lambda: config
        os.environ[resident.CAPABILITY_ENV] = (root / "stale-capability").read_text()
        try:
            resident.delegate("bluetooth-apply")
        except Exception as error:
            assert getattr(error, "code", None) == "RESIDENT_UNVERIFIED"
        else:
            raise AssertionError("stale source capability authorized another process")
        assert (root / "up-count").read_text().splitlines() == ["up"]
    finally:
        (root / "bt-on").unlink(missing_ok=True)
        if server.poll() is None:
            drain = prefix + "from bridge.resident import request_drain;request_drain(config,int(sys.argv[2]))"
            result = subprocess.run([sys.executable, "-c", drain, str(root), str(server.pid)], env=environment,
                capture_output=True, text=True, timeout=5)
            assert result.returncode == 0, result.stdout + result.stderr
        server.wait(timeout=8)  # actual ECHILD, after every fixture service exited
        diagnostics = server.stderr.read().decode("utf-8", errors="replace")
        server.stderr.close()
        assert server.returncode == 0, diagnostics


if __name__ == "__main__":
    acceptance(*(Path(value) for value in sys.argv[1:]))
