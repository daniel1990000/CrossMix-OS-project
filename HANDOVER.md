# TrimUI Smart Pro implementation handover

Checkpoint: 22 October 2026. Active branch: **`build/spruce-psp-experience`** in `daniel1990000/CrossMix-OS-project`. Work is saved in [draft PR #1](https://github.com/daniel1990000/CrossMix-OS-project/pull/1). The inherited CrossMix tree is historical reference and an offline migration source. The active implementation is under `project/`.

## Five-task batch U04 / D04 / P01–P03 — 22 October 2026

All five requested tasks are complete as host engineering work. The [master plan](project/docs/master-plan-2026-10-22.md) now records 11 of 25 tasks complete. See [the exact batch evidence](project/evidence/host-batch3/verification.json), [measurement methods](project/docs/host-measurement.md) and [port preparation/save contracts](project/docs/ports-preparation-and-saves.md).

U04 adds a synthetic 10,000-entry corpus, complete pagination/focus/Unicode checks and a bounded live model cache cleared on explicit refresh. The unchanged baseline rebuilt every entry for every query (~6 seconds on this host); corrected warm page/search queries are in tens of milliseconds. These are synthetic host workloads, not device gains. Empty files remain review-only and malformed individual entries do not hide valid games. Existing upstream managers, preset conventions and execution ownership remain intact.

D04 records real standalone SDL presentation-return timings, separate render/present durations, bounded samples and fixed navigation scenes. The read-only PID sampler now records child CPU and optional PSS while retaining identity and truncation limits. Physical video/audio/energy methods are specified separately; unmeasured hardware metrics remain unavailable.

P01 inspects the actual PortMaster package/class/registration, legacy marker and pending self-updates without executing them. Sonic includes Game.so/libogg; helpers, local libraries and managed Mono are inventoried. P02 reproduces Celeste's false success and checks the exact optional fix against pinned source, with failed repack/mount/bind/full-storage, retry, cleanup and pipeline failure fixtures. P03 distinguishes generated Render96 resources from a consumed input ROM and keeps Celeste owner files mandatory. Scoped external save backups, reviewed transactional restores and undo preserve unlisted slots. All save paths still need physical readback before uninstall; the inventory tool never deletes ports.

The full strict run passes **690 checks** (629 host/source + 61 PPSSPP), with zero skips, failures, errors or expected failures. Certification and CI now require **five** untouched pinned checkouts: SPRUCE_SOURCE_ROOT, PPSSPP_SOURCE_ROOT, SPRUCE_RA_SOURCE_ROOT, PORTS_SOURCE_ROOT and PORTMASTER_SOURCE_ROOT. The first full attempt caught a refresh regression in retained model bindings; its failed result is retained separately. The original assertion was preserved and the corrected implementation passes.

The descriptor selects **dev9**, an original-only host preview. The optional Celeste source diff remains unselected, all runtime/rights/device flags remain false, all 13 physical acceptance areas remain unrun, installed engines/owner data are unchanged, and PR #1 stays draft and unmerged. Next: R04 artifact custody, D01 experimental-route design and D02/D03 operator preparation, alongside actual R05/R06 evidence. No author communication is authorized by this continuation.

## Interface batch U01–U03 — 22 October 2026

The next three [master-plan](project/docs/master-plan-2026-10-22.md) tasks are complete as host engineering work. PNG, JPEG, BMP, static WebP and QOI now work through both decode paths. An original bounded QOI decoder avoids a new device dependency. Header checks bound native decoder allocation; malformed/oversize data and missing codecs produce the existing placeholder. [Format evidence and limits](project/docs/artwork-formats.md) distinguish actual host codec tests from untested target libraries.

**Games → Refresh library**, also available through F5, invalidates source metadata and positive/negative artwork caches. Refresh preserves the page and focused game or nearest surviving neighbor, clamps a removed page, and rejects stale asynchronous completions. Live integration retains initialized PyUI managers and the existing scanner/launch authorities.

The keyboard now has 50 keys, title punctuation and wide action keys. Text, field, actions and controller help scale through 1.75. Physical hints follow South/East Confirm and show Cancel/Delete/Find; long text shows its suffix and end cursor. The standalone preview's external Unicode input stays bounded to 128 code points. Embedded text entry follows the existing PyUI input route, including remapped buttons. [Accessibility notes](project/docs/interface-accessibility.md) define entry, deletion and font limits. The new `ui/keyboard.py` is mandatory in the signed source inventory.

The full local strict run passes **621 checks**: 560 host/source and 61 PPSSPP, with zero skips, failures, errors or expected failures. This includes 40 new format, refresh and keyboard checks, including the actual embedded input route under both Confirm conventions and inverse button remaps. [Normal keyboard](project/evidence/ui-polish/keyboard.png), [maximum-size keyboard](project/evidence/ui-polish/keyboard-large.png) and [QOI cover](project/evidence/ui-polish/artwork.png) captures are actual SDL host renders with original synthetic data. The capture script and [verification record](project/evidence/ui-polish/verification.json) are retained.

A preceding full run passed 620 of 621 checks and failed while waiting for a test orphan to publish its PID. The unchanged test passed all 20 predetermined diagnostic attempts, and a controlled 3.25-second setup delay reproduced the same three-second readiness failure. The fixture now publishes readiness atomically and waits with a six-second deadline and helper-liveness checks; production ownership logic and assertions are unchanged. All 21 synchronized diagnostic attempts and the 21-test principal suite pass. The failed certification is retained separately; the original host delay was not conclusively located.

The descriptor now selects **dev8**. Development artifacts at `/workspace/scratch/trimui-interface-dev8` pass signature/inventory verification, same-key deterministic rebuilding, installed-payload rendering/settings/navigation smoke and fixture activation/rollback. The no-Git source export reproduces the preview and source ZIPs byte for byte. All artifact checksums, changed runtime bytes and retained MIT/OFL notices were read back. The host uses Pillow 11.1.0 and isolated SDL_image 2.8.8. No device runtime library, installed engine or qualification gate changed; all 13 physical areas remain unrun. Source-use/distribution evidence and private native artifact custody remain open; PR #1 stays draft and unmerged.

Implementation [`c42c003`](https://github.com/daniel1990000/CrossMix-OS-project/commit/c42c003a147c614788c1e22b58be3e573f6901a3) passes [GitHub CI run 39858609637](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39858609637): all **621 checks**, zero skips/failures/errors/expected failures, dev8 packaging and upload. The clean PR merge checkout is `77b26c92b1dece2e114aa2097aef3b461b58b73c`; signed metadata records that identity. [Download host-preview-evidence](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39858609637/artifacts/12460398356), artifact ID `12460398356`, SHA-256 `6f01d358a84bcce58bd88fdf4bd6fca531e06d2a258c29c5182ef4c0966e8aea`. The complete download and all eight inner artifact checksums were verified; the source inventory matches the local build. Later evidence/handover text changes preserve the tested implementation hashes and packaged source inventory.

Suggested next group: **U04** large-library fixtures, **D04** measurement tooling and **P01** port dependency inventory. These are independent host tasks; physical qualification remains a separate stage.

## Previous release tooling batch R01–R03 — 22 October 2026

The first three tasks in the [master plan](project/docs/master-plan-2026-10-22.md) are complete. The inherited CrossMix release workflow is archived byte for byte in `docs/historical/`, outside Actions discovery. The remaining host workflow has read-only repository permissions and no tag/release trigger; release tags must use a revision containing this isolation change.

`project/dev/check.sh` now requires all three explicit pinned source roots. Certification checks their commits and materialized bytes before and after testing, rejects skipped/empty/incomplete suites and expected failures, and writes actual counts/identities to `dist/certification.json`. CI watches `docs/spruce-source-lock.json` and uploads failure records.

At this checkpoint `project/packaging/current-release.json` selected **dev7**. CLI and CI use the descriptor by default. Signed metadata and the build report record the exact frontend commit, modified-source status and a SHA-256 inventory. Exported original source retains that provenance and rejects changed bytes when rebuilding. Native binary hashes are historical references only; no upstream patch or native binary is selected.

The complete local certification passes **581 checks**: 520 host/source and 61 PPSSPP, with zero skips, failures, errors or expected failures. The unchanged baseline also passed all 561 checks in this workspace. See [batch evidence](project/evidence/release-tooling-batch1.json) for the actual certification and development package results. This session validates host behavior; all 13 physical acceptance areas remain unrun.

Implementation [`9a8e772`](https://github.com/daniel1990000/CrossMix-OS-project/commit/9a8e77232cd2b6908c4e5cae17312e4a2d942068) passes [GitHub CI run 39853492605](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39853492605): all **581 checks**, zero skips/failures/errors/expected failures, dev7 packaging and upload. GitHub tested its clean PR merge checkout `b31f7e4d96bb7a6bf33b286d9f6e3699a11469dc`; the signed package records that exact frontend identity. [Download host-preview-evidence](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39853492605/artifacts/12457629490), artifact ID `12457629490`, SHA-256 `d37d8396fe7dd5ac060dd65faccee9fc020b422b1b580588340f3a57c0a7ee9b`. The complete download and all inner artifact checksums were verified. Local no-Git export rebuilds reproduce the preview and source ZIPs exactly. Later evidence/handover/master-plan text changes preserve the tested implementation hashes.

At this earlier checkpoint the suggested batch was **U01–U03**, now completed above. R04 artifact custody, device preparation and external source-use/distribution evidence remain open. Keep PR #1 draft and unmerged. These prior private artifacts are under `/workspace/scratch/trimui-release-tooling-dev7`; they may need rebuilding after environment replacement.

## Inherited integration checkpoint

The current checkpoint completes the host software integration, common settings, PPSSPP state protocol/Resume route, native menu extensions, source composition/restoration tools and private source builds. Read the final records in [project/evidence](project/evidence/) for actual host counts, build fingerprints and development packaging results. Host fixtures, complete native cross-builds and physical qualification remain separate claims.

The inherited software checkpoint passed **527 host checks with zero skips or failures**: 466 Python/SDL/source-integration checks and 61 PPSSPP C++/build-tool checks. The **dev4** original-only development artifacts pass signature/inventory verification, deterministic rebuilds, installed-payload rendering and fixture activation/rollback.

**On 22 October 2026, the owner confirmed an original Smart Pro is available, but not for testing that day.** Physical acceptance has not been performed. PyUI notification delivery and exact recipe/SDK redistribution review remain open. Installed emulators are unchanged; runtime/profile activation stays disabled, and engine binaries/full recipe archives stay private.

## Latest source study and menu polish — 22 October 2026

Implementation: [`8768ab0`](https://github.com/daniel1990000/CrossMix-OS-project/commit/8768ab042da2c89c0087d068453bfd58f68445f5). The complete local run passes **561 checks** (500 host/source and 61 PPSSPP), with zero skips, failures or errors. Exact-commit [GitHub Actions run 39822730380](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39822730380) also passes all **561 checks**, with zero skips/failures/errors, dev6 packaging and artifact upload. [Download the current host-preview-evidence](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39822730380/artifacts/12445751282), artifact ID `12445751282`, SHA256 `764c8ed367185094a3c876a926c67869da4aa5eb80e4fc7fcac8f410265556ed`. Subsequent handover/evidence-only commits do not change this tested implementation.

The owner asked for deeper study of the three supplied repositories. The [source study](project/docs/psp-source-study.md) and exact-file traces cover their active menu/navigation/text/artwork paths; this is not a whole-repository audit or binary-decompilation claim. Source-backed fixes now snap pagination/reordered rows correctly, retain the nearest row after a Favorite disappears, explicitly reset newly opened Settings views, reuse glyph textures across tint/shadow/alpha changes, and mark repeated/blank paragraph overflow correctly. Options titles use two measured lines, with full overflow titles retained in message pages.

Review the fresh [home](project/evidence/source-study/home.png), [library](project/evidence/source-study/library.png), [long-title options](project/evidence/source-study/options.png) and [maximum-text options](project/evidence/source-study/large-text-options.png). These are actual SDL host captures with original synthetic metadata and the actual host clock. The capture script is included. The original [Sony PSP comparison](project/evidence/psp-design/comparison.png) remains available for the unchanged overall composition.

The deterministic glyph probe drops raster/uploads from **165 to 1** and cached data from **7,470,540 to 45,276 bytes** for 100 alpha changes of one text shape. These are host scenario counts, not whole-application/device measurements. The original-only **dev6** package at `/workspace/scratch/trimui-deep-study-development-final` passes signed inventory verification, deterministic rebuilds, installed-payload rendering/settings/navigation smoke and fixture rollback. Overlay SHA256: `11e97ec0b974707e782d518dfd1542a841c9f02680a3e4fac48f6d63deab52e4`; all published checksums and the three changed runtime modules were read back. See [verification](project/evidence/source-study/verification.json).

The first full run exposed a cross-view focus regression and a preexisting fake-readiness ordering race. New-view focus is now explicit; an existing principal-shell fixture waits for its actual resident-start marker with a deadline. Production principal behavior and exact assertions remain unchanged. The failed run is retained outside the passing count; 20 repeated readiness cases and all 21 principal checks pass. No emulator binary, shipped activation gate or owner data changed. Physical TG5040 acceptance and prior external release evidence remain open; PR #1 stays draft and unmerged.

## Classic PSP visual overhaul — 22 October 2026

Verified implementation: [`86509e1`](https://github.com/daniel1990000/CrossMix-OS-project/commit/86509e12ccccc3df4d69c95257efabb294752f03). [GitHub Actions run 39818966902](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39818966902) passes all **542 checks** (481 host/source and 61 PPSSPP), with zero skips/failures/errors, dev5 packaging and artifact upload. [Download the current host-preview-evidence](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39818966902/artifacts/12443392152), artifact ID `12443392152`, SHA256 `0da80fe550c8ab7829952798a88f9c766a42757e60303b67b807be0e1acb0b32`. Subsequent screenshot/evidence/handover-only commits do not change this tested implementation.

The frontend now follows the original PSP XMB composition: anchored horizontal categories, a vertical item column, selected-only category labels, original white pictograms, a brighter blue color field, two broad wave surfaces, flat options and a clean keyboard workspace. The actual coordinator clock appears at top right. Cover loading now handles queue pressure, cache eviction and reduced-motion completion reliably. SDL version/backend fallbacks retain the existing graphics runtime.

The owner explicitly requested use of PPSSPP, JohnnyCollado/PlayFieldPortal and sashkinbro/EmuCoreA. Their exact revisions and applied layout/motion/cover/native-theme decisions are in [visual design notes](project/docs/psp-visual-design.md). The PPSSPP palette matches the azure frontend through supported native fields; gameplay/config authority and native layouts remain with their existing owners.

Review the [new screens](project/evidence/psp-design/gallery.png), [actual Sony PSP comparison](project/evidence/psp-design/comparison.png), [individual home capture](project/evidence/psp-design/home.png) and [verification record](project/evidence/psp-design/verification.json). Captures are SDL host renders, not physical-device photos. The Sony reference is comparison evidence outside the development payload.

Local validation passed all 479 host/source and 61 PPSSPP checks with zero skips/failures/errors, followed by all 44 final UI checks and 40 final principal/source-binding/release checks. The two added rendering cases cover the clean keyboard and older/unsupported SDL paths. The dev5 original-only package passes signature/inventory, deterministic rebuilds, installed-payload smoke and fixture rollback. The final exact-code CI run also passes all 542 checks. Physical TG5040 acceptance and previously recorded external release evidence remain open; no installed emulator or activation gate changed. Both new rendering modules are now mandatory in the verified module inventory. A preexisting CI race fixture was made deterministic by serializing only its real preflight health reads; production locks and exact one-use consumption assertions are unchanged. The final dev5 package is at `/workspace/scratch/trimui-design-development-final`.

## Continuation — 22 October 2026

The acceptance recorder now retains a selected save that disappears after the baseline as explicit `missing=true`, `unchanged=false` evidence, including a missing save directory. It never recreates or restores that save. Reports expose the comparison; baseline saves remain mandatory, and symlinks/special files/inconsistent observations still fail collection. Five regression tests cover these cases.

Support export now redacts whole strings containing ROM/save paths and path-keyed entries, preventing filename fragments with spaces, quotes or newlines from leaking. Two regression tests cover structured and raw diagnostics. Unrelated structured status fields remain available; a plain-text log containing a private path can be redacted entirely.

The [continuation rights review](project/docs/continuation-rights-review.md) records exact outstanding evidence and absent historical private artifacts. No device was attached or tested, no notification was sent, and no gate, installed emulator or owner save changed. Private native binaries/source archives must be recovered and hash-verified or rebuilt before use; historical SDK audit results have not been rerun here.

Local validation: 21 acceptance tests and 13 inventory/support tests pass. The full host run attempted all 473 tests, with 14 failures and 22 errors in process-identity/lifecycle tests in this sandbox: Python's PID differs from `/proc/self` and `/proc/<pid>/stat` is absent. This is not a full passing run. Do not weaken identity checks or count those failures as skips. The continuation passes all **534 checks in GitHub CI** (473 host/source and 61 PPSSPP), with zero skips/failures/errors; see the exact commit and run below. Original-only development packaging passed signature/inventory, deterministic rebuild, installed-payload smoke and fixture rollback at `/workspace/scratch/08e013647ad3/development-continuation`.

The recreated private source-review kit is `/workspace/scratch/08e013647ad3/source-review-continuation`; verification with the external development public key passed. The fresh `/workspace/scratch/08e013647ad3/device-acceptance-ready` session has all 13 areas `not_run`. These paths are temporary workspace outputs, not a claim that previous private native archives survived. See [continuation evidence](project/evidence/continuation-acceptance-hardening.json).

## Previous verified checkpoint — acceptance hardening

- Implementation commit: [`37c330c6ebf8dd2e846003ee072eb2e0cf7f1bb1`](https://github.com/daniel1990000/CrossMix-OS-project/commit/37c330c6ebf8dd2e846003ee072eb2e0cf7f1bb1).
- [GitHub Actions run 39812635602](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39812635602): **success**, all **534 checks**, zero skips/failures/errors, development packaging and artifact upload. Host job `119942691297` reports 473 and 61 tests.
- [Updated original-only development artifact](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39812635602/artifacts/12441400284): ID `12441400284`, SHA256 `4fa98d8ec5d17850e885122adaf851e31a675cc574666d25a75b3ab5ddcfbc91`. No native engine/SDK binary is included. Later evidence/handover-only commits do not change the tested implementation.
- PR #1 remains draft and unmerged. Next milestone: original-device acceptance and actual source-use/distribution evidence, not additional host tests as a proxy.

## Inherited build checkpoint

- Software/build commit: [`42c83f699225a57251e9322f351fbda72c053830`](https://github.com/daniel1990000/CrossMix-OS-project/commit/42c83f699225a57251e9322f351fbda72c053830).
- [GitHub Actions run 39810880610](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39810880610): **success**, including all 527 checks, development packaging and artifact upload. Host job `119936465324` reports 466 and 61 tests, with zero skips.
- [Download `host-preview-evidence`](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39810880610/artifacts/12440875335), artifact ID `12440875335`, SHA256 `53f50c8691d8059baa5884b146f60a7fef41e0dccd31b1e09d55fafce29bf200`. It contains the original-only preview, scoped dev4 overlay, original source ZIP, checksums and build report. No native engine or SDK binary is included. GitHub currently lists expiry as 20 January 2027; rebuild from source if unavailable.
- [Draft PR #1](https://github.com/daniel1990000/CrossMix-OS-project/pull/1) records final scope, validation and remaining external evidence. It is open and unmerged.
- [Next-chat prompt](NEXT_CHAT_PROMPT.txt) is ready to paste into a new chat. Documentation-only commits after the software SHA above do not change the tested code; run the checks again after implementation changes.

## User direction and start point

Build a polished PSP-inspired whole-system experience for the **original TrimUI Smart Pro TG5040**, extending spruceOS v4.5.4 and its shipped PyUI. Retain existing device support, emulators, settings, games and saves. Reuse maintained projects, research beyond supplied links, work autonomously with parallel agents, and retain implementation/evidence/handovers in GitHub. Do not resume the superseded CrossMix/C++ runtime architecture.

Read [project/README.md](project/README.md), the active part of [TRIMUI_PLAN.md](TRIMUI_PLAN.md), [coverage](project/docs/feature-coverage.md), [binding](project/bridge/README.md), [state integration](project/ppsspp/state-session.md) and [release qualification](project/docs/release-qualification.md). Review PR checks at the exact branch SHA; a previous green run does not cover later edits. Keep the PR draft until the device and release evidence is available.

A lightweight checkout avoids the large historical payload:

```sh
git clone --filter=blob:none --sparse --branch build/spruce-psp-experience https://github.com/daniel1990000/CrossMix-OS-project.git trimui
cd trimui
git sparse-checkout set --no-cone /project/ /.github/workflows/ /docs/ /HANDOVER.md /NEXT_CHAT_PROMPT.txt /AGENTS.md /TRIMUI_PLAN.md /README.md /.gitignore /.gitattributes
```

## Implemented source

| Path | Current behavior |
|---|---|
| `project/psp_shell/ui/`, `app.py` | Original SDL interface, four categories, library/search/favorites, dialogs, accessibility, waves, original assets and headless/desktop preview. Checkpoint verification times appear only from authenticated backend records. |
| `project/psp_shell/adapters/spruce.py`, `library.py` | Read-only source snapshots or already initialized PyUI models, existing platform/preset filtering, exact ROM identity and token-bound original callbacks. |
| `project/bridge/process_source.py`, `principal.py`, `principal_integration.py` | Exact-source initialized model/menu/game/principal seams; Linux child-subreaper ownership including double-fork/setsid descendants; sealed staged commands preserving `$0`; correlated foreground completion. Fixed `qualified_runtime.py` defaults to `None`. |
| `project/psp_shell/hardware_settings.py`, `embedded.py` | Common brightness/volume/radio controls through existing initialized authorities, shared writer window, stale previews and configuration readback; fixed Wi-Fi/Bluetooth/controller/power/USB/apps/collections/advanced/per-game routes. Source menus retain their own layouts and hardware behavior. |
| `project/psp_shell/controls.py`, `ppsspp.py` | Separate frontend/game/menu policies, standard RetroArch and spruce IGM adapters; one PPSSPP controls/appearance transaction with five-file journal, stopped-writer checks, verified per-game override inventory, recovery and protected Undo. |
| `project/psp_shell/state_evidence.py` | Private session creation by the principal owner, exact native save/load validation, independently stopped writers and boot-bound authenticated capability transfer to fresh UI processes. Typed Resume uses the original game callback; arbitrary card JSON cannot grant it. |
| `project/ppsspp/` | Pinned native controls, completion API, private session protocol and checked save-and-quit patches; real C++ source acceptance; full PPSSPP/FFmpeg candidate build, ABI audit and retained corresponding-source tooling. Separate GPL scope. |
| `project/retroarch/` | Actual spruce IGM independent raw Confirm/Back extension, source parser/action acceptance, source locks/notices and full original-TG5040 candidate builder. Separate GPL scope. |
| `project/patches/`, `integration/` | Four reliability fixes plus separately selected PPSSPP wrapper forwarding; exact source inventory, original overlay verification, all-or-none private composition, signed expanded-module binding and exact-preimage restoration to a new output. No live installation command. |
| `project/psp_shell/ports.py`, `profiles/ports*` | Pinned launch-script/metadata contracts, owner-data import/staging/backup/Undo, read-only installed engine/Mono/support inventory and original spruce launch-token reuse. GTA III/VC, Sonic Mania, Celeste and Render96 remain candidates; San Andreas is disabled/experimental. |
| `project/tools/`, `packaging/` | Read-only installed-runtime probe, migration/support/benchmark tools, signed scoped original-only overlays, deterministic rebuild/smoke/fixture rollback, and private operator device acceptance recording. |

The legacy retained-thread/cooperative-audio source experiment remains available for comparison. **Select one integration mode; never apply it together with the process-boundary patch.** Process exit preserves all existing PyUI threads and releases their descriptors as one owned process subtree. No helper may kill or ignore an unknown child to announce successful return. A shell exit, missing command or arbitrary serialized receipt is insufficient.

## Exact source and build identities

- Spruce stable **v4.5.4**: `d45ff8dfe5756147522b04ae5863d17a90e88b54`; PyUI tree `4d0bdb3111d9226fbacbea6c89d65e540620e21e`. The complete stable archive was independently hashed: 1,652,634,074 bytes, SHA256 `4623f1cd824ac1d01e7663d11ca40a8d3ad874c5f071e692f4392957d2159cfd`. Ten selected integration/licence files match Git; see [release-source audit](project/evidence/release-source-audit.json).
- PPSSPP **v1.20.3**: `d357e6a32934800d3d80b49f910a603e1b069751`; spruce PowerVR recipe `9f770cb984fd8ffcc8f91d24fcbca859439c2e9b`. New state/API/recipe-override locks are separate from the original menu-only lock.
- Current complete PPSSPP candidate: **19,934,560 bytes**, SHA256 `a93f7db82692c4b95dcb15282d8d73080d51a8912fc8e435adb3b6dfe30c165d`. It compiles project patches 0001–0004, all ten selected spruce patches and pinned FFmpeg. The recursive **16-object SDK audit passes**, requiring only GLIBC 2.17. FFmpeg's actual configuration is LGPL-2.1-or-later with GPL/nonfree/version-3 options disabled; 55 named component notices are retained. See [complete state build](project/evidence/ppsspp-complete-state-build.json). No target executable was run.
- Earlier PPSSPP build attempts remain evidence: [initial build](project/evidence/ppsspp-candidate-build.json) linked against too-new libc symbols; [corrected menu-only build](project/evidence/ppsspp-sdk-search-build.json) fixed GCC9/SDK searches and rebuilt pinned FFmpeg. Their hashes/results do not describe the later state-session binary.
- The [first state-session build](project/evidence/ppsspp-state-session-initial-build.json) passed compilation/SDK checks but lost the first successful checkpoint's export after a later failure in the same request. The later retained-success protocol fixes that source behavior and has separate binary/source identities.
- RetroArch **v1.22.2**: `69a4f0ea1e8aaf442ae4858f2e7f2b31a1776576`; actual spruce IGM recipe `71d84da4dc88945177a3eb34268013355c705dbd`. The new IGM controls patch SHA256 is `39ecc22a4b43bf210132df9d30c6a7c8869b19afca4953ec9585807bcbbec5a6`. [Native build instructions](project/retroarch/build-candidate.md) record original-target SDK adaptations separately from source acceptance.
- Current complete RetroArch/IGM candidate: **15,182,848 bytes**, SHA256 `118146e2aed90c5ccbc416e4c7e01acc8ec7abb7462e1d43f97e8734f113df1d`. The recursive **23-object SDK audit passes**. Original-target adaptations disable unavailable Vulkan, preserve bundled compatibility-header precedence and link the proved GCC9 C++ runtime statically. Earlier configure/link/audit failures are retained separately. See [complete IGM build](project/evidence/retroarch-igm-build.json). The private binary and source/build archives live under `/workspace/scratch/retroarch-igm-tg5040-final`. No target executable was run.
- Bundled stable executable observations are separate: PPSSPP SHA256 `d0635cdb73e046cf8c62a92a4c59194cf9a80dfabbe08a0c9a0cb4628a1c96d7`, embedded v1.20.3; `ra64.universal` SHA256 `bd96dd8f10c479d17ff4a5db943a6828ccb0b74c6eb463faeb99d941fa16d550`, embedded 1.22.2. Version strings do not establish exact source correspondence or installed-device identity.

## Verification and workspace continuity

Run all host checks with three untouched pinned references. Source-dependent skips do not count as a complete pass:

```sh
PYTHON=/workspace/trimui-venv/bin/python \
SPRUCE_SOURCE_ROOT=/workspace/trimui-sources/spruce \
PPSSPP_SOURCE_ROOT=/workspace/trimui-sources/ppsspp \
SPRUCE_RA_SOURCE_ROOT=/workspace/trimui-sources/retroarch \
PYSDL2_DLL_PATH=/workspace/scratch/trimui-host-sdl-image/root/usr/lib/x86_64-linux-gnu \
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
sh project/dev/check.sh
```

The preview environment uses PySDL2 0.9.17 and Pillow 11.1.0 with system SDL2/libsodium. Source tests need Git, host C/C++ compilers and binutils. CI checks out all three exact sources and uploads original-only development artifacts; it does not publish native emulator/SDK outputs.

Build the current original-only preview from its descriptor with a new output directory:

```sh
python3 project/packaging/dev_release.py --output /workspace/scratch/trimui-interface-dev8 --include-source --smoke-python /workspace/trimui-venv/bin/python
```

Private PPSSPP output lives under `/workspace/scratch/ppsspp-complete-checkpoint-final`: `output/PPSSPPSDL_TrimUI` and `candidate-corresponding-source.tar.gz`. The exact final source archive size and SHA256 are recorded in `project/evidence/ppsspp-complete-state-build.json`. The earlier 640ce8 binary and its matching archive remain under `/workspace/scratch/ppsspp-complete-state-final` as historical evidence. Source/recipe/SDK inputs are untouched in sibling scratch directories. Private workspace files may be absent after environment replacement; rebuild from locks and never imply that an absent archive is still available. Keep engine binaries, complete upstream source distributions, SDK blobs, owner data and private keys out of Git/public preview artifacts.

Final original-only artifacts are in `/workspace/scratch/trimui-development-20261022-dev4-ready`. The verified review kit is `/workspace/scratch/trimui-source-review-20261022-dev4-ready`: 50 exact source/licence observations, five explicitly selected patches and the verified original overlay, with no derived base tree or source-use claim. See [review evidence](project/evidence/source-integration-review.json). An empty acceptance session is ready at `/workspace/scratch/trimui-tg5040-acceptance-ready`; all 13 physical areas remain `not_run`.

## Remaining external work

1. **When the original TG5040 is available**, use the [device runbook](project/docs/device-test-runbook.md) on a spare/restorable setup. Capture firmware, filesystem, installed source/engine/loader/library identities and complete writers; prove original-card/internal-launcher/scene restoration before experimenting. The recorder retains selected save hashes and append-only operator observations; checksums do not authenticate a hardware claim or enable a profile.
2. Test built-in/external input, held keys, real display readiness, native menus/themes and per-game overrides. Test normal launch/quit, complete descendant ownership, state save/failed-save/Resume/load acknowledgement, battery saves, suspend/wake/audio/low battery, save-aware poweroff and clean-unmount USB. Preserve lexical launch paths and newer saves. Measure fixed scenes before claiming speed, memory or battery improvement.
3. Prove FAT/exFAT interrupted transactions, update coexistence, classic fallback and recovery. Package rollback, whole-card restore, internal startup/scene restore and vendor firmware recovery are different procedures.
4. Complete [source-use and distribution evidence](project/docs/release-rights.md). The concrete PyUI [notification draft](project/docs/author-notification-draft.txt) names both pinned recipients and a proposed public project contact. **It is unsent.** Do not use tools to contact anyone without an explicit send instruction. A fixture review object, development signature or arbitrary JSON cannot complete notification or grant redistribution rights. The exact PPSSPP/IGM recipe sources and SDK/runtime grants remain unresolved; retain per-component notices and matching source privately.
5. Review each installed port's exact engine/runtime/data rights and physical input/graphics/save behavior. San Andreas has no verified target contract; do not label it supported or fabricate performance.

Only reviewed evidence for the corresponding feature may change `hardware_qualified`, `runtime_verified`, `source_use_verified`, installed fingerprints, state formats or writer profiles. Do not merge/release/activate merely because host checks and cross-builds pass.

## Critical contracts

- Existing PyUI stages `/tmp/cmd_to_run.sh`; the principal owns foreground execution. Preserve the normal device/model/controller callbacks and initialized favorites/recents managers. Their constructors can rewrite/prune histories; use snapshots or existing instances.
- Preserve lexical `Emu/<system>/../../spruce/scripts/emu/standard_launch.sh`. Canonicalizing the invoked path breaks `$0`-based system detection. Validate containment separately.
- Per-game preset keys include the ROM extension; duplicate basenames can share overrides. Unknown presets must not silently select another engine.
- PPSSPP platform INIs under `Saves/.config/ppsspp/PSP/SYSTEM/` remain authoritative; preserve spruce copy-in/copy-back. Manually authored per-game INIs can override global keys, so common changes require the complete independently verified override inventory.
- Keep `enableButtonWatchers=false` and the existing `save_poweroff.sh`. No second input/power owner, global graphics/libc upgrade, guessed state path, fake clean shutdown or Resume from a recent entry.
- Completed-state callback, process-tree completion, stopped config writers and durable storage are separate facts. A failed later save leaves an older authenticated checkpoint's original verification timestamp. Verification time is not the save-completion time and must not be labeled as such.

Original Python/assets use MIT, Noto Sans uses OFL, PPSSPP source patches/fixtures use their separate GPL-2.0-or-later scope, RetroArch patches/fixtures use GPL-3.0-or-later, and spruce/PyUI retain their own noncommercial/notification terms. Do not describe the combined project as wholly MIT or infer a root licence for every component.
