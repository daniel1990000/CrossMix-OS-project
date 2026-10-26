# TrimUI master plan — current register

Updated 26 October 2026. Active development is the dev18 library/backup batch on `build/dev18-library-backups`, based on main `9dfa857`. The [dev18 report](dev18-library-backups-2026-10-26.md), [current handover](../../HANDOVER.md) and [machine-readable status](../handover/LATEST.json) identify exact verification and delivery. The [unchanged historical plan](master-plan-history-through-dev17.md) retains prior research, decisions and dated completion records; its old branch/publication instructions are historical.

The original register remains **14/25 complete and 0/13 physical areas run**. New host features do not complete the pending device, distribution or operational rows. Published dev16 stays fixed at `99336f6`; no native binary or upstream patch is selected by dev18.

## Separate planned ISO-enabled continuation

The other chat prepared [G01–G08 real-game host validation](iso-enabled-roadmap-2026-10-26.md) and [its execution prompt](../handover/ISO_EXECUTION_PROMPT.txt). Its planning record verifies the supplied image's download and metadata but reports no gameplay, runtime change or certification rerun. Keep the plan's dependencies and acceptance criteria; its dev17 baseline is historical relative to this dev18 batch. This separate work targets C01–C05, D04 and host portions of N01/N02, without PS1, native-port or physical qualification. The register remains 14/25 and physical areas 0/13.

## Dev18 host batch

| Order | Deliverable | Acceptance |
|---|---|---|
| 1 | Save conflict protection and consistent normal-launch/Resume identities | Late edits survive Undo; partial retry keeps journals; optional capture incompatibility can skip capture only for valid normal Launch; explicit Resume always fails closed. |
| 2 | One captured source snapshot for packaging | Descriptor/lock/payload/source ZIP agree; hidden changes and replacement refs cannot attribute altered bytes to a clean commit; exported-source rebuilding remains deterministic. |
| 3 | Navigation and response ownership | Old reads/errors cannot reopen screens; completed writes keep receipts; selection survives later pages, reorder, refresh and native-menu return. |
| 4 | Scoped discovery and native Collections | All systems/search/sort/page/jump/full-result Surprise; existing collection membership authority, stable identities and read-only card inspection preserved. |
| 5 | Accessible information and help | 175% selectable; essential hints scale; warnings and long details remain reachable; actual default/high-contrast and embedded renders inspected. |
| 6 | Named offline backup history | Reachable host catalog, immutable payload identity, generation-checked labels, bounded cancellable verification, no live restore or native state ownership. |
| 7 | Review, certification and handover | Independent consequential-change reviews, strict five-source checks, installed smoke/rollback, no-Git rebuild, GitHub CI and downloaded-artifact verification. |

Named saved filters, additional palettes and richer metadata are follow-ups. Native multi-slot galleries, automatic save-history capture, live restore and cold-boot Resume require additional associations, writer evidence and qualification. Initial retained-capability authentication still performs full checks; reduced repeated history hashing is not proof of device latency improvement.

## 4. Prioritized execution register

**R01–R04, U01–U04, D01, D04 and P01–P03 are complete as host engineering; R05 is complete for owner-confirmed private noncommercial source use. The other 11 rows remain open.** P0 means a prerequisite for the named activity, not that every optional feature blocks the core release. Owners: **engineering** = assistant/developer work; **operator** = owner with physical device; **maintainer** = release owner/source-use correspondence. Effort bands are rough engineering sizing: S up to a focused day, M several focused days, L multiple iterations. They exclude external response time and hardware debugging; they are not delivery dates.

| ID | Priority / owner / size | Deliverable and completion criteria | Depends on |
|---|---|---|---|
| R01 | P0 / engineering / S | Disable or isolate inherited release automation. Smart Pro tags cannot invoke CrossMix packaging; reviewed allowlist retains notices. Inspect events without creating a release tag. | None |
| R02 | P0 / engineering / M | Certification runner rejects missing/mismatched sources and unexpected skips; records source IDs and actual counts. Add source-lock CI trigger. Do not hardcode 561 forever. | None |
| R03 | P0 / engineering / M | Current release descriptor selects frontend commit, base/PyUI, extension set, binary hashes, evidence and release ID. CLI/docs agree; historical evidence untouched. | None |
| R04 | P0 before native use / engineering + maintainer / M–L | Recover/hash-check or rebuild binaries with matching source/build archives; demonstrate retrieval from retained storage. New digest gets a new record. Retain original-only preview before expiry. | R03 |
| R05 | P0 before derivative assembly / maintainer / S + external action | Complete prepared noncommercial PyUI notice and retain actual delivery/scope evidence privately. Owner must explicitly instruct sending or supply evidence. | Exact scope |
| R06 | P0 before binary distribution / engineering + maintainer / L | Component ledger distinguishes tools, linked code, bundled libraries, device dependencies and assets; resolve exact recipe/IGM/SDK terms and corresponding source/notices. | R03, R04 |
| U01 | P1 / engineering / M | Test PNG/JPEG/BMP/WEBP/QOI capability across host and embedded paths; choose bounded decoding/normalization, safe malformed/oversize handling and consistent placeholders. | None |
| U02 | P1 / engineering / M | Invalidate image and negative caches when artwork changes at the same path; bound memory and refresh without losing selection. | U01 |
| U03 | P1 / engineering / M | Keyboard scales with accessibility settings, fits 1280×720, offers accurate controller help, punctuation/space/delete/cancel and predictable focus. Define supported text entry/localization explicitly. | None |
| U04 | P1 / engineering / M | Large-library fixtures test startup/search/navigation, long/non-Latin names, duplicate basenames and empty/corrupt entries. Establish budgets against baseline; preserve stable selection. | Measurement design |
| D01 | P0 before device activation / engineering / L | Trusted private experimental harness/manual procedure identifies exact candidate, checks ownership/runtime, supports bounded exit and recovery, and writes durable evidence. No editable flag or card JSON can grant production qualification. | R03, R05; R04 if native candidates used |
| D02 | P0 before device activation / engineering + operator / M | Verified card, save and necessary internal-file backups; separate overlay/card/internal recovery instructions; offline classic fallback and restore rehearsal on expendable media. | Inventory |
| D03 | P0 before device activation / engineering + operator / M | Record actual TG5040/firmware/filesystem/runtime; verify kernel APIs, /proc identity and required probe tooling including readelf. Static ELF inspection is labelled separately from live evidence. | D02 |
| D04 | P1 / engineering / M–L | Measurement tooling captures frame timing where possible, CPU/tree memory and reproducible scenes; physical video/power methods separately specified. Unmeasured metrics remain unavailable. | None |
| D05 | P1 / engineering + operator / L | Execute 13-area casebook in stages; retain raw logs, exact hashes, expected/actual result and recovery outcome. | R02, U01–U04, D01–D04 |
| D06 | P1 / engineering + maintainer / M | Independently review device evidence; create narrowly bound production runtime configuration only for supported candidate. No automatic promotion from report or signature. | D05, applicable R06 |
| N01 | P1 optional / engineering + operator / L | Qualify PPSSPP then RetroArch candidate individually: identity, native controls/theme, launch/return, save compatibility, failure recovery and performance. | R04–R06, successful core pilot |
| N02 | P1 optional / engineering + operator / L | Qualify same-boot Resume with real save/load proof, stale/replay rejection, profile changes and benign native INI writes; reboot falls back to Launch/native saves. | N01, D01 |
| P01 | P0 before port qualification / engineering / M | Inventory actual PortMaster platform package, spruce helpers, selected engine, Game.so/libraries and managed runtimes; cover installed-generation/self-update transitions. | None |
| P02 | P0 for Celeste only / engineering / M | Correct pinned preparation status handling; inject failed repack/mount/low-space cases, require nonzero result, no false completion marker and retry/cleanup. | P01 |
| P03 | P1 optional / engineering / M | Stage-aware data/runtime/preparation readiness, per-port save registry and uninstall/restore contract; Render96 generated output and Celeste managed runtime recognized. | P01 |
| P04 | P2 optional / operator + engineering / L | Qualify Sonic Mania first, then one classic GTA if owned and appropriate; publish exact per-title results. | P01, P03, core pilot, applicable rights |
| O01 | P1 before public device release / maintainer + engineering / M | Operational trust root/key custody, rotation/revocation/recovery exercise using existing signing system; no private keys in Git. | R03 |
| O02 | P1 / engineering + maintainer / M | Release bundle has stable download, hashes, source/notices, exact support matrix, install/update/restore, known issues, support export and screenshots labelled by provenance. | R02–R06 as applicable, D06, O01 |
| O03 | P2 / engineering + maintainer / M | Maintenance matrix and clean rebuild report; scoped upstream-drift reviews, bug triage and requalification rules. | R03, first pilot |

**R04 private custody, scoped R05 source use and D01 software engineering are complete.** D01 now connects its restrictions and bounded return to the actual embedded/principal/resident boundaries, with independent review and real host subprocess composition. D02 has actual backup-payload/expendable-restore tooling; D03 has read-only inventory/kernel tooling. Physical recovery and target readiness remain unrun. R06 now includes full retained-source inspection and exact native link/notice provenance; its remaining public distribution scope stays open. No host result promotes a device runtime.

## 6. Device programme and measurement

Preserve the existing minimum **10 cold boots, 20 normal/PSP appearance switches, 20 launch/quit cycles across applicable runtimes, and 10 sleep/wake cycles**. The runbook must identify which UI/emulator contexts each cycle covers; aggregate counts alone must not conceal an untested context. For optional omitted ports/engines, publish explicit scope exclusions rather than marking their cases passed.

Test sequence:

1. Inventory and restore rehearsal, including original bytes/permissions for relevant internal launcher/FN changes. A hash list is not a backup.
2. Classic pinned spruce baseline with unchanged installed engines, fixed brightness/radios/clocks and representative content.
3. PSP frontend with those same engines: navigation, appearance, launch/return, cancel/failure, settings and sleep.
4. Faults using disposable copies: malformed configs/assets, missing core/launcher, full/read-only storage, interrupted package transaction, persistent processes, USB export and recovery.
5. Optional native engines, then individual ports, each with exact independent identity/settings/save evidence.
6. Sustained performance and endurance; retain raw observations and limits.
7. Independent review and a deliberate production qualification decision.

The 13 areas remain: **restore; boot; input; library; launch/return; save/Resume; native controls; appearance; settings; power/sleep; USB; storage/updates; ports**.

Required observations include both sticks, pad discovery with USB audio/controller present at boot and hotplugged, restored display/input/audio ownership after exit, real save readback, classic fallback, no stranded processes/mounts, radio/sleep behavior and shared writers during shutdown/USB export. Do not duplicate upstream power or input owners.

Kernel/API probes cover child subreaper/wait behavior, memfd sealing or reviewed fallback, peer credentials and /proc process identity. Resolve trusted Python/readelf availability before the session. Device evidence must survive reboot and card export.

**Measurement policy:** baseline first, then choose explicit regression budgets before candidate comparison. Record median/p95/worst startup and navigation timing, frame intervals at the actual rendering boundary where available, CPU including children, memory growth and peak RSS/PSS where available. Summed RSS may double-count shared pages. Internal frame timestamps do not establish panel input latency: use an appropriate external video method for that claim. Use validated energy measurement for battery claims; short battery-percentage snapshots are insufficient. Record temperature only where measurable. No overclock during baseline qualification.

An upstream battery-consumption issue is a test lead, not a benchmark. Current `benchmark.py` supplies useful resource sampling but does not measure smoothness, audio faults, latency or battery energy.

References: [device runbook](https://github.com/daniel1990000/CrossMix-OS-project/blob/a7a735726b8635fb606e38e079d11ae8f0cdaa41/project/docs/device-test-runbook.md), [recovery](https://github.com/daniel1990000/CrossMix-OS-project/blob/a7a735726b8635fb606e38e079d11ae8f0cdaa41/project/docs/recovery.md), [installed-runtime evidence](https://github.com/daniel1990000/CrossMix-OS-project/blob/a7a735726b8635fb606e38e079d11ae8f0cdaa41/project/docs/installed-runtime-evidence.md), [manufacturer firmware](https://github.com/trimui/firmware_smartpro/releases/tag/v1.1.1), [SmartPro configuration](https://github.com/spruceUI/spruceOS/blob/d45ff8dfe5756147522b04ae5863d17a90e88b54/spruce/scripts/platform/SmartPro.cfg).
