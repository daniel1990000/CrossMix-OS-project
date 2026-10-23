# Qualified PyUI binding

## Complete source process boundary

The current source integration is `principal_integration.py`. Its
`stage_process_exit_integration` produces one exact-source review patch covering
the real MainMenu prelude, `mainui` startup/model caller, existing command writer
and principal loop. It is an alternative to the older cooperative-audio staging
below; do not apply both. The integration release tool composes it with the
separate reliability fixes on private copies and retains every preimage/hash.

The staged principal uses a fixed literal
`/mnt/SDCARD/App/PSPMode/integration/app` import root. The independently verified
original overlay must provide that directory; no selector or card metadata
chooses Python code. `qualified_runtime.py` is the fixed reviewed configuration
entrypoint and returns `None` in this development payload. It cannot be enabled
by a JSON flag or development package signature. Device-mode configuration
requires separate source-use, runtime, hardware and process-boundary gates,
positive live observations, exact installed source/payload hashes and the same
fixed `module_root`. All those expected values must come from independent
qualification.
The required inventory follows `REQUIRED_PROJECT_MODULES` in
`process_source.py`, including transitive frontend, UI, adapter and state
imports, as well as the pinned source and shared-service scripts. A development
archive signature does not supply independent runtime qualification. The
[experimental-route design](../docs/experimental-device-route.md) records the
separate admission and bounded-exit work still needed for a private pilot.

When qualified, `process_source.py` wraps the actual current Device, Display,
Controller, FavoritesManager, RecentsManager and source-initialized ROM builder.
It does not initialize second history/input/display owners. Its shared write
window serializes common hardware writes and launch preparation. Native Wi-Fi,
Bluetooth and per-game options reuse the already initialized source menus.
Optional PPSSPP controls/appearance/state adapters occupy fixed in-memory slots.
The source factory accepts `resume_evidence` and `mode_actions` callbacks; the
concrete `PrincipalStateSessionAuthority` supplies those together with its
principal command/completion callbacks.

Worker/input preparation deliberately leaves existing source threads and fds
owned by PyUI. The original device game route stages its normal command and
exits. Principal's dedicated child helper waits for the entire source subtree
before running that command. It uses Linux child-subreaper adoption and waits
until the kernel reports ECHILD, including double-forked and setsid children.
It never kills a surviving process to permit a second UI. Process exit releases
that subtree's Python threads and input/display descriptors; a shell exit status
or missing command file alone cannot provide the proof.

`run_pyui` commits an authenticated source-closure record only after that real
ECHILD. It binds the exact foreground, correlation journal and captured command
hash to the current boot and existing principal PID/start. The private key and
record live under `/tmp/trimui-project-principal`, outside card metadata. A
fresh command helper consumes that record before launch. A separate authenticated
boot-global lifetime and private `flock` serialize source/command transitions.
Both project and classic commands mark a dirty lifetime before any spawn;
in-flight command ownership becomes complete only after actual ECHILD and exact
command consumption. Killing a helper or principal leaves that dirty lifetime
blocked across a new principal PID. A fixed shell presence guard also blocks
fallback if the original payload/configuration is unavailable. A dead PID,
missing command file, or restarted principal cannot mint the missing proof.

The source writer atomically creates the existing command and a bounded private
correlation request containing its hash, exact foreground identity, source
PID/start and selected RomInfo identity. Resume adds an explicit state identity;
the principal checks it against the separately authenticated state capability
store. The request is data, not completion evidence or authority to choose code.
Principal executes sealed captured bytes, preserving staged `$0`, positional
arguments and the lexical emulator launcher path. A narrow reviewed Linux
syscall fallback supports memfd on older-glibc Python builds; creation and seal
readback remain target capability checks.

After all foreground descendants exit, principal atomically takes the staged
object into a private quarantine and verifies it before removal. A replacement
is retained/restored without overwriting a newer staged file. Only a sealed
`PrincipalCompletion` can issue `SpruceReturnEvidence`. It matches the token,
request, boot, generation and independent principal hash before health clears.
The optional state owner creates its private session in the principal helper,
retains it through command execution and separately observes state/writer
completion there. A private boot-bound authenticated capability store carries
verified state eligibility into the next source process; a serialized receipt
cannot mint that eligibility.

`resident.py` retains shared service descendants under a principal-owned sibling
of the foreground helpers. Exact source hooks delegate Bluetooth apply, Wi-Fi
mutations, input calibration, the five existing network-service toggles, and the
two tasks that restart shared network services. The relay invokes the original
fixed scripts with their existing locks/daemon guards; it adds no hardware
implementation. Actual configured radio commands must match the reviewed fixed
paths. Unknown task commands retain their original source subtree ownership.

The private Unix socket authenticates peer credentials, principal lifetime and
an HMAC source capability. Only a direct principal helper can enroll; subsequent
requests require its live source lineage and the next sequence number. Requests
are bounded typed operation data. Wi-Fi credentials stay on private IPC/stdin
and are not logged. Original service stdin is closed. Games inherit neither the
relay capability nor its server identity. A disconnected or replayed request
cannot trigger a fallback invocation in the foreground subtree.

The relay adopts and reaps its original services, while source ECHILD accounts
only for the closed foreground subtree. It never claims the shared services or
their writers stopped. A drain request stops new work and waits for every child
to exit naturally. Persistent services keep that drain pending. Existing runtime
services created before the relay remain with their original authority. Physical
input, graphics, storage, power/sleep/USB and recovery still require the device.

`test_principal_integration.py` exercises real Linux child adoption, escaped
descendants, signals, failed launch, exact command consumption/replacement,
scoped callback lifetime, older-libc memfd fallback, actual transformed game and
principal seams, killed-helper/orphan recovery refusal, authenticated delegation,
actual Bluetooth apply/watch workers surviving a game handoff, and an
initialized-model host frame. The state source harness
also exercises real patched SaveSlot/Process/export through the principal proof
and a fresh-process authenticated Resume/load. These are host fixtures; no
installed device or source-use/distribution gate is qualified by them.

## Initialized-owner binding API

`bootstrap.py` provides an original in-process binding for an already running
PyUI. It does not initialize devices, SDL, controller interfaces, favorites,
recents or ROM managers. `bind_running_pyui` reads the existing `Device`,
`Display` and `Controller` singletons through fixed imports, then installs a
lazy factory for `pyui_entry.maybe_run_main_menu`. Selecting classic skips that
factory and the optional presentation imports.

A reviewed source bootstrap can call the API with these existing authorities:

```python
from bridge.bootstrap import ExistingPyUIModels, bind_running_pyui

binding = bind_running_pyui(
    models=ExistingPyUIModels(
        existing_system_manager, existing_game_list,
        existing_favorites_manager, existing_recents_manager,
        label_for=existing_label_resolver, artwork_for=existing_artwork_resolver,
    ),
    state_dir="/mnt/SDCARD/App/PSPMode/state",
    profile=independently_qualified_profile,
    inventory=observe_current_runtime,
    preferences=observe_current_preferences,
    quiescent=existing_session_is_idle,
    stop_background_tasks=stop_existing_background_work,
    restore_background_tasks=restore_existing_background_work,
    release_input=release_existing_input,
    restore_input=restore_existing_input,
    verify_return=verify_spruce_foreground_return,
    control_adapter=qualified_controls,
    theme_manager=qualified_ppsspp_theme_manager,
)
```

The variable names above are caller-supplied references, not implementations or
metadata fields. Expected source/runtime hashes come from the independently
qualified profile. The inventory callback must observe current installed hashes
and positive TG5040, firmware and platform identity; it must never fill the
expected profile from the files it is checking. Preferences are refreshed from
the existing configuration authority. Every preflight rechecks the current
owner identities and model readiness, including after an observation callback.
An owner replacement after context creation invalidates the next handoff.

The supplied model callbacks must use initialized PyUI models. Both history
managers must have completed their existing `_init_event` startup. The wrapper
creates a project adapter around those references; it never calls the managers'
constructors or initialization methods. Keep existing per-game preset identity,
lexical launch paths and device callbacks intact.

## Earlier cooperative lifecycle alternative

`lifecycle.py` retains the actual device-startup, manager-startup and audio-route
callbacks passed by the source caller. Startup completion requires successful
callback outcomes; thread disappearance alone is insufficient. Its paired
stop/restore methods stop and join only the cooperative audio watcher it owns.
A timed-out stop retains that owner and blocks a replacement watcher. Neither
one-shot initialization callback runs again during restoration. An unexpectedly
ended audio watcher also blocks readiness, including a source early return for
unsupported USB audio without a separately qualified no-watcher contract.

Those three wrappers do not cover the entire source lifecycle. Inspection of
the exact pinned source also found constructor/config/key watchers, a controller
polling thread, nested audio/Bluetooth work, timezone/throttle/cache workers and
SDL audio ownership. `other_owners_idle` is a required independent positive check
for those owners and staged/active foreground work. Do not replace it with an
unconditional true value on a device. No shipped caller supplies that complete
authority.

Stop/release callbacks must have matching restoration that is safe even after a
partial failure. The runner marks these operations before invoking them. A
rejected handoff restores the paired authorities before reopening presentation.
A failed restoration blocks classic fallback and repeated restoration attempts.
Existing power/watchdog ownership and `save_poweroff.sh` remain unchanged.

`source_integration.audit_source_lifecycle` is read-only and checks ten exact
source blobs. `stage_lifecycle_hook` can produce a separate review patch for the
real `mainui.py` startup/caller seam and a stop-event-aware
`DeviceCommon.watch_audio_route`. It requires the existing source-use gate,
writes outside the source tree and never applies the patch. The existing
no-argument audio watcher behavior remains available to classic PyUI.

The staged source calls `begin_source_tasks` with its current device and existing
`background_startup`, then `bind_source_session` with its constructed MainMenu
and retained tasks. A trusted source bootstrap must first register an in-memory
factory using `configure_source_caller`, including the resolved source-use flag
and the independent owner check. Without registration the existing source
startup branch runs and the optional binding remains absent. Metadata cannot
register executable callbacks. The factory returns an `InitializedPyUIBinding`
around existing models and owners, with `tasks.quiescent`,
`tasks.stop_background_tasks` and `tasks.restore_background_tasks` as its
lifecycle callbacks; the caller validates those identities before binding.

The separate MainMenu staging helper preserves game-selection-only mode,
GameSwitcher and box-art processing before the optional view. Neither staged
patch is installed or enabled. The lifecycle patch leaves MainMenu, principal,
boot files and hardware profile flags untouched. This earlier alternative does
not supply the complete source/process authority implemented by the principal
integration above, and must not be combined with it.

## Collecting a real return

Only a qualified spruce return seam may explicitly call
`binding.collect_return(main_menu)`. Normal frontend startup never calls it.
The callback receives a `ForegroundIdentity` containing the saved token, exact
request, boot and generation. It must return a `SpruceReturnEvidence` object
with that identity, the pinned source commit, independently qualified principal
hash, positive staged-command absence and foreground-completion observations,
and a bounded reference to the retained verification evidence.

A receipt dictionary loaded from card metadata is rejected. Missing authority,
cross-boot identities, wrong hashes, incomplete observations, callback failures,
runtime changes and replacement foreground records retain the tombstone. The
binding rechecks runtime and idle ownership after the callback and compares the
generation under the health lock before clearing it. The receipt establishes
foreground completion only; it does not prove a save or emulator state succeeded.

The principal integration above supplies the source return seam; its physical
qualification remains pending. A staged callback returning, shell syntax acceptance, screenshot, process
exit code or missing guessed state path cannot supply that proof on its own.
The source owner must account for surviving processes and retained display/input
ownership and preserve its evidence. Do not clear an uncertain same-boot handoff
to make either frontend start.

## Verification status

`test_bootstrap.py` and `test_embedded.py` exercise injected original fixtures:
live-evidence refresh, independent expected hashes, owner replacement, pending
models, fixed singleton imports, strict return correlation, partial lifecycle
failure and blocked fallback after restoration failure. They execute no hardware
services and qualify no installed OS. `test_pyui_lifecycle.py` additionally
executes the actual staged startup function and audio watcher in isolation,
checks the retained task/failure/restore contract, and rejects changed source
or unresolved source-use staging. Its true gate inputs are fixtures. The shipped
source-use, runtime and hardware gates remain false. Device qualification of the
source worker/input release, installed caller, principal return, original-card
restore, real launch/saves and power/USB behavior remain qualification work.
