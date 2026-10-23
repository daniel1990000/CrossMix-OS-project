"""Real Linux process ownership under cooperative observation deadlines.

Each ownership case runs in a fresh host helper. No target binary, source
installation, device, power operation or user content is executed.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

from bridge.principal import TreeObservationPolicy
from psp_shell.runtime import ContractError


PROJECT = Path(__file__).resolve().parents[1]


class PrincipalObservationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="principal-observation-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def helper(self, body):
        prefix = """
import json, os, sys, time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from bridge.principal import (TreeObservationPolicy, TreeBlockedObservation,
                              run_owned_tree, _subreaper)
from bridge.process_source import process_start
from psp_shell.runtime import ContractError
ROOT = Path(sys.argv[1])
"""
        environment = dict(os.environ, PYTHONPATH=str(PROJECT) + os.pathsep + str(PROJECT / "tests"))
        result = subprocess.run([sys.executable, "-c", textwrap.dedent(prefix) + textwrap.dedent(body), str(self.root)],
                                env=environment, text=True, capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_policy_rejects_invalid_deadlines_callbacks_and_polling(self):
        for deadline in (True, None, "5", float("nan"), float("inf"), -1, 0):
            with self.subTest(deadline=deadline), self.assertRaises(ContractError) as caught:
                TreeObservationPolicy(deadline, lambda _: None)
            self.assertEqual(caught.exception.code, "INVALID_OBSERVATION")
        for interval in (False, None, "0.1", float("nan"), 0, 0.001, 0.251):
            with self.subTest(interval=interval), self.assertRaises(ContractError):
                TreeObservationPolicy(time.monotonic() + 1, lambda _: None, interval)
        with self.assertRaises(ContractError):
            TreeObservationPolicy(time.monotonic() + 1, None)

    def test_untyped_and_expired_policy_never_start_a_source(self):
        self.helper("""
for value, code in [({}, 'INVALID_OBSERVATION'),
                    (TreeObservationPolicy(time.monotonic() - 1, lambda _: None), 'OBSERVATION_EXPIRED')]:
    with patch('bridge.principal.subprocess.Popen') as start:
        try: run_owned_tree([sys.executable, '-c', 'pass'], observation=value)
        except ContractError as error: assert error.code == code
        else: raise AssertionError('unadmitted source started')
        start.assert_not_called()
""")

    def test_missing_helper_identity_refuses_before_start(self):
        self.helper("""
with patch('bridge.principal.process_start', return_value=None), patch('bridge.principal.subprocess.Popen') as start:
    try: run_owned_tree([sys.executable, '-c', 'pass'],
                        observation=TreeObservationPolicy(time.monotonic() + 1, lambda _: None))
    except ContractError as error: assert error.code == 'SOURCE_CAPABILITY_UNAVAILABLE'
    else: raise AssertionError('unidentified helper started')
    start.assert_not_called()
""")

    def test_default_wait_preserves_completion_and_nonzero_status(self):
        self.helper("""
before = _subreaper()
result = run_owned_tree([sys.executable, '-c', 'raise SystemExit(7)'])
assert result.exit_status == 7 and result.children_reaped == 1
assert _subreaper() == before
""")

    def test_timely_observed_exit_has_completion_and_no_blocked_event(self):
        self.helper("""
events = []
before = _subreaper()
result = run_owned_tree([sys.executable, '-c', 'raise SystemExit(9)'],
    observation=TreeObservationPolicy(time.monotonic() + 3, events.append, .01))
assert result.exit_status == 9 and result.children_reaped == 1 and events == []
assert _subreaper() == before
""")

    def test_expiry_reports_live_owner_once_then_waits_without_completion(self):
        self.helper("""
events = []
before = _subreaper()
started = time.monotonic()
def observe(event):
    assert type(event) is TreeBlockedObservation
    assert event.helper_pid == os.getpid() and event.helper_start == process_start(os.getpid())
    assert event.root_start == process_start(event.root_pid)
    os.kill(event.root_pid, 0)  # Observation does not terminate the live owner.
    events.append(event)
try:
    run_owned_tree([sys.executable, '-c', 'import time; time.sleep(.25)', 'private-owner-secret'],
        observation=TreeObservationPolicy(time.monotonic() + .08, observe, .01))
except ContractError as error:
    assert error.code == 'OBSERVATION_BLOCKED'
    assert 'private-owner-secret' not in str(error)
else: raise AssertionError('expired observation issued completion')
assert len(events) == 1 and events[0].reason == 'deadline_expired'
assert events[0].observed_monotonic >= events[0].deadline_monotonic
assert not events[0].root_exit_observed
assert time.monotonic() - started >= .2
assert 'private-owner-secret' not in json.dumps(asdict(events[0]))
try: os.waitpid(-1, os.WNOHANG)
except ChildProcessError: pass
else: raise AssertionError('returned over a surviving child')
assert _subreaper() == before
""")

    def test_setsid_double_fork_survivor_retains_kernel_ownership(self):
        self.helper(r"""
source = '''import os,time
if os.fork(): os._exit(0)
os.setsid()
if os.fork(): os._exit(0)
time.sleep(.3)
os._exit(0)
'''
events = []
started = time.monotonic()
try:
    run_owned_tree([sys.executable, '-c', source],
        observation=TreeObservationPolicy(time.monotonic() + .1, events.append, .01))
except ContractError as error: assert error.code == 'OBSERVATION_BLOCKED'
else: raise AssertionError('surviving descendant admitted return')
assert len(events) == 1 and events[0].root_exit_observed
assert events[0].children_reaped == 2
assert time.monotonic() - started >= .25
try: os.waitpid(-1, os.WNOHANG)
except ChildProcessError: pass
else: raise AssertionError('orphan escaped subreaper')
""")

    def test_observer_failure_still_owns_tree_and_omits_private_error_text(self):
        self.helper("""
events = []
before = _subreaper()
def failed(event):
    events.append(event)
    raise OSError('private-observer-credential')
started = time.monotonic()
try:
    run_owned_tree([sys.executable, '-c', 'import time; time.sleep(.2)'],
        observation=TreeObservationPolicy(time.monotonic() + .05, failed, .01))
except ContractError as error:
    assert error.code == 'OBSERVATION_REPORT_FAILED'
    assert 'private-observer-credential' not in str(error)
else: raise AssertionError('failed journal admitted completion')
assert len(events) == 1 and time.monotonic() - started >= .15
assert _subreaper() == before
try: os.waitpid(-1, os.WNOHANG)
except ChildProcessError: pass
else: raise AssertionError('observer failure released a child')
""")

    def test_polling_sleeps_and_does_not_spin_while_child_lives(self):
        self.helper("""
real_sleep = time.sleep
delays = []
def slept(delay):
    assert 0 < delay <= .025
    delays.append(delay)
    real_sleep(delay)
with patch('bridge.principal.time.sleep', side_effect=slept):
    result = run_owned_tree([sys.executable, '-c', 'import time; time.sleep(.12)'],
        observation=TreeObservationPolicy(time.monotonic() + 3, lambda _: None, .025))
assert result.exit_status == 0 and 2 <= len(delays) < 30
""")

    def test_foreign_child_and_spawn_failure_do_not_issue_completion(self):
        self.helper("""
import subprocess
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(.1)'])
try:
    try: run_owned_tree([sys.executable, '-c', 'pass'],
                        observation=TreeObservationPolicy(time.monotonic() + 1, lambda _: None))
    except ContractError as error: assert error.code == 'FOREIGN_CHILD'
    else: raise AssertionError('foreign child ignored')
finally: child.wait()
before = _subreaper()
try: run_owned_tree(['/definitely-missing-observed-source'],
                    observation=TreeObservationPolicy(time.monotonic() + 1, lambda _: None))
except OSError: pass
else: raise AssertionError('failed spawn issued completion')
assert _subreaper() == before
""")

    def test_expired_source_observation_keeps_dirty_lease_after_true_exit(self):
        self.helper("""
from bridge.principal import PrincipalBoundary
from bridge.resident import PrincipalLease
from test_principal_integration import fixture_configuration
config = fixture_configuration(ROOT)
launcher = config.sd_root / 'App/PyUI/launch.sh'
launcher.parent.mkdir(parents=True)
launcher.write_text('#!' + sys.executable + '\\nimport time; time.sleep(.2)\\n')
launcher.chmod(0o700)
original = run_owned_tree
events = []
def observed(*args, **kwargs):
    return original(*args, **kwargs,
        observation=TreeObservationPolicy(time.monotonic() + .05, events.append, .01))
with patch('bridge.principal.run_owned_tree', side_effect=observed):
    try: PrincipalBoundary(config).run_pyui()
    except ContractError as error: assert error.code == 'OBSERVATION_BLOCKED'
    else: raise AssertionError('source lease closed after expiry')
assert len(events) == 1 and (config.private_runtime / 'dirty').exists()
assert PrincipalLease(config).global_state()['phase'] == 'source-running'
try: PrincipalBoundary(config).run_pyui()
except ContractError as error: assert error.code == 'SOURCE_CLOSURE_UNVERIFIED'
else: raise AssertionError('classic restarted over retained dirty lifetime')
""")

    def test_expired_command_observation_preserves_foreground_and_staged_bytes(self):
        self.helper("""
from bridge.principal import PrincipalBoundary
from bridge.resident import PrincipalLease
from bridge.bootstrap import ForegroundIdentity
from test_principal_integration import fixture_configuration, fixture_pending_command
config = fixture_configuration(ROOT)
raw = ('sleep .2\\n').encode()
health, foreground = fixture_pending_command(config, raw)
original = run_owned_tree
def observed(*args, **kwargs):
    return original(*args, **kwargs,
        observation=TreeObservationPolicy(time.monotonic() + .05, lambda _: None, .01))
with patch('bridge.principal.run_owned_tree', side_effect=observed):
    try: PrincipalBoundary(config).run_command()
    except ContractError as error: assert error.code == 'OBSERVATION_BLOCKED'
    else: raise AssertionError('command completed a failed admission')
assert ForegroundIdentity.from_health(health) == foreground
assert config.staged_command.read_bytes() == raw
assert (config.state_dir / 'principal-source-command.json').exists()
assert (config.private_runtime / 'dirty').exists()
assert PrincipalLease(config).global_state()['phase'] == 'command-running'
""")


if __name__ == "__main__":
    unittest.main()
