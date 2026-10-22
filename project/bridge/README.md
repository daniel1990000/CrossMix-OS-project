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

Pinned `mainui.py` starts a device-startup thread, a manager-startup thread and a
daemon audio-route watcher. It does not retain a generic stop/join authority for
all of them. The existence of this binding does not solve that source lifecycle.
A reviewed integration must retain and qualify the actual thread/task ownership,
wait for one-shot startup completion, and provide the paired stop/restore
callbacks. `quiescent` must positively establish that existing work is idle and
no other staged or active foreground operation owns the session. Do not replace
it with an unconditional true value on a device.

Stop/release callbacks must have matching restoration that is safe even after a
partial failure. The runner marks these operations before invoking them. A
rejected handoff restores the paired authorities before reopening presentation.
A failed restoration blocks classic fallback and repeated restoration attempts.
Existing power/watchdog ownership and `save_poweroff.sh` remain unchanged.

The MainMenu staging helper preserves game-selection-only mode, GameSwitcher
and box-art processing before the optional view. It still requires the existing
source-use gate before producing an upstream derivative. There is no installed
bootstrap caller, startup-thread patch or enabled MainMenu hook in this payload.

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
services and qualify no installed OS. The shipped source-use, runtime and
hardware gates remain false. Source caller/thread integration, actual principal
return, original-card restore, real launch/saves and power/USB behavior remain
device qualification work.
