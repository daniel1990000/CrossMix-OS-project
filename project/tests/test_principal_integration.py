"""Actual transformed source seams and Linux-owned process boundary acceptance.

All true source/runtime/hardware flags are named host fixtures. No installed
device, emulator, input device, power service or real game is run or qualified.
"""
import ast
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bridge.bootstrap import ForegroundIdentity, PRINCIPAL_PATH
from bridge.principal_integration import SOURCE_BLOBS, stage_process_exit_integration
from bridge.process_source import ProcessSourceConfiguration
from psp_shell.health import FrontendHealth, _atomic
from psp_shell.runtime import POWER_OFF_ROUTE, SPRUCE_COMMIT

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("SPRUCE_SOURCE_ROOT", "/workspace/spruce-base"))
MIYOO = "App/PyUI/main-ui/devices/miyoo_trim_common.py"


def fixture_configuration(root, **kwargs):
    """Explicit fixture config; its independent expected values are synthetic."""
    root = Path(root)
    (root / "card").mkdir(exist_ok=True)
    profile = {"id": "host-fixture-principal", "execution_environment": "host-fixture",
        "source_use_verified": True, "runtime_verified": True, "hardware_qualified": True,
        "process_exit_qualified": True, "source_commit": SPRUCE_COMMIT,
        "firmware_version": "1.1.1", "required_hashes": {PRINCIPAL_PATH: "a" * 64}}
    observed = {"model": "TG5040", "platform": "SmartPro", "architecture": "aarch64", "live": False,
        "source_commit": SPRUCE_COMMIT, "firmware_version": "1.1.1", "hashes": {PRINCIPAL_PATH: "a" * 64}}
    return ProcessSourceConfiguration(profile=profile, inventory=lambda: observed,
        preferences=lambda: {"enableButtonWatchers": False, "poweroffCmd": POWER_OFF_ROUTE},
        state_dir=root / "state", sd_root=root / "card", staged_command=root / "cmd_to_run.sh", private_runtime=root / "runtime",
        execution_environment="host-fixture", **kwargs)


def fixture_pending_command(config, raw):
    """Stage in an actual source child and commit only real ECHILD closure."""
    import base64
    launcher = config.sd_root / "App/PyUI/launch.sh"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!" + sys.executable + "\n" +
        "from test_principal_integration import fixture_configuration, _fixture_stage_command\n" +
        "import base64\nfrom pathlib import Path\n" +
        "config=fixture_configuration(Path(" + repr(str(config.sd_root.parent)) + "))\n" +
        "_fixture_stage_command(config,base64.b64decode(" + repr(base64.b64encode(raw).decode()) + "))\n")
    launcher.chmod(0o700)
    from bridge.principal import PrincipalBoundary
    PrincipalBoundary(config).run_pyui()
    return FrontendHealth(config.state_dir), ForegroundIdentity.from_health(FrontendHealth(config.state_dir))


def _fixture_stage_command(config, raw):
    health = FrontendHealth(config.state_dir)
    health.begin_foreground("host-fixture-command")
    foreground = ForegroundIdentity.from_health(health)
    # This is correlation input, not completion evidence. Only the real
    # child-subreaper operation below can produce a sealed completion object.
    config.staged_command.write_bytes(raw)
    _atomic(config.state_dir / "principal-source-command.json", {"schema": 1,
        "foreground": asdict(foreground), "command_sha256": hashlib.sha256(raw).hexdigest(),
        "source_pid": 2147483646, "source_start": "123", "source_game": None, "state_intent": None})
    return health, foreground


class PrincipalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="principal-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_code(self, body, *, expected=0):
        prefix = """
import json, os, sys, time, signal
from pathlib import Path
from unittest.mock import patch
from test_principal_integration import fixture_configuration, fixture_pending_command
from bridge.principal import PrincipalBoundary, PrincipalCompletion, OwnedTreeCompletion, run_owned_tree
from bridge.process_source import COMMAND_REQUEST
from psp_shell.runtime import ContractError
ROOT=Path(sys.argv[1])
config=fixture_configuration(ROOT)
"""
        env = dict(os.environ, PYTHONPATH=str(PROJECT) + os.pathsep + str(PROJECT / "tests"))
        result = subprocess.run([sys.executable, "-c", textwrap.dedent(prefix) + textwrap.dedent(body), str(self.root)],
                                env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_real_kernel_child_exit_and_signal_results_are_sealed(self):
        self.run_code(r"""
for code, expected in [('raise SystemExit(7)', 7), ('import os,signal; os.kill(os.getpid(),signal.SIGTERM)', -15)]:
    result=run_owned_tree([sys.executable,'-c',code])
    assert result.exit_status==expected and result.children_reaped==1
for tree in [OwnedTreeCompletion(1,0,1,object()), {'exit_status':0}]:
    value=PrincipalCompletion(None,'a'*64,tree,'fixture',object())
    try: value.spruce_return()
    except ContractError: pass
    else: raise AssertionError('forged completion accepted')
""")

    def test_reviewed_syscall_fallback_creates_and_verifies_seals_without_new_libc(self):
        self.run_code(r"""
from bridge.principal import _sealed_script
with patch('bridge.principal.os.memfd_create',None,create=True):
    fd=_sealed_script(b'exit 0\n')
try:
    try: os.write(fd,b'changed')
    except OSError: pass
    else: raise AssertionError('unsealed fallback descriptor')
finally: os.close(fd)
with patch('bridge.principal.os.memfd_create',None,create=True),patch('bridge.principal.platform.machine',return_value='unreviewed'):
    try: _sealed_script(b':')
    except ContractError as error: assert error.code=='SOURCE_CAPABILITY_UNAVAILABLE'
    else: raise AssertionError('unknown syscall ABI used')
""")

    def test_double_fork_setsid_descendant_delays_completion_and_closes_resource(self):
        self.run_code(r"""
owned=ROOT/'owned-resource'
source='''import os,time,sys
fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT,0o600)
if os.fork(): os._exit(0)
os.setsid()
if os.fork(): os._exit(0)
time.sleep(0.2)
os.write(fd,b'closed after descendants')
os.close(fd)
os._exit(0)
'''
started=time.monotonic()
result=run_owned_tree([sys.executable,'-c',source,str(owned)])
assert time.monotonic()-started>=0.15
assert result.children_reaped==3 and owned.read_bytes()==b'closed after descendants'
""")

    def test_foreign_children_and_launch_failure_cannot_issue_completion(self):
        self.run_code(r"""
import subprocess
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.1)'])
try:
    try: run_owned_tree([sys.executable,'-c','pass'])
    except ContractError as error: assert error.code=='FOREIGN_CHILD'
    else: raise AssertionError('unrelated child ignored')
finally: child.wait()
try: run_owned_tree(['/definitely-missing-source-launcher'])
except OSError: pass
else: raise AssertionError('failed launch completed')
""")

    def test_actual_boundary_preserves_script_zero_lexical_launcher_and_clears_exact_request(self):
        self.run_code(r"""
script='printf "%s\\n" "$0" > "'+str(ROOT/'zero')+'"; printf "%s" "${1-unset}" > "'+str(ROOT/'one')+'"; exit 9\n'
health,expected=fixture_pending_command(config,script.encode())
result,completion=PrincipalBoundary(config).run_command()
assert result.exit_status==9 and completion.foreground==expected
assert completion.spruce_return().foreground==expected
assert (ROOT/'zero').read_text().strip()==str(config.staged_command)
assert (ROOT/'one').read_text()=='unset'
assert health.foreground_identity() is None
assert not config.staged_command.exists() and not (config.state_dir/COMMAND_REQUEST).exists()
""")

    def test_command_replacement_at_atomic_consumption_is_preserved_and_never_clears(self):
        self.run_code(r"""
health,expected=fixture_pending_command(config,b'exit 0\n')
original_rename=os.rename
def replace_at_take(source,target,*args,**kwargs):
    if Path(source)==config.staged_command:
        replacement=ROOT/'replacement'
        replacement.write_bytes(b'printf replacement\n')
        os.replace(replacement,config.staged_command)
    return original_rename(source,target,*args,**kwargs)
with patch('bridge.principal.os.rename',side_effect=replace_at_take):
    try: PrincipalBoundary(config).run_command()
    except ContractError as error: assert error.code=='STAGED_COMMAND_CHANGED'
    else: raise AssertionError('replacement silently consumed')
assert config.staged_command.read_bytes()==b'printf replacement\n'
assert health.foreground_identity() is not None
""")

    def test_qualified_environment_and_completion_callbacks_share_actual_owned_lifetime(self):
        self.run_code(r"""
from test_principal_integration import fixture_configuration
events=[]
def environment(identity,request):
    assert identity==request.foreground
    events.append('environment')
    return {'TRIMUI_PROJECT_STATE_REQUEST':str(ROOT/'private-request'),'TRIMUI_PROJECT_RESUME_STATE':''}
def completed(value):
    assert value.spruce_return().foreground==value.foreground
    events.append('complete')
config=fixture_configuration(ROOT,command_environment=environment,completion_observer=completed)
health,expected=fixture_pending_command(config,('printf "%s" "$TRIMUI_PROJECT_STATE_REQUEST" > "'+str(ROOT/'scope')+'"\n').encode())
PrincipalBoundary(config).run_command()
assert events==['environment','complete'] and (ROOT/'scope').read_text()==str(ROOT/'private-request')
assert health.foreground_identity() is None
""")

    def test_failed_completion_observer_and_replaced_foreground_keep_tombstone(self):
        self.run_code(r"""
from test_principal_integration import fixture_configuration
def failed(_): raise ValueError('fixture observer failure')
config=fixture_configuration(ROOT,completion_observer=failed)
health,expected=fixture_pending_command(config,b'exit 0\n')
try: PrincipalBoundary(config).run_command()
except ValueError: pass
else: raise AssertionError('observer failure accepted')
assert health.foreground_identity() is not None
""")

    def test_killed_source_helper_cannot_reauthorize_orphaned_owner_from_dead_source_pid(self):
        self.run_code(r"""
import subprocess
from bridge.principal import _subreaper
from psp_shell.health import FrontendHealth
from test_principal_integration import _fixture_stage_command
source=ROOT/'source.py'
source.write_text('''import os,sys,time
from pathlib import Path
from test_principal_integration import fixture_configuration,_fixture_stage_command
root=Path(sys.argv[1]);config=fixture_configuration(root)
_fixture_stage_command(config,('printf launched > '+str(root/'should-not-run')+'\\n').encode())
if os.fork(): os._exit(0)
os.setsid()
ready=root/'escaped-pid';pending=ready.with_suffix('.pending')
pending.write_text(str(os.getpid()));pending.replace(ready)
while not (root/'release-owner').exists(): time.sleep(.01)
''')
launch=config.sd_root/'App/PyUI/launch.sh';launch.parent.mkdir(parents=True)
import shlex
launch.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(source))+' '+shlex.quote(str(ROOT))+'\n');launch.chmod(0o700)
previous=_subreaper(True)
helper=subprocess.Popen([sys.executable,'-c','from pathlib import Path;import sys;from test_principal_integration import fixture_configuration;from bridge.principal import PrincipalBoundary;PrincipalBoundary(fixture_configuration(Path(sys.argv[1]))).run_pyui()',str(ROOT)])
try:
    # Wait for completed source staging and a fully published orphan PID before
    # testing helper death; imports and fsyncs are fixture setup, not the contract.
    ready=ROOT/'escaped-pid';deadline=time.monotonic()+6
    while not ready.exists() and helper.poll() is None and time.monotonic()<deadline: time.sleep(.01)
    assert helper.poll() is None, f'source helper exited before orphan readiness: {helper.returncode}'
    assert ready.is_file(), 'source helper did not publish orphan readiness within 6s'
    escaped=int(ready.read_text())
    helper.kill();helper.wait()
    health=FrontendHealth(config.state_dir)
    assert health.foreground_identity() is not None
    try: PrincipalBoundary(config).run_command()
    except ContractError as error: assert error.code=='SOURCE_CLOSURE_UNVERIFIED'
    else: raise AssertionError('dead source PID minted missing subtree completion')
    assert not (ROOT/'should-not-run').exists() and health.foreground_identity() is not None
finally:
    (ROOT/'release-owner').touch()
    helper.wait()
    if 'escaped' in locals(): os.waitpid(escaped,0)
    _subreaper(previous)
""")

    def test_classic_dirty_source_survives_killed_principal_lifetime(self):
        self.run_code(r"""
import subprocess,shlex
from bridge.principal import _subreaper
source=ROOT/'classic-source.py'
source.write_text('''import os,sys,time
from pathlib import Path
root=Path(sys.argv[1]);(root/'cmd_to_run.sh').write_text('printf launched > '+str(root/'should-not-run')+'\\n')
if os.fork(): os._exit(0)
os.setsid();(root/'escaped-pid').write_text(str(os.getpid()))
while not (root/'release-owner').exists(): time.sleep(.01)
''')
launch=config.sd_root/'App/PyUI/launch.sh';launch.parent.mkdir(parents=True)
launch.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(source))+' '+shlex.quote(str(ROOT))+'\n');launch.chmod(0o700)
helper_code='from pathlib import Path;import sys;from test_principal_integration import fixture_configuration;from bridge.principal import PrincipalBoundary;PrincipalBoundary(fixture_configuration(Path(sys.argv[1]))).run_pyui()'
principal_code='import subprocess,sys;from pathlib import Path;p=subprocess.Popen([sys.executable,"-c",sys.argv[2],sys.argv[1]]);Path(sys.argv[1],"helper-pid").write_text(str(p.pid));p.wait()'
previous=_subreaper(True)
principal=subprocess.Popen([sys.executable,'-c',principal_code,str(ROOT),helper_code])
try:
    deadline=time.monotonic()+3
    while not (ROOT/'escaped-pid').exists() and time.monotonic()<deadline: time.sleep(.01)
    escaped=int((ROOT/'escaped-pid').read_text());helper=int((ROOT/'helper-pid').read_text())
    principal.kill();principal.wait();os.kill(helper,signal.SIGKILL);os.waitpid(helper,0)
    assert (config.private_runtime/'dirty').exists()
    assert __import__('psp_shell.health',fromlist=['FrontendHealth']).FrontendHealth(config.state_dir).foreground_identity() is None
    try: PrincipalBoundary(config).run_command()
    except ContractError as error: assert error.code=='SOURCE_CLOSURE_UNVERIFIED'
    else: raise AssertionError('fresh principal reused an orphaned classic command')
    assert not (ROOT/'should-not-run').exists()
finally:
    (ROOT/'release-owner').touch()
    principal.wait()
    if 'escaped' in locals(): os.waitpid(escaped,0)
    _subreaper(previous)
""")

    def test_killed_classic_command_helper_blocks_new_source_even_when_command_file_disappears(self):
        self.run_code(r"""
import subprocess,shlex
from bridge.principal import _subreaper
game=ROOT/'classic-game.py'
game.write_text('''import os,sys,time
from pathlib import Path
root=Path(sys.argv[1])
if os.fork(): os._exit(0)
os.setsid();(root/'escaped-pid').write_text(str(os.getpid()))
while not (root/'release-owner').exists(): time.sleep(.01)
''')
config.staged_command.write_text(shlex.quote(sys.executable)+' '+shlex.quote(str(game))+' '+shlex.quote(str(ROOT))+'\n')
previous=_subreaper(True)
helper=subprocess.Popen([sys.executable,'-c','from pathlib import Path;import sys;from test_principal_integration import fixture_configuration;from bridge.principal import PrincipalBoundary;PrincipalBoundary(fixture_configuration(Path(sys.argv[1]))).run_command()',str(ROOT)])
try:
    deadline=time.monotonic()+3
    while not (ROOT/'escaped-pid').exists() and time.monotonic()<deadline: time.sleep(.01)
    escaped=int((ROOT/'escaped-pid').read_text())
    helper.kill();helper.wait();config.staged_command.unlink()
    try: PrincipalBoundary(config).run_pyui()
    except ContractError as error: assert error.code=='SOURCE_CLOSURE_UNVERIFIED'
    else: raise AssertionError('in-flight classic command was considered complete')
    assert (config.private_runtime/'dirty').exists()
finally:
    (ROOT/'release-owner').touch();helper.wait()
    if 'escaped' in locals(): os.waitpid(escaped,0)
    _subreaper(previous)
""")

    def test_private_source_closure_can_be_consumed_by_only_one_competing_helper(self):
        self.run_code(r"""
import threading
from bridge.resident import PrincipalLease
from psp_shell.health import FrontendHealth
health,expected=fixture_pending_command(config,('printf once >> '+str(ROOT/'launch-count')+'\n').encode())
barrier=threading.Barrier(2);consume=PrincipalLease.consume_source;results=[]
# Exercise closure consumption after both real health reads complete. The
# health lock intentionally rejects concurrent readers before this seam.
foreground_lock=threading.Lock();read_foreground=FrontendHealth.foreground_identity
def serialized_foreground(self):
    with foreground_lock:return read_foreground(self)
def synchronized(self,*args): barrier.wait(timeout=3);return consume(self,*args)
def command(boundary):
    try: boundary.run_command();results.append('complete')
    except ContractError as error: results.append(error.code)
boundaries=[PrincipalBoundary(config) for _ in range(2)]
with patch.object(FrontendHealth,'foreground_identity',serialized_foreground),patch.object(PrincipalLease,'consume_source',synchronized):
    threads=[threading.Thread(target=command,args=(boundary,)) for boundary in boundaries]
    for thread in threads:thread.start()
    for thread in threads:thread.join(timeout=5)
assert sorted(results)==['SOURCE_CLOSURE_UNVERIFIED','complete'],results
assert (ROOT/'launch-count').read_text()=='once' and health.foreground_identity() is None
assert not (config.private_runtime/'dirty').exists()
""")

    def test_disabled_fixed_runtime_keeps_boot_global_dirty_guard(self):
        self.run_code(r"""
from bridge.principal import main
dirty=ROOT/'dirty';dirty.touch()
with patch('bridge.principal.configured_runtime',return_value=None),patch('bridge.resident.DIRTY_GUARD',dirty):
    assert main(['status'])==125
""")


class ProcessSourceAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (SOURCE / MIYOO).is_file():
            raise unittest.SkipTest("Untouched pinned spruce source not available; set SPRUCE_SOURCE_ROOT")
        cls.temp = tempfile.TemporaryDirectory(prefix="process-source-acceptance-")
        cls.root = Path(cls.temp.name)
        cls.stage, cls.patched = cls.root / "stage", cls.root / "patched"
        cls.record = stage_process_exit_integration(SOURCE, cls.stage, source_use_verified=True)
        for name in cls.record["changed_paths"]:
            target = cls.patched / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, target)
        subprocess.run(["git", "apply", str(cls.stage / cls.record["patch"])], cwd=cls.patched, check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temp"):
            cls.temp.cleanup()

    def test_complete_alternative_is_exact_source_gated_and_uses_fixed_payload_root(self):
        self.assertEqual(len(self.record["sources"]), len(SOURCE_BLOBS))
        self.assertTrue(self.record["supplies_main_menu_hook"])
        self.assertFalse(self.record["requires_legacy_lifecycle_hook"])
        self.assertFalse(self.record["hardware_execution_enabled"])
        for row in self.record["transformed"]:
            self.assertEqual(hashlib.sha256((self.patched / row["path"]).read_bytes()).hexdigest(), row["patched_sha256"])
        subprocess.run(["sh", "-n", str(self.patched / "spruce/scripts/principal.sh")], check=True)
        with self.assertRaises(Exception):
            stage_process_exit_integration(SOURCE, self.root / "never-produced")
        with self.assertRaises(Exception):
            stage_process_exit_integration(SOURCE, self.root / "bad-path", source_use_verified=True,
                                          module_root="/mnt/SDCARD/../untrusted")

    def test_main_menu_prelude_and_original_source_worker_exit_are_preserved(self):
        text = (self.patched / "App/PyUI/main-ui/menus/main_menu.py").read_text()
        self.assertLess(text.index("game_selection_only_mode_enabled"), text.index("maybe_run_main_menu(self)"))
        self.assertLess(text.index("self.check_for_gameswitcher()"), text.index("maybe_run_main_menu(self)"))
        self.assertLess(text.index("self.check_for_boxart_resizing()"), text.index("maybe_run_main_menu(self)"))
        mainui = (self.patched / "App/PyUI/main-ui/mainui.py").read_text()
        self.assertNotIn("stop_event", mainui)
        self.assertIn("bind_initialized_source(main_menu, project_tasks, get_rom_select_options_builder())", mainui)
        self.assertIn("sys.exit()", (SOURCE / "App/PyUI/main-ui/devices/device_common.py").read_text())

    def test_actual_transformed_principal_blocks_before_a_second_owner_on_uncertain_source(self):
        with tempfile.TemporaryDirectory(prefix="principal-shell-boundary-") as temporary:
            root = Path(temporary)
            helpers = root / "helpers.sh"
            helpers.write_text('''
log_message() { :; }
flag_remove() { :; }
flag_add() { :; }
flag_check() { return 1; }
set_smart() { :; }
stop_pyui_message_writer() { :; }
enable_or_disable_rgb() { :; }
set_rgb_in_menu() { :; }
set_network_proxy() { :; }
display_kill() { :; }
low_battery_check() { :; }
prepare_for_pyui_launch() { :; }
log_activity_event() { :; }
''')
            modules = root / "modules/bridge"
            modules.mkdir(parents=True)
            (modules / "principal.py").write_text("# fixture module-presence check only\n")
            guard = root / "guard.py"
            guard.write_text("#!" + sys.executable + "\n" + textwrap.dedent('''
                import sys, time
                from pathlib import Path
                root = Path(__file__).parent
                operation = sys.argv[1]
                with (root / "calls").open("a") as calls:
                    calls.write(operation + "\\n")
                started = root / "resident-started"
                if operation == "resident":
                    started.touch()
                elif operation == "resident-ready":
                    # A real startup observation, not an immediate fake success:
                    # pyui must not run until the background fixture has logged.
                    deadline = time.monotonic() + 2
                    while not started.exists():
                        if time.monotonic() >= deadline:
                            raise SystemExit("Fixture resident did not start before readiness deadline")
                        time.sleep(0.005)
                raise SystemExit(0 if operation in {"status", "resident", "resident-ready"}
                                 else 125 if operation == "pyui" else 99)
            '''))
            guard.chmod(0o700)
            text = (self.patched / "spruce/scripts/principal.sh").read_text()
            text = text.replace(". /mnt/SDCARD/spruce/scripts/helperFunctions.sh", ". " + str(helpers))
            text = text.replace(self.record["module_root"], str(root / "modules"))
            text = text.replace('PYTHONPATH="' + str(root / "modules") + '" /mnt/SDCARD/spruce/flip/bin/MainUI -m bridge.principal', str(guard))
            # The source failure branch exits before any framebuffer, storage,
            # emulator or post-PyUI command. Assert that actual shell behavior.
            result = subprocess.run(["sh", "-c", text], env=dict(os.environ, PLATFORM="SmartPro"),
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 125, result.stdout + result.stderr)
            calls = (root / "calls").read_text().splitlines()
            self.assertEqual(calls[0], "status")
            self.assertEqual(calls[-1], "pyui")
            self.assertCountEqual(calls[1:-1], ["resident", "resident-ready"])

    def test_actual_principal_dirty_guard_precedes_missing_module_or_disabled_fallback(self):
        with tempfile.TemporaryDirectory(prefix="principal-no-module-dirty-") as temporary:
            root = Path(temporary)
            helper = root / "helpers.sh"; helper.write_text("log_message() { :; }\n")
            dirty = root / "runtime/dirty"; dirty.parent.mkdir(); dirty.touch()
            text = (self.patched / "spruce/scripts/principal.sh").read_text()
            text = text.replace(". /mnt/SDCARD/spruce/scripts/helperFunctions.sh", ". " + str(helper))
            text = text.replace("/tmp/trimui-project-principal/dirty", str(dirty))
            text = text.replace(self.record["module_root"], str(root / "missing-original-modules"))
            result = subprocess.run(["sh", "-c", text], env=dict(os.environ, PLATFORM="SmartPro"),
                capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 125, result.stdout + result.stderr)

    def test_actual_transformed_game_stages_correlated_model_request_and_runs_original_launcher(self):
        with tempfile.TemporaryDirectory(prefix="source-model-session-") as temporary:
            root = Path(temporary)
            fixture = root / "source.py"
            fixture.write_text(textwrap.dedent('''
                import ast,json,os,sys,threading
                from pathlib import Path
                from types import SimpleNamespace
                from test_principal_integration import fixture_configuration
                from bridge import process_source
                from psp_shell.health import FrontendHealth
                ROOT=Path(sys.argv[1]); config=fixture_configuration(ROOT)
                process_source.configured_runtime=lambda: config
                device=SimpleNamespace(perform_startup_tasks=lambda:None,watch_audio_route=lambda:None,
                    fix_sleep_sound_bug=lambda:None,exit_pyui=lambda:sys.exit(0))
                tasks=process_source.begin_process_source_tasks(device,lambda:None)
                tasks._startup.thread.join();tasks._managers.thread.join()
                tasks.stop_background_tasks();tasks.release_input()
                FrontendHealth(config.state_dir).begin_foreground('host-fixture-source-game')
                system=config.sd_root/'Emu/PSP';system.mkdir(parents=True)
                rom=config.sd_root/'Roms/PSP/owner.iso';rom.parent.mkdir(parents=True);rom.write_bytes(b'owner fixture')
                game=SimpleNamespace(system_name='PSP',game_system_config=SimpleNamespace(
                    get_emu_folder=lambda:str(system),get_launch=lambda:'../../spruce/scripts/emu/standard_launch.sh'))
                model=SimpleNamespace(rom_file_path=str(rom),game_system=game)
                source=ast.parse(Path(sys.argv[2]).read_text())
                methods=[n for n in ast.walk(source) if isinstance(n,ast.FunctionDef) and n.name in ('write_cmd_to_run','run_game')]
                for n in methods:n.decorator_list=[]
                namespace={'RomInfo':object,'subprocess':__import__('subprocess'),'os':os,'re':__import__('re'),
                    'Theme':SimpleNamespace(check_and_create_ra_assets=lambda:None),
                    'Display':SimpleNamespace(deinit_display=lambda:None),
                    'Device':SimpleNamespace(get_device=lambda:device)}
                exec(compile(ast.Module(body=methods,type_ignores=[]),'<actual transformed source game>','exec'),namespace)
                namespace['MiyooTrimCommon']=SimpleNamespace(write_cmd_to_run=namespace['write_cmd_to_run'])
                namespace['run_game'](device,model)
            '''))
            env = dict(os.environ, PYTHONPATH=str(PROJECT) + os.pathsep + str(PROJECT / "tests"))
            launch = root / "card/App/PyUI/launch.sh"
            launch.parent.mkdir(parents=True)
            import shlex
            launch.write_text("#!/bin/sh\nexec " + " ".join(shlex.quote(v) for v in
                [sys.executable, str(fixture), str(root), str(self.patched / MIYOO)]) + "\n")
            launch.chmod(0o700)
            boundary = 'from pathlib import Path;from test_principal_integration import fixture_configuration;from bridge.principal import PrincipalBoundary;import sys;PrincipalBoundary(fixture_configuration(Path(sys.argv[1])))'
            subprocess.run([sys.executable, "-c", boundary + ".run_pyui()", str(root)],
                           env=env, check=True, capture_output=True, timeout=5)
            request = json.loads((root / "state/principal-source-command.json").read_text())
            self.assertEqual(request["source_game"], {"rom_relative": "Roms/PSP/owner.iso", "system_id": "PSP"})
            launcher = root / "card/spruce/scripts/emu/standard_launch.sh"
            launcher.parent.mkdir(parents=True)
            launcher.write_text('#!/bin/sh\nprintf "%s" "$0" > "' + str(root / "lexical") + '"\n')
            result = subprocess.run([sys.executable, "-c", boundary + ".run_command()", str(root)], env=env, text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Emu/PSP/../../spruce/scripts/emu/standard_launch.sh", (root / "lexical").read_text())
            self.assertIsNone(FrontendHealth(root / "state").foreground_identity())

    def test_actual_bluetooth_worker_delegates_persistent_watcher_without_blocking_game(self):
        with tempfile.TemporaryDirectory(prefix="resident-bt-source-fixture-") as temporary:
            environment = dict(os.environ, PYTHONPATH=str(PROJECT) + os.pathsep + str(PROJECT / "tests"))
            result = subprocess.run([sys.executable, str(PROJECT / "tests/resident_fixture.py"), temporary,
                str(self.patched / "App/PyUI/main-ui/devices/device_common.py"),
                str(SOURCE / "spruce/scripts/bluetooth.sh")], env=environment, text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_actual_calibration_service_toggle_and_task_seams_preserve_original_followup(self):
        """Use actual transformed methods; delegation is the named fixture seam."""
        import shlex
        from bridge import resident
        from psp_shell.runtime import ContractError
        events = []
        def delegated(operation, arguments=(), **kwargs):
            events.append((operation, list(arguments)))
            return True
        def unexpected(*args, **kwargs):
            raise AssertionError("source started a resident service under its foreground")
        with tempfile.TemporaryDirectory(prefix="resident-source-seams-") as temporary:
            root = Path(temporary)
            config = fixture_configuration(root)
            with patch("bridge.process_source.configured_runtime", return_value=config), patch("bridge.resident.delegate", side_effect=delegated):
                tree = ast.parse((self.patched / "App/PyUI/main-ui/devices/trimui/trim_ui_smart_pro.py").read_text())
                function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "apply_stick_calibration")
                namespace = {"os": os, "subprocess": SimpleNamespace(run=unexpected)}
                exec(compile(ast.Module(body=[function], type_ignores=[]), "<actual source calibration>", "exec"), namespace)
                event = root / "fixture-event"; event.write_bytes(b"fixture")
                old_fd = os.open(event, os.O_RDONLY | os.O_NONBLOCK)
                watcher = SimpleNamespace(fd=old_fd, event_path=str(event))
                namespace["apply_stick_calibration"](SimpleNamespace(volume_key_watcher=watcher))
                self.assertNotEqual(watcher.fd, old_fd)
                with self.assertRaises(OSError):
                    os.fstat(old_fd)
                os.close(watcher.fd)
                tree = ast.parse((self.patched / "App/PyUI/main-ui/utils/cfw_system_config.py").read_text())
                source_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CfwSystemConfig")
                namespace = {"json": json, "shlex": shlex, "subprocess": SimpleNamespace(run=unexpected),
                    "PyUiLogger": SimpleNamespace(get_logger=lambda: SimpleNamespace(error=unexpected))}
                exec(compile(ast.Module(body=[source_class], type_ignores=[]), "<actual source CFW settings>", "exec"), namespace)
                cfw = namespace["CfwSystemConfig"]
                cfw._config_path = str(root / "cfw.json")
                cfw._data = {"menuOptions": {"network": {"ssh": {"selected": False, "changeCmd": resident.NETWORK_TOGGLE + " ssh"}}}}
                cfw.set_menu_option("network", "ssh", True)
                self.assertIs(cfw.get_selected_value("network", "ssh"), True)
                tree = ast.parse((self.patched / "App/PyUI/main-ui/option_select_ui.py").read_text())
                action = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_action")
                ui_events = []
                namespace = {"exit_after_running": False, "execute_immediately": True, "run_source_shell": resident.run_source_shell,
                    "Display": SimpleNamespace(display_message=lambda *a, **k: ui_events.append("message"), reinitialize=lambda: ui_events.append("display")),
                    "Controller": SimpleNamespace(clear_input_queue=lambda: ui_events.append("input"))}
                exec(compile(ast.Module(body=[action], type_ignores=[]), "<actual source task action>", "exec"), namespace)
                namespace["run_action"](resident.SCRIPT_PREFIX + "tasks/clearwifi.sh")
                self.assertEqual(ui_events, ["message", "input", "display", "message"])
                self.assertEqual(events, [("input-calibration", []), ("network-service", ["ssh", "True"]), ("task", ["clearwifi.sh"])])
            with patch("bridge.process_source.configured_runtime", return_value=config):
                with self.assertRaises(ContractError):
                    resident.delegate_radio("wifi", "/unreviewed/command", ("apply",))
                with self.assertRaises(ContractError):
                    resident.delegate_known_command([resident.NETWORK_TOGGLE, "ssh", "True; other-command"])


class InitializedSourceBindingTests(unittest.TestCase):
    def test_fixed_factory_wraps_initialized_models_renders_and_reuses_existing_advanced_authorities(self):
        from bridge import process_source
        from bridge.pyui_entry import bind_context_factory
        from psp_shell.embedded import EmbeddedDependencies, EmbeddedRunner, qualification
        events = []
        ready = threading.Event()
        ready.set()
        device = SimpleNamespace(perform_startup_tasks=lambda: events.append("source-startup"),
            watch_audio_route=lambda: None, run_game=lambda _: self.fail("unexpected game launch"))
        systems = SimpleNamespace(get_active_systems=lambda: [], get_game_system_by_name=lambda _: None)
        device.get_game_system_utils = lambda: systems
        display = SimpleNamespace(renderer=SimpleNamespace(renderer=object()),
            window=SimpleNamespace(window=object()), present=lambda: events.append("present"))
        controller = SimpleNamespace(get_input=lambda **_: False, still_held_down=lambda: False,
            clear_input_queue=lambda: None, clear_last_input=lambda: None, last_input=lambda: None)
        favorites = SimpleNamespace(_init_event=ready, get_favorites=lambda: [],
            initialize=lambda *_: self.fail("history reinitialized"))
        recents = SimpleNamespace(_init_event=ready, get_recents=lambda: [],
            initialize=lambda *_: self.fail("history reinitialized"))
        collections = SimpleNamespace(_init_event=ready, get_collection_names=lambda: [], get_games_in_collection=lambda _: [],
            initialize=lambda *_: self.fail("collections reinitialized"))
        builder = SimpleNamespace(rom_utils=SimpleNamespace(get_roms=lambda *_: ([], [])),
            resolve_display_name=lambda value: "fixture", get_image_path=lambda value: None)
        popup = lambda _: events.append("game-options")
        menu = SimpleNamespace(favorites_menu=SimpleNamespace(popup_menu=SimpleNamespace(run_game_select_popup_menu=popup)),
            launch_selection=lambda value: events.append("advanced:" + value),
            settings_menu=SimpleNamespace(wifi_menu=SimpleNamespace(show_wifi_menu=lambda: events.append("wifi")),
                bt_menu=SimpleNamespace(show_bluetooth_menu=lambda: events.append("bluetooth"))))
        modules = {name: SimpleNamespace() for name in ("devices", "display", "controller", "menus", "menus.games", "menus.games.utils")}
        modules.update({"devices.device": SimpleNamespace(Device=SimpleNamespace(get_device=lambda: device)),
            "display.display": SimpleNamespace(Display=display), "controller.controller": SimpleNamespace(Controller=controller),
            "menus.games.utils.favorites_manager": SimpleNamespace(FavoritesManager=favorites),
            "menus.games.utils.recents_manager": SimpleNamespace(RecentsManager=recents),
            "menus.games.utils.collections_manager": SimpleNamespace(CollectionsManager=collections),
            "menus.games.utils.rom_info": SimpleNamespace(RomInfo=lambda system, path: SimpleNamespace(game_system=system, rom_file_path=path))})
        class Renderer:
            def __init__(self, *_, **kwargs):
                self_outer.assertFalse(kwargs["own_resources"])
                self_outer.assertIs(kwargs["external_renderer"], display.renderer.renderer)
            def render(self, *_): events.append("render")
            def close(self): events.append("close-presentation")
        self_outer = self
        with tempfile.TemporaryDirectory(prefix="initialized-source-") as temporary:
            config = fixture_configuration(Path(temporary))
            with patch.dict(sys.modules, modules), patch.object(process_source, "configured_runtime", return_value=config), \
                    patch.object(process_source, "_source_tasks", None):
                tasks = process_source.begin_process_source_tasks(device, lambda: events.append("source-managers"))
                tasks._startup.thread.join(1)
                tasks._managers.thread.join(1)
                binding = process_source.bind_initialized_source(menu, tasks, builder)
                self.addCleanup(bind_context_factory, None)
                context = binding(menu)
                qualification(context).assert_safe()
                self.assertIs(context.game_options_handler, popup)
                health = FrontendHealth(config.state_dir)
                health.request("project", 0)
                runner = EmbeddedRunner(context, health=health, dependencies=EmbeddedDependencies(renderer_factory=Renderer))
                result = runner.run(max_frames=1)
                self.assertTrue(result.first_frame)
                self.assertIs(runner.backend.provider.favorites_manager, favorites)
                self.assertTrue(runner.dispatcher.dispatch("system.capabilities")["game_options"])
                for route in ("wifi", "bluetooth"):
                    runner.open_advanced(route)
                    self.assertIn(route, events)
                with tasks.write_window():
                    with self.assertRaises(Exception):
                        tasks.stop_background_tasks()
                self.assertEqual(events.count("source-startup"), 1)
                self.assertEqual(events.count("source-managers"), 1)


if __name__ == "__main__":
    unittest.main()
