# Principal observation deadlines

D01 host engineering, 23 October 2026. `run_owned_tree()` now accepts an
optional typed `TreeObservationPolicy(deadline_monotonic, on_blocked,
poll_interval_seconds=0.05)` constructed by trusted calling code. The shipped
runtime entry and device profiles do not supply a policy or admit a candidate.
This implements an observation seam, not the complete experimental route.

Without a policy the existing blocking child-subreaper wait is unchanged. With
one, the same helper polls the kernel with `waitpid(WNOHANG)`, sleeping between
observations. Intervals must be between 10 and 250 milliseconds. A missing
helper process identity, invalid policy or already expired deadline refuses
startup. Startup is checked again immediately before the child is created.

On expiry the helper emits one `TreeBlockedObservation`. It contains the
deadline and observation's monotonic timestamps, helper/root PID and observed
start identity, reap count and whether the root exit was already observed. It
does not contain the command, environment, content paths or exception text.
A root can exit before its `setsid`/double-fork descendants; this event therefore
does not report resource closure or a completed save.

The helper retains subreaper ownership and continues waiting for real kernel
`ECHILD`. It does not kill a process or launch classic. After actual closure,
an expired observation raises `OBSERVATION_BLOCKED` instead of returning an
`OwnedTreeCompletion`. An observer exception, including a failed evidence
write, is withheld until closure and becomes `OBSERVATION_REPORT_FAILED` with
no private exception text. These errors occur before the existing caller can
consume staged bytes, close a source lease, clear a foreground or complete a
command. Dirty records remain for reviewed recovery; later closure alone
cannot turn a failed admission into a successful case. Subreaper state is
restored only after all children have exited, or after no child was started.

The observer is cooperative trusted code. It must do bounded local reporting,
not start programs or terminate owners. A blocked observer syscall cannot be
safely preempted here. The deadline bounds the decision to stop admission; it
does not guarantee process termination, a working fallback or elapsed-time
closure. A permanently surviving descendant keeps the helper alive. If the
helper itself dies, the existing dirty/foreground evidence still requires
recovery; no timer authenticates orphan closure. Scheduling delay can also
cause conservative refusal when `ECHILD` was not observed before the deadline.

## Host validation

`project/tests/test_principal_deadlines.py` has 12 host tests covering invalid
policies, pre-start expiry, unavailable helper identity, unchanged default
completion, timely/nonzero exit, one-shot live-owner reporting, sleeping
polls, `setsid`/double-fork descendants, observer failure, foreign children,
failed spawn and restored subreaper state. Actual source/command boundary
tests inject the optional policy at the trusted call seam and prove expired
observations retain dirty source leases, foreground identity, staged bytes
and correlated requests even after real child exit.

No device candidate was admitted or executed. R05 source-use evidence,
D02/D03 physical recovery/inventory, the reviewed fixed experimental entry and
actual original-TG5040 stop/recovery rehearsal remain required for D01.
