# TrimUI audit plan using Vice City Stories

Prepared 26 October 2026. This is an execution plan, not a completed software or device audit.

The target is the original TrimUI Smart Pro TG5040, using the project's pinned spruceOS v4.5.4/PyUI base and existing PPSSPP route. The repository examined was main at `9dfa857fec43c165b2b8836406012f1b38cfed87`. Current development is dev17; the published computer preview is dev16. Actual device firmware, filesystem and installed engine remain to be observed.

The latest [dev17 receipt](../evidence/host-fixes-20261024/verification.json) records 1,107 passing strict host tests at implementation `de9ecf099a305f2623086c9d78b808fe4d14197c`, with zero skips/errors/failures. These tests were not rerun while preparing this plan. The [physical casebook](../evidence/device-acceptance-plan.json) still records 0/13 areas run. Neither this plan nor the supplied game changes those results.

## Supplied test material

[The supplied GoFile link](https://gofile.io/d/x8y4jAzg) exposes one file:

| Field | Observed value |
|---|---|
| Filename | Grand Theft Auto - Vice City Stories (USA) (PSP) (PSN).iso |
| Server-reported and HTTP range total size | 1,696,006,144 bytes |
| ISO structure | ISO9660 primary descriptor, PSP_GAME and UMD_DATA.BIN directory entries |
| PARAM.SFO title | Grand Theft Auto: Vice City Stories |
| PARAM.SFO DISC_ID | ULUS10160 |
| PARAM.SFO DISC_VERSION | 1.03 |
| PARAM.SFO PSP_SYSTEM_VER | 2.81 |
| PARAM.SFO CATEGORY | UG |
| PARAM.SFO SHA-256 | 2bb27a13cc037f4c640516b82ff9ce1d2fe5fbe12204339a5d230ca9545ae835 |
| Full image SHA-256 | e7d26d0efb2fb7a37bb73c51bddae9baffa39feab7d76e30299b4c9e5d6fc80a |

The complete ISO was downloaded on 26 October 2026 at 17:32 UTC into private workspace storage. Its 1,696,006,144-byte size and MD5 (5b6b0ed024eaea63511a387efd6b9595) match the GoFile listing; SHA-256 was calculated from the full downloaded file. Local ISO descriptor/directory/PARAM.SFO inspection confirms the values above and a matching declared volume size. These checks establish download consistency, not independent authenticity or gameplay correctness. The image has not been executed. The filename's PSN label is not independent provenance evidence. PSP_SYSTEM_VER is game metadata, not the TrimUI firmware version.

The full ISO and download receipt are retained under `/workspace/trimui-audit/private-inputs/`. Download, size/hash verification and local structure/metadata inspection are complete. Freeze the full SHA-256 above in every run identity. Preserve the original image read-only and use separate test saves. Keep game bytes, saves, screenshots containing private data and session credentials outside GitHub. Store sanitized manifests and test summaries in the repository.

Vice City Stories supplies a realistic PSP workload for launch, streaming, controls, saves and sustained gameplay. It cannot qualify PS1, ports or every PSP game. Keep existing redistributable smoke fixtures and add separate representative titles for each claimed runtime.

## Execution order and deliverables

| Stage | Execution environment | Deliverable and exit condition |
|---|---|---|
| A. Freeze inputs | Host/offline | Complete game digest; exact project, five upstream pins, engine/config hashes; evidence directory and test scope |
| B. Audit software | Host/offline | Strict certification, independent code review, fault-injection findings and package verification |
| C. Exercise native desktop runtime | Host with real PPSSPP | Real game boot/save/load/quit observations, explicitly labeled desktop; graphics/audio only if actually observed |
| D. Establish recovery and device identity | Spare card and actual TG5040 | Verified backups, independent readback, physical restore rehearsal and actual installed-runtime inventory |
| E. Inspect private UI | Reviewed view-only device route | Browse/render/input/return observations with existing process/display/input owners preserved |
| F. Qualify full lifecycle | Separately reviewed device execution route | All applicable casebook areas and cycle counts, including game launches and writes |
| G. Measure and review | Actual TG5040 | Matched scene reports, sustained tests, independent review and a scoped go/no-go decision |

A failed prerequisite blocks its dependent stage; independent host work continues. Record blocked and excluded cases explicitly. Do not convert them to passes.

## B. Host audit: inspect failure behavior, then prove fixes

Recreate the exact five upstream checkouts from the existing locks. Run the established certification entry point from a clean checkout:

```sh
PYTHON=/path/to/venv/bin/python \
SPRUCE_SOURCE_ROOT=/path/to/pinned-spruce \
PPSSPP_SOURCE_ROOT=/path/to/pinned-ppsspp \
SPRUCE_RA_SOURCE_ROOT=/path/to/pinned-ra-recipe \
PORTS_SOURCE_ROOT=/path/to/pinned-ports \
PORTMASTER_SOURCE_ROOT=/path/to/pinned-portmaster \
sh project/dev/check.sh --report /private/audit/certification.json

python3 project/packaging/dev_release.py \
  --output /private/audit/package --include-source \
  --smoke-python /path/to/venv/bin/python
```

Paths are examples. Resolve exact commits from the current locks; do not substitute latest upstream versions. Zero skipped tests is required. Preserve the full test list/log and changed test count; 1,107 is a historical reference, not a target that excuses deleted checks.

Review the actual implementation alongside its tests. Extend existing suites only for uncovered behavior or reproduced defects:

| Priority and area | Audit cases | Existing test locations |
|---|---|---|
| P0: saves and recovery | Disk full, short/failed copy, permission failure, interrupted staging, failed fsync/rename, conflicting/newer saves; no unrelated data changes | test_recovery_payload.py, test_recovery_preflight.py, test_state_evidence.py |
| P0: launch/process ownership | Quoting and shell metacharacters, descendant cleanup, stale PID/boot, duplicate/replayed commands, timeout, missing resident, failed return; no second input/display owner | test_principal_integration.py, test_principal_deadlines.py, test_pyui_lifecycle.py, test_runtime.py |
| P0: settings/Resume | Transaction interruption at each write boundary, Undo conflict, wrong game/engine/state, incomplete write, native load rejection, stale authentication, reboot fallback | test_settings_transactions.py, test_common_emulator_transaction.py, test_ppsspp_state_wrapper.py; PPSSPP source tests |
| P1: UI and library | Rapid Games/Favorites/filter switches with delayed responses; repeated inputs; Unicode/long/duplicate names; broken artwork, empty libraries, refresh/focus and bounded cache/resource growth | test_ui_artwork_async.py, test_ui_model.py, test_large_library.py, test_artwork_formats.py |
| P1: paths and external inputs | Symlink swaps, traversal, malformed metadata, changed PS1 disc references, TLS/download failure, extractor error and USB staging failure | test_game_information.py, test_upstream_reliability.py, test_usb_storage_patch.py |
| P1: evidence and packages | Forged/stale/missing observations; reused raw files; overwritten inputs; hidden source edits/deletions; missing transitive payload; tampered signature/source inventory; rollback | test_gameplay_benchmark.py, test_qualification_review.py, test_certification.py, test_release_integration.py, test_package_overlay.py |

Use disposable fixtures for destructive failures. Existing tests already cover many cases; map coverage before adding more. Reproduce each finding on the affected revision, write the smallest meaningful regression, fix it, and confirm the regression fails on old code and passes on the fix. Review results independently. Run the full certification and installed package smoke after fixes, then verify deterministic/source-export rebuilds using the existing release procedure.

Audit reports must distinguish compiled source fixtures, a complete native cross-build, stock desktop PPSSPP, patched desktop/native integration and physical-device runs. One cannot stand in for another. Check packaged bytes and the installed payload, not only the development checkout.

## C. Desktop gameplay checks

Use the fully hashed supplied ISO, a separately identified PPSSPP executable and a disposable configuration/save directory. Record whether that binary contains our state callback patches. Exercise actual title boot, new-game/load flow, native controls, in-game save, normal quit, restart and native save readback. Test save states separately.

Capture actual screenshots/video, emulator logs and exit status. A log saying serialization completed proves neither correct rendered gameplay nor our authenticated Resume integration. A headless/software-renderer run remains a host functional test and supplies no Smart Pro speed or audio result. Current desktop smoke evidence uses another title; GTA adds a new workload, not retroactive coverage.

## D–F. Device recovery and qualification

Follow [recovery payload](recovery-payload.md), [recovery preflight](device-recovery-preflight.md), [device probe](device-probe.md) and [installed runtime evidence](installed-runtime-evidence.md). Back up card files, saves and relevant internal files; retrieve and verify independent retained copies. Rehearse restoration on expendable media, including actual boot and save readback. Observe the real device model, firmware, filesystem, kernel boot ID, principal identity, interpreter, loaded libraries, engine and configuration hashes. Do not use cloud-host observations as device evidence.

The current [private experimental runtime](experimental-runtime.md) is implemented but view-only. It refuses game/tool launches, favorite/settings writes, refresh, Resume, USB and power transitions. It requires actual recovery/runtime reviews and verified startup. Use it for browsing, presentation, input and bounded return only.

Before full launch/save/sleep testing, document and independently review the specific private integration route that permits those operations through existing spruce authorities. If no such reviewed route exists, that is a concrete implementation prerequisite. Do not bypass it by turning on shipped production gates. Native candidate and authenticated Resume work require their own exact source/build/runtime scope.

Reuse [device_acceptance.py and qualification_review.py](qualification-review.md), with an independently prepared expected profile and private evidence root. Retain before/after snapshots and a predeclared save policy. Minimum physical policy:

- At least 10 cold boots total, covering classic and PSP, with distinct boot UUIDs.
- 10 classic-to-PSP and 10 PSP-to-classic appearance switches.
- 20 launch/quit cycles for each selected runtime.
- 10 sleep/wake cycles each for classic, PSP and every selected runtime.
- All applicable areas: restore, boot, input, library, launch/return, save/Resume, native controls, appearance, settings, power/sleep, USB, storage/updates and ports.

For GTA, verify every control and analog range, pause/native menu return, in-game save persistence after normal exit/relaunch, audio after sleep, and recovery after a failed launch. Test project Resume only with the qualifying patched engine and completed-write/load-acknowledgement evidence. Reject wrong state/game/engine identity and stale/replayed sessions. Treat power-off Resume as a later feature; test the documented reboot fallback rather than claiming unsupported behavior.

Include SD full/read-only, malformed settings, interrupted update, USB staging failure, missing game and missing engine cases. Begin fault injection on fixtures and disposable media. Stop an affected device sequence on unexpected save changes, ownership loss, unrecoverable hangs, failed restore or unplanned internal writes. Retain the failure and evidence before attempting a reviewed recovery.

## G. Vice City Stories scene protocol

These are proposed scenes. During baseline reconnaissance, fix exact start saves, route, duration, camera, time/weather where controllable, warmup and end conditions. Hash each scene definition. Do not call variable traffic or combat deterministic; record variability and repeat runs.

| Scene ID | Proposed task | What it stresses |
|---|---|---|
| vcs-title-load | Cold game launch through title to a fixed save; measure launch-to-controllable separately | Loading, first-use resources, frontend handoff |
| vcs-on-foot | Fixed 120-second on-foot route and camera sweep from the same save | Input, geometry, frame pacing |
| vcs-driving | Fixed 120-second driving route with streaming transitions | Streaming, stutter, audio continuity |
| vcs-action | Fixed 120-second mission/combat segment, once a reproducible setup is available | Busy gameplay and variability |
| vcs-save-return | Native in-game save, exit, relaunch, load and verify expected progress | Save integrity and process return |
| vcs-sustained | Repeat the demanding route for 30 minutes in each comparison arm | Sustained speed, audio and thermal/resource behavior |

First compare unchanged spruce/current PPSSPP/settings against our frontend with the same PPSSPP binary and effective settings. Use five independent matched pairs per selected performance scene. Counterbalance arm order and restore matched starting conditions. Keep loading latency separate from steady-state gameplay.

Then test one native setting at a time. Compare engine changes separately. Record resolution, explicit and automatic frameskip, graphics backend, clocks, brightness, radios, charging and initial thermal/battery conditions. Keep configuration/save directories isolated so baseline runs cannot silently change candidate inputs.

Use the existing [gameplay reporting tools](gameplay-performance.md), not a second benchmark framework:

```sh
PYTHONPATH=project python project/tools/gameplay_benchmark.py record \
  --manifest /private/run-1.json \
  --observations /private/run-1-observations.json \
  --output /private/run-1-report.json

PYTHONPATH=project python project/tools/gameplay_benchmark.py compare \
  --baseline /private/b1.json /private/b2.json /private/b3.json /private/b4.json /private/b5.json \
  --candidate /private/c1.json /private/c2.json /private/c3.json /private/c4.json /private/c5.json \
  --metric native_speed_percent --output /private/comparison.json
```

For demanding profiles, add the existing sustained baseline/candidate inputs covering 30 minutes per arm. Every run needs distinct retained raw observations; duplicated files do not create independent runs.

Report intended speed, native speed, native FPS, frame-time median/p95/p99/worst where supported by raw measurements, audio faults, visible defects, resource use and image-quality tradeoffs. The current comparison schema may accept only a subset; retain additional metrics as supplementary raw analysis rather than inventing CLI metric names. Never assume a 60 FPS target. Physical latency needs button-and-screen video with stated frame uncertainty. Battery claims require validated energy measurements; percentage changes or USB charging draw alone are insufficient.

Choose numerical performance budgets after baseline reconnaissance and freeze them before candidate measurements. Report individual paired differences and spread. If noise exceeds the chosen margin, mark the result inconclusive and collect more data. No candidate preset becomes recommended just because it boots or produces higher FPS.

## Evidence, defect triage and completion

Maintain one traceability row per claim: requirement → implementation/source identity → test ID → execution environment → raw evidence → result → defect/retest → reviewer. Use statuses planned, blocked, pass, fail and excluded with reasons. Keep the existing append-only attempt chains; fixes and retests never erase earlier failures.

Each run must identify the project/package, game SHA-256, engine, effective settings, scene, actual device/environment, boot/process, timestamps and applicable before/after saves. Store raw observations privately, verify retained copies and publish only sanitized summaries. A metadata hash is consistency evidence, not proof that a physical test occurred.

P0 findings include save loss/corruption, broken recovery, unsafe writes and process/input ownership failures. P1 includes crashes, wrong launch/configuration and repeatable gameplay/audio regressions. P2 covers nonblocking presentation/usability defects. Stop release qualification for unresolved P0/P1 findings in the selected scope; give lower-priority findings an owner and explicit disposition.

Completion requires: full strict host certification; installed artifact/source/signature and rollback checks; scoped native evidence; all applicable physical cases and minimum cycles; matched gameplay and sustained results; independent review of retained evidence; and separate release custody/distribution decisions where applicable. The review tool generates a proposal and does not activate profiles.

The game download/hash and local metadata checks are complete. Immediate next work is to rerun dev17 certification with the five pins, map existing tests to the audit matrix, reproduce any uncovered defects, and run real desktop GTA checks. Device stages remain blocked until actual TG5040 access and recovery evidence exist. This plan adds no device pass, performance claim or production activation.
