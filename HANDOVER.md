# TrimUI Smart Pro implementation handover

Checkpoint: 22 October 2026. Active branch: **`build/spruce-psp-experience`** in `daniel1990000/CrossMix-OS-project`.

Saved for review in [draft PR #1](https://github.com/daniel1990000/CrossMix-OS-project/pull/1). The branch contains all implementation source, tests, notices, screenshots and this handover. Read the PR's latest Actions run for remote CI/artifacts; locally saved evidence remains separately identified.

Latest continuation: retained PyUI startup/audio task ownership and exact-source
caller staging, an installed loader/mapped-library evidence probe, and a separate
optional PPSSPP save-slot completion patch. That patch checks finalization and
binds exact game/engine/state fingerprints after the real asynchronous save.
It is outside the previously cross-built candidate and enables no Resume action.
The actual principal return authority and physical qualification remain open.
All **349 host checks** pass with zero skips, failures or errors. The **dev3**
development artifacts pass deterministic rebuild, signature/inventory,
installed-payload rendering and fixture activation/rollback checks.

## User direction

Build a polished PSP-inspired whole-system experience for the **original TrimUI Smart Pro TG5040**. Improve and specialize spruceOS, retaining its working device support, emulators, existing features and saves. Reuse existing projects extensively, including [PPSSPP](https://github.com/hrydgard/PPSSPP), and research other useful sources. The user has authorized autonomous implementation and parallel agents. Keep progress, decisions, evidence and future-chat handovers in GitHub.

The repository name and inherited tree still say CrossMix. That tree and the collapsed appendix in [TRIMUI_PLAN.md](TRIMUI_PLAN.md) are historical reference and an offline migration source. **Do not resume the superseded CrossMix runtime architecture.** The latest comprehensive plan and this implementation checkpoint govern current work.

## Start here

1. Read this file, [project/README.md](project/README.md), the active portion of [TRIMUI_PLAN.md](TRIMUI_PLAN.md), [spruce source lock](docs/spruce-source-lock.json), and [PPSSPP reuse map](project/ppsspp/reuse-map.md).
2. Check out `build/spruce-psp-experience`. Work is saved on this branch; do not assume `main` contains the implementation until its draft PR is merged.
3. Run the documented host checks with both untouched pinned upstream checkouts. Review the saved evidence and distinguish fixtures from physical observations.
4. Continue the next concrete work below. Avoid another planning-only cycle or asking the user to repeat the plan.

A lightweight clone avoids the large historical CrossMix payload:

```sh
git clone --filter=blob:none --sparse --branch build/spruce-psp-experience https://github.com/daniel1990000/CrossMix-OS-project.git trimui
cd trimui
git sparse-checkout set --no-cone /project/ /.github/workflows/ /docs/ /HANDOVER.md /AGENTS.md /TRIMUI_PLAN.md /README.md /.gitignore
```

## Saved implementation

| Path | Ownership and behavior |
|---|---|
| `project/psp_shell/ui/` | Original Python SDL navigation, renderer, input, text/artwork caches, waves and accessibility. Shared-renderer embedding preserves existing PyUI SDL ownership. |
| `project/psp_shell/app.py` | Runnable desktop/demo and read-only card browser; fixed Dispatcher operations; optional injected launch/control adapters. Standalone mode never starts games or device commands. |
| `project/psp_shell/adapters/spruce.py`, `library.py` | Source snapshot and injected existing PyUI models, platform filtering, exact ROM/preset identity, token-validated existing callbacks. |
| `project/psp_shell/runtime.py`, `health.py`, `embedded.py` | Launch coordination, shared input/display runner, foreground handoff records, checksummed health/selector state and classic fallback. |
| `project/bridge/` | Lazy frontend seam, trusted initialized-owner/model binding, refreshed independent evidence and strict correlated returns. Retained startup/audio tasks have paired stop/restore; a ten-file source audit and source-use-gated staging add the actual startup caller/cooperative watcher seam. Default unbound/unqualified execution stays classic. No installed registration or hook is enabled. |
| `project/psp_shell/settings.py`, `controls.py` | Format-preserving transactions, previews, generations, writer/hash gates, compensating backends, recovery and targeted undo. PPSSPP changes require the opt-in flag and exact Confirm/Back pair under the engine's INI semantics. Three shipped emulator profiles remain unqualified. |
| `project/ppsspp/` | Upstream v1.20.3 native-menu source patch, exact hashes/notices, C++ acceptance, original themes and isolated full-build tooling. A separate optional save-slot evidence patch has its own lock and compiled source acceptance; it is not part of the previous complete candidate build. See [the build procedure](project/ppsspp/build-candidate.md). |
| `project/psp_shell/ppsspp.py` | Original theme adoption helper, preview, backup, qualified stopped-writer gates, multi-file recovery and undo. Settings → PPSSPP appearance previews the frontend's contrast/motion choices before applying them through an injected manager. Standalone mode has no emulator write adapter. |
| `project/patches/` | Four pinned spruce fixes: quote the launcher directory, refuse insecure TLS retry, preserve actual archive extraction exit status, and refuse mounted-card USB export after staging failure. Stored as reviewable patches only. |
| `project/packaging/`, `project/tools/build_payload.py` | Deterministic signed scoped overlays, strict archive verification, fixture staging/activation/health/rollback and development artifact builder. |
| `project/tools/` | Read-only inventory/support, offline migration, benchmarks and fixture creation. The [installed-runtime probe](project/docs/installed-runtime-evidence.md) inspects exact ELF/interpreter paths and optionally correlates an already-running process's mapped library inodes without executing the emulator. |
| `project/psp_shell/ports.py`, `project/profiles/ports.json` | Owner-data import preview, staging, backups, rollback and configuration undo. GTA III/VC, Sonic Mania, Celeste and Render96 candidates; San Andreas stays disabled/experimental. |
| `.github/workflows/smartpro-offshoot.yml` | Pinned source checkouts, host tests, preview and verified development artifacts. Workflow execution status is separate from locally saved test evidence. |

The first implementation uses original Python modules around **existing PyUI**, not a replacement native C++ supervisor. Early incomplete CrossMix prototypes were archived locally and excluded from this active branch. This checkpoint contains no modified base emulator or firmware.

## Exact pins and evidence

- Spruce stable **v4.5.4**, commit `d45ff8dfe5756147522b04ae5863d17a90e88b54`; shipped PyUI tree `4d0bdb3111d9226fbacbea6c89d65e540620e21e`.
- Full `spruceV4.5.4.7z` was downloaded (1,652,634,074 bytes) and independently SHA-256 checked: `4623f1cd824ac1d01e7663d11ca40a8d3ad874c5f071e692f4392957d2159cfd`. Ten named integration/licence files match the pinned Git source. See [release-source-audit.json](project/evidence/release-source-audit.json) and its reproducible audit script.
- Bundled `Emu/PSP/PPSSPPSDL_TrimUI`: 19,885,376 bytes, SHA-256 `d0635cdb73e046cf8c62a92a4c59194cf9a80dfabbe08a0c9a0cb4628a1c96d7`, Git blob `509ffbd9ba3874c05ae3b470d77cab5299d85c4e`, embedded `v1.20.3` string. This does not establish its complete build source, installed-device identity or the new extension.
- PPSSPP upstream **v1.20.3**, commit `d357e6a32934800d3d80b49f910a603e1b069751`. Optional spruce PowerVR build recipe pinned at `9f770cb984fd8ffcc8f91d24fcbca859439c2e9b`.
- The latest GitHub planning/research commits through `3832c662641fbff18ac3ddafef70a48db5981440` were merged and preserved, including the broad research mandate and sections 7A/7B. The newer upstream PPSSPP research pin is separate from the SDL2-compatible v1.20.3 implementation pin.
- Host checks and development packaging results are saved under [project/evidence](project/evidence/). Test counts, skips and exact checks are recorded there. Actual dummy-SDL previews and signature/rebuild/stage/rollback checks passed. No physical-device performance result is claimed.
- A previous complete separate PPSSPP PowerVR cross-build succeeded with the project extension and all ten selected pinned spruce patches. The read-only SDK audit found incompatible GLIBC requirements: libc `2.28` and libm `2.27`/`2.29`, absent from the recipe's `2.25` sysroot. See [candidate-build evidence](project/evidence/ppsspp-candidate-build.json). Its candidate and pinned source/input snapshot were retained privately in the prior environment; they were not restored here. Its bundled FFmpeg archives have not been matched to that pinned source; no executable was installed or published.
- The corrected candidate builds both PPSSPP and its pinned FFmpeg from source, with explicit GCC 9/SDK header and library search. Its AArch64 executable is 19,909,952 bytes, SHA-256 `1f0980edcf4ddd2550a050d9159658046827d37165a80d283647c504226a77df`, and requires only `GLIBC_2.17`. The recursive 16-object SDK inventory passes. See [corrected-build evidence](project/evidence/ppsspp-sdk-search-build.json). This does not prove the installed device's loader, drivers, input or save compatibility.

The PPSSPP patch reuses ConfigSetting serialization, SDL input translation, native menu key handling and existing settings widgets. Opt-in `[ProjectNativeMenu] IndependentMenuControls` defaults false; physical south/east Confirm/Back stays separate from PSP gameplay and ButtonPreference. Reserved keys cannot also trigger native info/tab/direction actions or a remapped Pause-to-exit action in native menus. Tests compile selected real patched functions and the actual INI value parser with explicit narrow fixtures. Target qualification remains separate from source acceptance and cross-building.

The whole-system status is tracked in [feature-coverage.md](project/docs/feature-coverage.md). [The binding contract](project/bridge/README.md) identifies the existing source lifecycle and principal return work that remains unbound.

The new [lifecycle source audit](project/evidence/pyui-lifecycle-source-audit.json)
pins ten actual sources and enumerates seven unaccounted owner groups. It does
not qualify those workers. The optional PPSSPP patch and its separate lock retain
their own source/acceptance evidence; neither the prior candidate's executable
hash nor its SDK-inventory pass applies to that new patch. No installed-runtime
report or original-device test was collected during this continuation.

## Next concrete work

1. **Complete the actual qualified PyUI caller and return authority.** `RetainedPyUITasks` now owns the existing two one-shot callbacks and cooperative audio watcher, preserving failures, stop timeouts and restoration ownership. `configure_source_caller` connects a trusted in-memory factory to `InitializedPyUIBinding`; source-use-gated staging adds the actual `mainui` caller and stop-event seam. No registration is shipped. Account for nested startup/audio refresh, SmartPro constructor/config/key/input workers, timezone/throttle/cache/network/audio workers and staged foreground descendants before supplying `other_owners_idle`. The ten-file audit lists those gaps. Pair the separate MainMenu hook while preserving its GameSwitcher, box-art and game-selection-only prelude. The principal still only waits for the staged shell and removes the command file; that does not prove descendant or display/input completion. No qualified principal return seam exists. Keep correlated same-boot receipts and real successful input polling; never clear a tombstone to start another UI.
2. **Qualify the separate source-built PPSSPP candidate.** [The build procedure](project/ppsspp/build-candidate.md) uses `--strict-sdk-search --rebuild-ffmpeg` to avoid Ubuntu cross-header/library leakage and the old FFmpeg prebuilt's `fcntl64` import. The previous complete engine links and passes the recursive SDK symbol-version inventory. Preserve its failed attempts and corrected result. Use the new [read-only probe](project/docs/installed-runtime-evidence.md) for exact installed ELF/interpreter identities and already-running mapped libraries, then separately collect input and complete writer ownership. Verify saves, states, native widgets and PowerVR rendering on a spare/restorable card. The optional state patch needs a separate full build and new source/binary/SDK evidence before joining this candidate. Keep the installed engine unchanged until qualification passes. The pinned recipe scripts lack an explicit licence grant and SDK redistribution remains unaudited; keep candidate binaries and their full recipe/source archive private while distribution gates are unresolved. In upstream SDL, south/east are `NKCODE_BUTTON_2/3`, not Android `BUTTON_A/B`.
3. **Qualify common controls and matching PPSSPP appearance.** The common UI now exposes both controls and PPSSPP appearance, with preview/apply/Undo and separate generations. Controls require all three extension keys, report persisted configuration status conservatively, and reject incomplete previews. Appearance matches contrast/motion only after explicit review; palette overwrite defaults to Cancel. Both use the actual PPSSPP INI rules and stopped-writer gates. Supply qualified installed profiles and serialize both adapters in the same write window before target use. Verify per-game overlay behavior. Keep standard RetroArch, spruce IGM and native PPSSPP surfaces separate; the IGM adapter remains unsupported.
4. **Integrate and qualify exact in-emulator state evidence for real Resume.** The separate optional patch adds `SaveState::SaveSlotWithEvidence` around the actual queued Save/Process/SaveSlot lifecycle. It reports final rename failure and blocked operations; successful evidence uses the engine's real slot path/SFO identity, request/session correlation, and streamed ROM/engine/state hashes. It has no external exporter, caller or launch protocol. Full ROM hashing can pause emulation and remains qualification-only. Callback completion proves neither durable storage nor clean shutdown; abandoned queued work supplies no success. Supply a reviewed emulator owner/caller, complete writer and state profile evidence, separate full candidate build, and real save/load/return tests before wiring any Resume action. Do not guess `.ppst` paths, infer success from a screenshot or repurpose battery saves as states.
5. **Complete the whole-system plan and physical qualification.** Hardware settings and advanced utilities should delegate to existing spruce authorities. Networking/power/sleep/USB, high-level settings UI coverage, all emulator/native-screen visual parity, port engines/data qualification and measured optimization remain incomplete. Use the plan's feature matrix and update it with actual results. Source-tested patches need a reviewed release application path, not silent writes.
6. **Run original TG5040 tests on a spare/restorable card when hardware is available.** Capture installed firmware, libraries, devices, config writers, boot/scene hashes and save checksums; prove original-card/internal-startup restore, classic fallback, launch/return, saves, suspend/power, USB clean unmount and FAT/exFAT interruption recovery. Only then qualify the corresponding profile fields. No device is connected in this checkpoint.

## Critical contracts

- Runtime/principal remains the process owner. Existing PyUI stages `/tmp/cmd_to_run.sh`; the principal loop executes it. `sh -n` is not semantic validation. Fixed action tokens delegate existing initialized callbacks.
- Preserve lexical launch spelling `Emu/<system>/../../spruce/scripts/emu/standard_launch.sh`; canonicalizing the invoked path breaks `$0`-based system detection. Validate containment separately.
- Favorites/recents are PyUI JSON arrays. Some existing manager constructors rewrite/prune them: use the pure read-only snapshot path for inspection, and inject already initialized live managers for writes.
- Per-game preset keys use ROM basename **including extension**; duplicate basenames can share an override. Unknown stored presets must not silently pick another engine.
- PPSSPP authoritative platform INIs are under `Saves/.config/ppsspp/PSP/SYSTEM/`; spruce copies platform to active at launch and back on exit. Preserve writers and never edit gameplay controls to implement UI-only conventions.
- Keep `enableButtonWatchers=false` and the existing `save_poweroff.sh` route. Do not introduce another power owner. Existing USB staged export uses reboot and clean unmount; the fourth source patch refuses its legacy mounted-export failure branch. Release application and physical storage/UI-return qualification remain pending.
- Source hash matches do not qualify hardware. Shipped `hardware_qualified`, `runtime_verified`, `source_use_verified`, emulator fingerprints/extension and writer gates remain false/unsupported.
- Package rollback is distinct from whole-card, internal boot/scene and vendor recovery. A rollback never restores older user saves over newer data.

## Licences and external actions

Original Python/palette code is MIT and Noto Sans is OFL. PPSSPP patches/fixtures are separately GPL-2.0-or-later with exact retained notices. Spruce/PyUI terms and attribution remain separate; do not label the whole offshoot MIT or assume original code changes upstream rights.

The pinned nested PyUI licence includes an author-notification requirement for use including derivatives. A draft exists at `project/docs/author-notification-draft.txt`; **nothing has been sent**. Source-use and derivative distribution remain unresolved gates. Continue independent original helpers, tests and PPSSPP work without inventing an approval requirement for those tasks. Do not send email/Slack/other outreach without the user's explicit send instruction. Do not mark the source-use gate complete from the draft alone.

## Workspace continuity

Current worktree: `/workspace/trimui`. Restored untouched sparse host references:
`/workspace/spruce-base` and `/workspace/ppsspp-source`. Preview virtual
environment: `/workspace/scratch/trimui-buildenv`. The prior environment's full
PPSSPP checkout, recipe, SDK, target executables/source archives and full spruce
release archive are not present in this environment. Their sanitized saved
evidence remains in GitHub; reconstruct inputs from the pinned build procedure
when needed. This continuation has not repeated the complete target cross-build.
Current host development artifacts are
`/workspace/scratch/trimui-development-20261022-dev3`. They can be rebuilt with
`project/packaging/dev_release.py`;
scratch paths are conveniences, not the durable handover.

Only repository source, licences and saved evidence should be relied on in a new environment. Recreate dependencies/checkouts using the pinned identities. Never commit signing private keys, card dumps, user saves, proprietary game data, downloaded base distributions or credentials. Continue saving coherent commits and updating this handover as work advances.
