# D01 host admission foundations

The new original [admission controller](../bridge/experimental.py) and
[evidence journal](../bridge/experimental_journal.py) implement host-testable
parts of the [experimental-route design](experimental-device-route.md). They
provide a synthetic view-only case. The shipped source entry remains
unavailable; no device entry calls this controller, and D01 remains open.

## Implemented boundaries

`HostCandidate` binds an independently supplied frontend commit, original
source inventory, release descriptor, signed-package and signer fingerprints,
the pinned spruce commit/PyUI tree, and an exact file/hash inventory. These
bindings identify already reviewed inputs; the controller does not verify a
package signature or prove where the expected hashes came from. The expected
inventory must be prepared independently, rather than copied from the observed
fixture. File mode/ownership and complete installed distribution review remain
separate work.

`inspect_host_fixture()` reads files through anchored directory descriptors,
rejects links and special files, checks file/directory stability, and bounds
depth, entries and total bytes. It never executes inspected files. The
conventional `/mnt/SDCARD` path is refused. A pathname alone cannot identify all
removable media, so the caller still supplies synthetic host content.

`prepare_host_view()` accepts exact typed host observations through a trusted
in-process callback. A fresh check compares the expected files, boot identity,
principal PID/start identity, preference/owner readiness, dirty lifetime and
staged-command status. The same checks run before and after guarded actions.
Live-device observations and serialized dictionaries are refused. There is no
configuration-file, environment-variable or command-line admission loader.

The capability admits one case, expires before startup, and refuses a second
start. Copying and pickling it are disabled. These checks protect against stale
or accidentally altered host inputs; they do not defend against an owner
replacing Python code or the operating system. They establish no source-use,
runtime, hardware, production or distribution permission.

## View-only actions and cooperative return

Trusted callers can guard only navigation, rendering, polling existing input,
reading the library and searching. Game/tool launches, favorites/settings
writes, advanced menus, state/Resume, USB and power transitions are rejected
before their callbacks run. Names never resolve code; the callback is supplied
by fixed application code. A future integration must bind every actual model
action to this policy. Calling an arbitrary writer under a false `render`
label is outside the trusted-caller contract.

Monotonic checks enforce at most 60 seconds to begin and request ordinary
return after at most 120 seconds of observed view time. Shorter host limits are
supported. A return request has a separate maximum five-second observation
window; repeating the request cannot extend it. The controller checks time
before and after callbacks. It cannot interrupt blocked renderer/input/source
or restoration calls, and it does not start a timer thread or kill a process.
A delayed callback is recorded when it returns; this is no hard runtime bound.

Completion requires a fresh matching identity and explicit typed positive
observations for restored owners, idle state, classic frame readiness and
classic input readiness, with no staged command. Failed or late restoration,
changed owners, missing preferences, dirty state, callback/clock failure or
uncertain evidence leaves the case blocked. A blocked case never returns
permission to start classic. The host observations do not establish physical
display/input restoration.

## Durable local evidence

The journal requires a new file in an existing private directory outside the
fixture. It retains a fixed event vocabulary, monotonic timestamps, sequence
numbers and opaque candidate/session/boot/owner digests. Paths, ROM names,
arguments, environment, credentials and exception text are absent. All records
carry `host_fixture` provenance.

Each append checks the named directory/file identity, ownership, permissions,
link count, expected size and complete prior content hash. It writes one
bounded record, fsyncs it and verifies the resulting content before returning a
digest. A failed fsync, short write, replacement, same-size edit, exhausted
budget or non-owner thread poisons the writer. There is no replay/retry that
turns uncertain publication into a successful append. A failed write can leave
partial or uncertain bytes; preserve them for review. Opening the same output
again is refused.

Fresh `read_host_journal()` verifies bounded content, unique JSON keys, exact
fields, monotonic order, stable session binding and the chained checksums.
Readback detects accidental changes; it is neither an authenticity signature
nor an admission loader. No independent-media copy/retrieval or real-device
custody is performed by these helpers.

## Validation and remaining integration

The focused host suite contains 38 passing tests:

```sh
PYTHONPATH=project /workspace/smartpro-venv/bin/python -m unittest \
  project.tests.test_experimental_admission \
  project.tests.test_experimental_journal
```

It covers mismatched/extra/missing files, changed boot/PID/start identity,
expiry/replay, dirty/staged lifetimes, missing readiness, forbidden actions,
late callbacks and restoration, partial restoration, clock failure, thread
ownership, serialization, file/directory replacement, symlinks/hardlinks,
same-size edit before/during append, short writes, failed fsync and corrupted
readback. `qualified_runtime.configuration()` continues to return `None`.

Still required before an actual pilot: implement/review the fixed experimental
device entry at both source/embedded boundaries; bind its expected complete
installed imports and authorities; use actual R05 delivery/scope evidence and
actual D02/D03 backup/restoration/runtime readiness; integrate real action and
stop requests; retain and retrieve physical evidence; rehearse the independent
recovery route. Optional native admissions need the exact retained R04 set and
applicable R06 review. The production qualification path remains separate.
