# Qualified PyUI binding

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

## Lifecycle responsibilities

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
boot files and hardware profile flags untouched. A real principal return
authority and complete source worker/input release remain outstanding.

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

The pinned principal still needs a reviewed and physically qualified return
seam. A staged callback returning, shell syntax acceptance, screenshot, process
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
source-use, runtime and hardware gates remain false. Complete source worker/input
release, installed caller qualification, actual principal return, original-card
restore, real launch/saves and power/USB behavior remain qualification work.
