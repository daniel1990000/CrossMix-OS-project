# Private state sessions and Resume

The optional state extension now has an actual emulator-owned caller, bounded
private result export, exact native state-load acknowledgement and authenticated
transfer between fresh principal/PyUI processes. The shipped runtime/profile
gates remain disabled. No installed emulator is replaced.

Patch 0003 is a deliberately new `--project-state-session=` extension. It is not
an interface already present in stable spruce/PPSSPP. Its source lock is
[state-session.lock.json](state-session.lock.json); apply the locked native-menu
patch, [state API patch](state-evidence.md), then this patch in that order.
The separate [complete build evidence](../evidence/ppsspp-complete-state-build.json)
records the state-enabled PowerVR candidate and rebuilt FFmpeg. That build also
uses the pinned post-recipe checked save-and-quit adaptation. These artifacts
remain private while recipe/SDK distribution clearance is unresolved.

## Existing owners and actual route

The principal creates and retains `PrivateStateSession` before executing the
existing source-staged command. It derives the selected ROM from the correlated
actual PyUI model request and checks the descriptor/preset through the original
read-only source adapter. Expected engine, configuration, writer and hardware
identities come from a separately qualified typed profile.

The optional spruce wrapper patch forwards only the quoted
`TRIMUI_PROJECT_STATE_REQUEST` and `TRIMUI_PROJECT_RESUME_STATE` fields to the
existing PPSSPP invocation. The standard launcher, lexical system detection,
PowerVR setup, configuration copy-in/copy-back and principal process boundary
remain the authorities. The private result parser refuses invalid sessions;
Resume cannot be requested with only an unpaired state pathname.

`NativeInit` accepts the explicit private-session option. A native `SaveSlot`
call queues bounded session work. `SaveState::Process` starts that work on the
existing emulator owner thread, calls the real state API and exports only its
completed result. The source API hashes exact engine/ROM bytes around the
operation and the finalized state afterward. A failed write, failed final
rename, identity change or failed private export reaches the original callback
as failure. The recipe's save-and-quit callback quits only after success; its
signal handler performs no file I/O.

For Resume, the existing `--state=FILE` argument must exactly match the private
request. The extension suppresses the competing startup/autoload route, verifies
the actual recorded state bytes, then calls the real `SaveState::Load` from
`Process`. Only completed successful load plus unchanged game/engine/state/session
identity produces a load acknowledgement. A warning or mere queue return does
not qualify. A load acknowledgement is stored separately from a saved checkpoint.

The principal's actual child-subreaper/ECHILD completion supplies foreground
return proof. A separate current writer authority must identify the complete
stopped-writer set. Neither proves a state operation on its own. A failed state
operation cannot invent a successful checkpoint. The engine retains the latest
genuinely completed save and load identities separately, so a later failed save
does not erase a successful earlier save in the same request. The principal
rechecks its exact current bytes before creating a capability. A later failed
session preserves an older stored checkpoint's original verification time.

Resumed sessions can save a new checkpoint using the existing native controls.
The new save and prior load acknowledgement are independently consumable. If the
new save replaces the old state bytes, the old load acknowledgement fails current
file validation; that does not prevent accepting the exact new saved checkpoint.

## Capability transfer between processes

`StateCapabilityStore` holds its HMAC key and records in a private volatile
directory outside the SD card. The directory is 0700; key, requests and results
are 0600 regular files. A private regular lock serializes first-use key creation;
only a fully written, fsynced key is atomically published, so concurrent helpers
cannot consume an empty key. Components are opened without following symlinks. The
key never belongs in GitHub, development payloads, card archives or support
bundles. Keep this store under `/tmp` so reboot removes it.

Only an exact typed verified completion can be authenticated for transfer.
Records bind the kernel boot identity, foreground request/token/generation,
game/engine/state identities, profile fingerprint and original checkpoint
observation. A fresh source process verifies the HMAC and independently rechecks
the qualified profile, native configuration hashes, actual engine/ROM/state
bytes and current stopped-writer lease. Replaced engine/configuration, changed
writer inventory, another boot, a modified record or a changed state disables
that capability. Arbitrary card JSON cannot create one.

The signed observation includes UTC and monotonic **verification** times. The
principal records these after the engine exits and foreground/writer/file checks
pass. Saving at 10:00 and playing until 11:00 therefore gives a verification time
near 11:00; the actual save time is unavailable in this protocol. The UI labels
this observation `Checkpoint verified`, never `Checkpoint saved`. It does not
establish compatibility or a clean shutdown. Reload and a later failed save
preserve the original verification observation. Backend rows expose
`state_recorded_at`, `state_recorded_at_kind="verification"`,
`state_recorded_monotonic_ns`, `state_request_id` and `state_profile_sha256`.

The source Resume handler records explicit bounded state intent, then calls the
existing `device.run_game`. The principal checks that intent against its
authenticated capability, creates a fresh private session and supplies the
scoped environment to the existing staged command. No shell text is parsed to
guess the selected game or inject an executable callback.

The fixed reviewed runtime configuration can bind these original callbacks:

```python
authority = PrincipalStateSessionAuthority(
    store=StateCapabilityStore("/tmp/trimui-state-capabilities"),
    private_root="/tmp",
    profiles={"PSP": independently_qualified_state_profile},
    observe_writers=qualified_current_writer_lease,
)
# ProcessSourceConfiguration fields:
command_environment = authority.command_environment
completion_observer = authority.completion_observer
resume_evidence = authority.resume_evidence
mode_actions = authority.source_mode_actions
```

Those expected profiles and writer leases are mandatory source-bound inputs,
not examples of completed device qualification. The shipped fixed configuration
returns `None`. The independent state profile requires hardware/save-load/native
launch/writer qualification, engine and native configuration hashes, approved
state roots, architecture, principal hash and complete writer identities.

## Packet definition

This new protocol uses canonical UTF-8 netstrings: `byte_length:data,`.
Requests start with `TPSE1Q\n`; results with `TPSE1R\n`. Total size is at most
32 KiB and each field at most 8 KiB. Leading-zero lengths, extra fields, trailing
bytes, embedded NULs and truncated data are rejected. Request file name is
exactly `request`. Output retains at most three fixed result files:
`result` records the latest completed attempt, while `save-completed` and
`load-completed` retain each operation's latest successful identity. Each uses
a private temporary file, file fsync, atomic rename and directory fsync. Positive
completion is published before the final `result`. Consumers reject missing or
invalid final reports and completion sequences newer than that report; an
interrupted publication cannot promote its orphan completion. Equal sequences
must contain identical packets. A failure never replaces a positive completion.
Result packets contain no executable code, callback names or shutdown assertions.

| Request index | Value |
|---|---|
| 0–5 | Random session ID; request ID; foreground token; boot ID; generation; game ID |
| 6–9 | Exact ROM path and SHA-256; independently expected engine SHA-256; approved state root |
| 10–14 | `save` or `resume`; exact prior state path and SHA-256 for Resume, otherwise empty; source-format ID; slot |

| Result index | Value |
|---|---|
| 0–5 | Exact corresponding session/request/foreground/game identity |
| 6–9 | `save` or `load`; operation sequence; `success` or `failure`; bounded message |
| 10–13 | Positive SFO disc ID/version; engine game prefix; exact ROM path |
| 14–19 | Engine, ROM and state SHA-256; corresponding sizes |
| 20–26 | Exact engine state path; slot; pinned upstream commit; extension ID; engine version; architecture; state-format ID |

Failure packets have empty evidence fields 10–26. The private result alone is
insufficient: only the retained launch identity and separate qualified
foreground/writer authorities allow acceptance. A failed latest attempt remains
reported as failure; only separately retained genuine completion can qualify a
checkpoint. Missing callback or lost core cannot invent one. All file sizes and
streaming limits from the [state API](state-evidence.md) still apply.

## Verification and remaining qualification

Host tests compile the actual patched queue, `SaveSlot`, `Process`, command-line
session parser, export and load functions with the real upstream SHA-256 code.
They cover finalization failures, identity changes, private modes/symlinks,
native state mismatch and successful load acknowledgement. The integration
test runs actual source command staging in one process, genuine principal
sealed-script/subreaper completion, native state fixture export, authenticated
transfer, same-request save→failure, a failed later session, Resume in a fresh
process, then load→new save→failure and another fresh Resume. It checks the
new save independently when replaced bytes invalidate the old load receipt.
Failed later sessions preserve the earlier verification time. Source staging
itself runs through actual `run_pyui`→ECHILD and authenticated source closure;
no kernel completion seal is fabricated.

The independent profile's configuration hashes are strict. Pinning a writable
full `ppsspp.ini` may invalidate it after normal native undo metadata or settings
updates. Device qualification must verify the intended configuration inventory
and stability policy, including copy-back; the host's static fixture config
does not resolve that installed behavior.

Emulator serialization, PSP state bytes, installed configuration and writer
qualification in these tests are explicit non-live fixtures. The complete
candidate build and SDK symbol inventory add build evidence. Installed loader,
PowerVR, actual input, native widgets, per-game configuration, real saves/load,
durability, suspend/power/USB and recovery still require the original TG5040.
The complete route is present for qualification; the test evidence does not
authorize enabling its device profiles.
