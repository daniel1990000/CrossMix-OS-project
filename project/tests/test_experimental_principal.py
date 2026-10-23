# SPDX-License-Identifier: MIT
"""Experimental observation does not replace kernel ownership completion."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class ExperimentalPrincipalObservationTests(unittest.TestCase):
    def helper(self, code):
        prefix = """import os,sys,time
from bridge.principal import run_owned_tree,TreeObservationPolicy,_subreaper
from psp_shell.runtime import ContractError
"""
        result = subprocess.run([sys.executable, "-c", prefix + code],
            env={**os.environ, "PYTHONPATH": str(PROJECT)}, capture_output=True,
            text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_released_observation_keeps_waiting_for_real_descendant_exit(self):
        self.helper("""
events=[]
before=_subreaper()
started=time.monotonic()
result=run_owned_tree([sys.executable,'-c','import time;time.sleep(.16)'],
    observation=TreeObservationPolicy(time.monotonic()+.04,events.append,.01,
                                      observation_active=lambda:False))
assert result.children_reaped==1 and result.exit_status==0
assert time.monotonic()-started>=.13 and events==[]
assert _subreaper()==before
try:os.waitpid(-1,os.WNOHANG)
except ChildProcessError:pass
else:raise AssertionError('kernel ownership was released early')
""")

    def test_failed_activity_read_cannot_issue_completion_after_eventual_exit(self):
        self.helper("""
events=[]
started=time.monotonic()
def failed():raise ValueError('private review data must not be logged')
try:
 run_owned_tree([sys.executable,'-c','import time;time.sleep(.14)'],
    observation=TreeObservationPolicy(time.monotonic()+1,events.append,.01,
                                      observation_active=failed))
except ContractError as error:
 assert error.code=='OBSERVATION_REPORT_FAILED'
 assert 'private review data' not in str(error)
else:raise AssertionError('failed observation issued completion')
assert len(events)==1 and events[0].reason=='observation_failed'
assert time.monotonic()-started>=.12
try:os.waitpid(-1,os.WNOHANG)
except ChildProcessError:pass
else:raise AssertionError('descendant still owns resources')
""")

    def test_activity_predicate_must_return_an_actual_boolean(self):
        self.helper("""
events=[]
try:
 run_owned_tree([sys.executable,'-c','pass'],
    observation=TreeObservationPolicy(time.monotonic()+1,events.append,.01,
                                      observation_active=lambda:1))
except ContractError as error:assert error.code=='OBSERVATION_REPORT_FAILED'
else:raise AssertionError('truthy metadata disabled the deadline')
assert len(events)==1 and events[0].reason=='observation_failed'
""")

    def test_deadline_failure_cannot_be_undone_by_later_release(self):
        self.helper("""
events=[]
calls=[]
def active():calls.append(1);return True
try:
 run_owned_tree([sys.executable,'-c','import time;time.sleep(.12)'],
    observation=TreeObservationPolicy(time.monotonic()+.035,events.append,.01,
                                      observation_active=active))
except ContractError as error:assert error.code=='OBSERVATION_BLOCKED'
else:raise AssertionError('expired case was completed')
assert len(events)==1 and events[0].reason=='deadline_expired'
assert len(calls)>=1
""")


class ExperimentalProcessCompositionTests(unittest.TestCase):
    def composition(self, mode):
        with tempfile.TemporaryDirectory(prefix="experimental-process-") as temporary:
            root = Path(temporary) / "card"
            result = subprocess.run([sys.executable, str(PROJECT / "tests/experimental_process_fixture.py"),
                "driver", str(root), mode], env={**os.environ,
                "PYTHONPATH": os.pathsep.join((str(PROJECT), str(PROJECT.parent)))},
                capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_authenticated_source_runner_releases_then_kernel_closes_and_case_replay_is_denied(self):
        self.composition("view")

    def test_forbidden_model_mutation_cannot_clear_the_real_principal_lifetime(self):
        self.composition("mutator")

    def test_a_staged_command_is_preserved_and_prevents_real_release(self):
        self.composition("staged")

    def test_slow_renderer_cleanup_cannot_borrow_the_remaining_view_budget(self):
        self.composition("slow_cleanup")


if __name__ == "__main__":
    unittest.main()
