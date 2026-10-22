# TrimUI Smart Pro implementation handover

Checkpoint: 22 October 2026. Active branch: **`build/spruce-psp-experience`** in `daniel1990000/CrossMix-OS-project`.

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
| `project/bridge/` | Lazy frontend seam and exact-source MainMenu hook staging. Default unbound/unqualified execution stays classic. No installed hook is enabled. |
| `project/psp_shell/settings.py`, `controls.py` | Format-preserving transactions, previews, generations, writer/hash gates, compensating backends, recovery and targeted undo. Three shipped emulator profiles remain unqualified. |
| `project/ppsspp/` | Upstream v1.20.3 source patch, exact source/patch hashes, GPL notices, actual C++ acceptance harness, original PPSSPP themes and detailed reuse decisions. |
| `project/psp_shell/ppsspp.py` | Original theme adoption helper, preview, backup, qualified stopped-writer gates, multi-file recovery and undo. Not yet wired to a common settings UI. |
| `project/patches/` | Three pinned spruce fixes: quote the launcher directory, refuse insecure TLS retry, preserve actual archive extraction exit status. Stored as reviewable patches only. |
| `project/packaging/`, `project/tools/build_payload.py` | Deterministic signed scoped overlays, strict archive verification, fixture staging/activation/health/rollback and development artifact builder. |
| `project/tools/` | Read-only inventory/support, offline migration, read-only benchmark collection and fixture creation. |
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

The PPSSPP patch is real source work: it reuses ConfigSetting serialization, SDL input translation, native menu key handling and existing settings widgets. Opt-in `[ProjectNativeMenu] IndependentMenuControls` defaults false; physical south/east Confirm/Back stays separate from PSP gameplay and ButtonPreference. Tests compile selected real patched functions with explicit narrow fixtures. **A full emulator build and target qualification are still outstanding.**

## Next concrete work

1. **Finish qualified PyUI bootstrap and return binding.** `context_from_running_pyui` and `bind_context_factory` exist, but the live trusted factory is intentionally absent. Bind already initialized Device/Display/Controller, existing models, explicit stop-background/release/restore callbacks and live independent hash inventory. Preserve MainMenu's existing GameSwitcher, box-art and game-selection-only prelude. Readiness requires a real successful input poll. Advanced existing menu routes also carry foreground tokens. Clear uncertain handoff records only from a verified spruce return seam; never launch a second UI over an uncertain surviving game.
2. **Build the complete PPSSPP source candidate separately.** Reproduce the pinned PowerVR/SDL toolchain and patches, apply the native-menu extension in a separate tree, build the full engine, verify ABI/library dependencies and retain corresponding source/notices. Keep the installed engine unchanged until save compatibility and input/rendering qualification pass. In upstream SDL, south/east are `NKCODE_BUTTON_2/3`, not Android `BUTTON_A/B`. Check other native-action collisions under unusual gameplay remaps.
3. **Connect common controls and matching PPSSPP appearance.** Dispatcher `controls.*` and the UI profile flow are implemented. The PPSSPP theme manager is tested but not exposed in the common UI. The current emulator adapter writes the Confirm/Back extension pair; it must also verify/enable the opt-in `IndependentMenuControls` state through a reviewed qualified transaction before declaring the feature effective. Extend that contract and tests. Keep standard RetroArch, spruce IGM and native PPSSPP surfaces separate; the IGM adapter is still unsupported.
4. **Implement exact in-emulator state evidence for real Resume.** Reuse PPSSPP SaveState APIs from inside the emulator; no external state protocol has been fabricated. Verify state operation success, exact game/engine/state identity and metadata. Do not guess `.ppst` paths, infer success from a screenshot or repurpose battery saves as states.
5. **Complete the whole-system plan and physical qualification.** Hardware settings and advanced utilities should delegate to existing spruce authorities. Networking/power/sleep/USB, high-level settings UI coverage, all emulator/native-screen visual parity, port engines/data qualification and measured optimization remain incomplete. Use the plan's feature matrix and update it with actual results. Source-tested patches need a reviewed release application path, not silent writes.
6. **Run original TG5040 tests on a spare/restorable card when hardware is available.** Capture installed firmware, libraries, devices, config writers, boot/scene hashes and save checksums; prove original-card/internal-startup restore, classic fallback, launch/return, saves, suspend/power, USB clean unmount and FAT/exFAT interruption recovery. Only then qualify the corresponding profile fields. No device is connected in this checkpoint.

## Critical contracts

- Runtime/principal remains the process owner. Existing PyUI stages `/tmp/cmd_to_run.sh`; the principal loop executes it. `sh -n` is not semantic validation. Fixed action tokens delegate existing initialized callbacks.
- Preserve lexical launch spelling `Emu/<system>/../../spruce/scripts/emu/standard_launch.sh`; canonicalizing the invoked path breaks `$0`-based system detection. Validate containment separately.
- Favorites/recents are PyUI JSON arrays. Some existing manager constructors rewrite/prune them: use the pure read-only snapshot path for inspection, and inject already initialized live managers for writes.
- Per-game preset keys use ROM basename **including extension**; duplicate basenames can share an override. Unknown stored presets must not silently pick another engine.
- PPSSPP authoritative platform INIs are under `Saves/.config/ppsspp/PSP/SYSTEM/`; spruce copies platform to active at launch and back on exit. Preserve writers and never edit gameplay controls to implement UI-only conventions.
- Keep `enableButtonWatchers=false` and the existing `save_poweroff.sh` route. Do not introduce another power owner. Existing USB staged export uses reboot and clean unmount; its legacy failure branch still needs qualification/repair.
- Source hash matches do not qualify hardware. Shipped `hardware_qualified`, `runtime_verified`, `source_use_verified`, emulator fingerprints/extension and writer gates remain false/unsupported.
- Package rollback is distinct from whole-card, internal boot/scene and vendor recovery. A rollback never restores older user saves over newer data.

## Licences and external actions

Original Python/palette code is MIT and Noto Sans is OFL. PPSSPP patches/fixtures are separately GPL-2.0-or-later with exact retained notices. Spruce/PyUI terms and attribution remain separate; do not label the whole offshoot MIT or assume original code changes upstream rights.

The pinned nested PyUI licence includes an author-notification requirement for use including derivatives. A draft exists at `project/docs/author-notification-draft.txt`; **nothing has been sent**. Source-use and derivative distribution remain unresolved gates. Continue independent original helpers, tests and PPSSPP work without inventing an approval requirement for those tasks. Do not send email/Slack/other outreach without the user's explicit send instruction. Do not mark the source-use gate complete from the draft alone.

## Workspace continuity

Original worktree: `/workspace/trimui`. Source-only references: `/workspace/spruce-base` and `/workspace/ppsspp-source`. Preview virtual environment: `/workspace/scratch/trimui-buildenv`. Verified full archive and selected members: `/workspace/scratch/spruce-release/`. Development artifacts can be rebuilt with `project/packaging/dev_release.py`; scratch paths are conveniences, not the durable handover.

Only repository source, licences and saved evidence should be relied on in a new environment. Recreate dependencies/checkouts using the pinned identities. Never commit signing private keys, card dumps, user saves, proprietary game data, downloaded base distributions or credentials. Continue saving coherent commits and updating this handover as work advances.
