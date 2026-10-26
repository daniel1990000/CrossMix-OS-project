# ISO-enabled execution plan — 26 October 2026

Status: planned, awaiting the user's next execution instruction. No builds, gameplay runs or implementation changes were performed when writing this plan.

This batch uses the downloaded GTA: Vice City Stories ISO to exercise our existing software with a real PSP game and fix defects that synthetic fixtures could not expose. It extends the [audit plan](trimui-audit-plan-2026-10-26.md) and [master roadmap](master-plan-2026-10-22.md). Execution starts from current main, recording its actual commit; the planning baseline was `4a97d8a253e9d572e51f17876711597d38181633`.

## Input already available

- File: `/workspace/trimui-audit/private-inputs/Grand Theft Auto - Vice City Stories (USA) (PSP) (PSN).iso`.
- Receipt: `/workspace/trimui-audit/private-inputs/download-receipt.json`.
- Size: 1,696,006,144 bytes.
- SHA-256: `e7d26d0efb2fb7a37bb73c51bddae9baffa39feab7d76e30299b4c9e5d6fc80a`.
- Local metadata: title Grand Theft Auto: Vice City Stories, DISC_ID ULUS10160, DISC_VERSION 1.03.
- Source for recovery if this ephemeral workspace disappears: https://gofile.io/d/x8y4jAzg. Redownload only if needed and require the same full digest.
- Download, size/checksum and local ISO metadata checks are complete. Gameplay is not yet tested.

Use a private test workspace outside Git. Keep the ISO immutable; create fresh disposable memstick/configuration/save directories for each arm. Recheck the input digest before and after execution. Never commit game bytes, extracted game assets, native saves/states, keys or full emulator/base distributions.

## What can now advance

| Existing roadmap area | Work enabled by this game | What completion means in this batch |
|---|---|---|
| C03/C04; U04 | Real image identity, title presentation, filtering, search, favorites and recents | Game identity and UI behavior verified using this actual input; no duplicate scanner |
| C01 | Real PPSSPP per-game INI creation/rewrites, resolution/frameskip behavior and Undo | Existing transaction manager tested against actual native-produced config and native readback |
| C05 | Real in-game saves, state availability, failed-save presentation and Continue flows | Desktop behavior and actual checkpoint evidence; no falsely available Resume |
| N01, PPSSPP portion | Real game boot, native menus/theme/controls and compatibility | Desktop native evidence only; N01's device qualification stays open |
| N02 | Real completed state writing/loading, protocol receipts and normal native INI changes | Native and composed host evidence where feasible; physical same-boot Resume stays open |
| C02; D04 | Named GTA scenes and actual observation imports | Reusable scene definitions, measured desktop reports and prepared device protocol |
| R02/R03; existing release work | Regressions found by real-game use | Reproduced fixes, strict certification and installed-package verification |

C01–C06 and U01–U04 already have host implementations. This batch tests and repairs them; it does not rebuild those foundations. GTA PSP content does not unlock PS1/C06 or the separate classic-GTA native port in P04.

## Work packages and acceptance

### G01 — Freeze the real-game test fixture

Verify the full input digest and local PARAM.SFO against the receipt. Record source revision, exact upstream locks, host architecture, renderer/audio capabilities and executable/config identities. Reuse existing inventory/library authorities; prepare a disposable mounted-card-style layout for read-only frontend inspection.

Exercise this game's information panel, full filename with spaces/parentheses, search, system filters, favorites and recents using their existing host test seams. Test same-path replacement on a disposable copy/fixture, never the original ISO.

**Done:** a sanitized fixture manifest binds shell game identity, content hash and native DISC_ID; actual UI renders/observations show consistent identity and selection. Identity changes invalidate stale actions. Record image/artwork capability separately from game launch. Missing cover art must remain a valid state.

### G02 — Establish a real desktop PPSSPP baseline

Use the pinned PPSSPP source/version and a host-compatible executable with recorded provenance. Check available display/renderer/audio paths before choosing a run mode. The retained aarch64 PowerVR candidate is not an x86 desktop executable.

Boot the ISO through the title into controllable gameplay. Exercise movement, analog input, confirm/cancel, pause/native menu and return. Create an actual in-game save, quit normally, restart and verify the saved progress. Separately exercise native save state, load state and normal exit. Repeat three independent save/quit/relaunch/load cycles with retained run identities; this is a proposed host acceptance count, not the physical casebook threshold.

**Done:** gameplay is observed and progress restoration verified, with executable/config/save identities, logs, exit status and private captures. Distinguish ordinary game savedata from emulator states. If only headless execution is possible, record exactly which serialization/boot facts were observed; visual/audio acceptance remains blocked. A process that merely starts is insufficient.

### G03 — Verify per-game controls, configuration and Undo

Let PPSSPP create its real per-game INI in the disposable environment, then inspect its actual location and native ID. The shell's performance manager must continue to consume a verified existing association; it must not invent an override from the filename.

Exercise resolution, manual frameskip, auto frameskip and Use global setting one at a time. Check native readback and applicable setting interlocks. Test Apply/Undo, unrelated native edits, owned-key conflicts, shared native configuration and a stale content/config identity. Audit native menu Confirm/Back and the matching theme where the tested build supports them; keep gameplay remaps separate.

Capture config inventories around launch, save-state, load-state and quit. Investigate the known hypothesis that benign PPSSPP writes invalidate a full-file configuration fingerprint. If reproduced, decide whether that invalidation is intended or a defect. Any proposed compatibility rule needs a threat/semantic review and tests proving relevant changes still invalidate trust; do not simply weaken hash checks.

**Done:** real native-generated INIs and readback demonstrate preservation/Undo behavior; any change has a minimal reproduction and regression. Desktop option behavior may pass while Smart Pro preset suitability remains unmeasured.

### G04 — Exercise the patched native save/load protocol

First assess a host-native SDL build using the exact pinned source and existing locked native-menu, state API and session patches. Inspect the existing build pipeline and retained sources before adding anything. Record compiler, dependency and patch hashes. Platform adaptations, if necessary, remain small, separately reviewed and explicitly distinct from the target PowerVR build.

Run the full patched emulator with this game. Exercise actual SaveSlot/Process completion and the private result protocol, then a fresh native process with a matched load request and completed-load acknowledgement. Test new save after load, a later failed save, wrong game/engine/state identity, corrupt/truncated state, wrong slot, replayed request and interrupted result publication using disposable inputs. Assert failure outcomes without treating queued operations as completion.

**Done:** actual emulator-generated state bytes and genuine save/load completion packets validate with the existing parser; failure cases preserve the last valid checkpoint correctly. Keep the original verification time when later saves fail. A selected-function compile fixture or stock PPSSPP cannot satisfy this package.

If a host build cannot execute the relevant patches without unsupported target assumptions, retain the exact build/runtime blocker and continue G02/G03/G06/G07. Do not replace a blocked native test with synthetic success.

### G05 — Connect actual host completion to launch/return and Continue

Depends on G04 for patched Resume claims. Review whether existing source staging, principal/subreaper completion, state authorities and fresh frontend processes can compose with the real host emulator. Extend an existing explicit host test seam only where necessary. Never fabricate a hardware-qualified profile or allow a host seam to select a shipped device configuration.

Exercise actual launch, process exit/descendant cleanup, return, recents and Continue status. In the host composition, test a valid state transfer into a fresh process, native load acknowledgement, failure explanations, stale identities, and later-save failure preserving earlier verification metadata. Use explicit emulated boot changes for host rejection tests and label them as such.

**Done:** a composed real-emulator host route has evidence for each boundary. If only the native protocol can run, report G04 completed and G05 blocked/partial. Device rendering/input ownership, actual sleep and device recovery remain separate.

### G06 — Create repeatable gameplay scenes and reports

Use the audit plan's title/load, on-foot, driving, action, save/return and sustained scenes. Progress the game as needed to create private test saves. Define exact starts/ends, routes, camera, duration, warmup and controllable conditions; record unavoidable traffic/combat variation. Hash scene definitions and starting save identities.

Use existing gameplay_benchmark.py and resource tools. Import only observations actually measured: native speed/FPS from identified counters, frame pacing from retained frame/video evidence, audio from reviewed recordings. Missing values stay null. Separate startup, steady state and resource measurements.

For a meaningful desktop comparison, use five independent matched pairs with the same game/scene/engine and change one setting at a time; freeze numerical budgets after baseline reconnaissance and before candidate runs. A frontend comparison requires a real equivalent baseline and candidate composition. Do not compare dummy UI timing with gameplay or call stock desktop PPSSPP a spruce device baseline. Add a 30-minute desktop stability run when rendering/audio are observable; the later device protocol still requires matched 30-minute runs per arm for demanding profiles.

**Done:** real scene definitions, private raw data and honest host reports validate through the existing importer. Desktop results are host-scoped; candidate Smart Pro presets remain untested.

### G07 — Fix findings and certify the resulting software

Prioritize data integrity and recovery, incorrect state/configuration handling, launch/return failures, then presentation defects. Each fix needs the actual reproduction, smallest relevant regression, old-code failure and fixed-code pass. Preserve legitimate behavior and existing authorities.

Run project/dev/check.sh with all five exact pinned source roots and zero skips/errors/failures. Run existing development packaging, installed smoke/rollback and source-export/deterministic rebuild verification after changes. Record exact implementation/build/source inventory identities. Leave the published dev16 packet intact. Use the established descriptor/version process if a new development artifact is warranted.

**Done:** all found release-blocking defects in the selected host scope are fixed and checked, or explicitly unresolved with retained reproduction and scope. Historical 1,107 tests are a baseline, not a fresh result or count target.

### G08 — Close the batch with evidence and roadmap updates

Write one sanitized batch report under project/docs/ and receipts under project/evidence/iso-continuation-20261026/. Include package status, actual commands, observed results, defects/fixes, identities and private evidence retrieval instructions without credentials. Preserve failed attempts and blocked cases. Independent review checks findings and claims before updating HANDOVER.md, LATEST.json, the master roadmap and continuation prompt.

**Done:** every G01–G08 item is pass, fail, blocked or excluded with evidence/reason. Any partial item lists its unmet criterion. Host results cannot increment the 14/25 original completion count or 0/13 physical count unless the original row's full criteria are independently met; this batch supplies no physical evidence.

## Dependency order and parallel ownership

G01 → G02 → G03. G04 can start once G01 fixes inputs; native runtime execution follows G02's environment checks. G05 depends on G04. G06 uses G02 and any working composition; G07 handles findings throughout and closes after the selected work; G08 closes last.

Follow AGENTS.md's parallel-work policy: assign native build/protocol, frontend/configuration, and evidence/regression review lanes with nonoverlapping file ownership. A single integration owner runs final checks and updates roadmap/handover. Shared source pins, emulator binaries and test saves must not be mutated concurrently.

## Still outside this batch

Actual TG5040 inventory/recovery, PowerVR behavior, physical input, sleep/wake, USB, battery, device performance and production qualification require the device. D02/D03/D05/D06 and device criteria of N01/N02 stay open. Distribution rights, production key custody and maintenance ownership are not changed by this ISO.

Named save history, state galleries and power-off Resume remain later product work, not automatic additions to this audit batch. No emulator/OS rewrite, source-port conversion, replacement SDK programme, public game upload or new device release is planned.

The next instruction can be: **Execute project/handover/ISO_EXECUTION_PROMPT.txt.**
