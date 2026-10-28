# TrimUI project handover — dev18

Updated 26 October 2026. Dev18 is merged into `main` through [PR #2](https://github.com/daniel1990000/CrossMix-OS-project/pull/2) at `30aa59ffa35195bcad2b2553f91c43fc32301556`. No new public release was created. The separate ISO roadmap and execution prompt from the other chat are preserved; conflict resolution changed documentation only. [The merge record](project/evidence/dev18-library-backups-20261026/merge-record.json) retains the exact merged source and verification boundaries.

Read [the dev18 report](project/docs/dev18-library-backups-2026-10-26.md), [verification](project/evidence/dev18-library-backups-20261026/verification.json), [machine-readable status](project/handover/LATEST.json), [README](project/README.md) and [master register](project/docs/master-plan-2026-10-22.md). Historical detail is retained in [the previous handover](HANDOVER-HISTORY-through-dev17.md), [previous status](project/handover/LATEST-through-dev17.json) and [previous plan](project/docs/master-plan-history-through-dev17.md); their old current/latest fields are historical.

## Delivered

- Scoped search, full system filters, sorts, paging, letter jumps and full-result Surprise across All games, Favorites, Continue and native Collections. Collection membership stays with the existing native authority.
- Persisted page/game identity, native-menu refresh, rejection of stale reads/errors/cards, and retained mutation receipts. A delayed Game A card cannot open after focus changes to Game B.
- Text choices through 175%, scaled physical-button/status hints, readable dialogs, long-title wrapping, warning-first information, Controls & help and contextual empty actions.
- Named offline backup catalog, historical receipts, detail/rename/removal, cancellable verification with progress, explicit external registration and protected new-directory CLI restore. No payload modification or live-save restore.
- Per-file conflict checks for Undo, normal-launch/optional-capture separation, fresh Resume identities, captured-source packaging, installed build identity and complete signed runtime module coverage.

## Exact verification

Clean implementation: **`399a528542da1139903c93cef3041d23acad2fca`**.

**1,209/1,209 strict host checks pass**, with zero failures, errors, skips or expected failures, against all five exact pinned source trees. The clean package contains 68 payload files and a 234-file original-source inventory with digest `bed2e770420510d3cae0cdf86f13714e65a8c27c7cc65c3d4f03d4fd9cb2082a`. Installed preview, source/payload/signature checks, fixture activation/rollback and byte-identical no-Git rebuilding of both ZIPs pass. Generated development private keys were deleted.

[Review records](project/evidence/dev18-library-backups-20261026/review.json) identify independent agent lanes, reproduced issues and fixes. Actual SDL evidence covers a 144-render matrix, 18 end-to-end workflow captures and a 70-entry synthetic backup catalog with unchanged source/payload bytes. Twenty-six representative PNGs are retained. These are host fixtures, not hardware trials.

[CI readback](project/evidence/dev18-library-backups-20261026/ci-readback.json) records its exact PR merge checkout, artifact digest, signed inventory and matching source bytes. The PR describes the latest metadata-head CI result. CI merges in the separate main-branch document, so its source inventory and ZIP identity differ from the local clean implementation package. Later evidence/handover commits also have their own identity; never relabel older package hashes as a newer head.

## Published preview and ownership

[Dev16 remains the public computer preview](https://github.com/daniel1990000/CrossMix-OS-project/releases/tag/smartpro-host-0.1.0-dev16), fixed at `99336f6525efbd1b790a15c7de54acca3eacd1ec` with 11 assets. Dev18 creates no new public release and changes no published asset. Original-only artifacts exclude games, saves, private keys and native emulator/SDK distributions. Automatic repository archives retain inherited mixed material and are outside the attached original-only scope.

Keep PPSSPP, the current PS1 route, native input/display/process ownership and existing save/memory-card locations. No device/profile gate is enabled and no emulator binary or upstream patch is selected. Private source-use authorization remains scoped to [the owner-confirmed record](project/evidence/completion-20261023/owner-permission.json); it does not settle public native-distribution terms. Do not send author messages or request private keys. [Historical native custody](project/evidence/artifact-custody/native-retention.json) is unchanged; dev18 does not claim a fresh native build or retrieval.

## Next work and limits

The original register remains **14/25 complete; physical acceptance remains 0/13**. With the device, begin with inventory and a real recovery rehearsal, then follow [the existing casebook](project/docs/device-test-runbook.md): native menu return, input/display restoration, interrupted saves, storage faults, launch/quit, sleep/wake and actual Resume on exact installed profiles. Check real I/O latency during backup verification. Host tests do not prove device performance, battery life, recovery or Resume reliability.

Keep the baseline comparison protocol: unchanged spruce and current emulator/settings, this frontend with those same settings, then individual changes. Use five matched runs per named scene and 30-minute demanding-profile runs before recommended presets. Production signing custody, public native-distribution decisions and maintenance ownership remain open.

State galleries, automatic named state history and power-off Resume remain deferred. The delivered catalog is the useful offline portion: it names and verifies already-retained recovery payloads. Saved filter presets and frontend collection editing remain follow-ups.

The owner moved **Vice City emulation/testing to another chat**. Continue this development/review/delivery track independently. Do not download or test that game again here, or infer gameplay results from the other document without its specific evidence.

## Separate ISO-enabled continuation

Main also contains [the ISO-enabled roadmap](project/docs/iso-enabled-roadmap-2026-10-26.md) and [execution prompt](project/handover/ISO_EXECUTION_PROMPT.txt), prepared in the other chat. That plan records the supplied image's download/metadata verification and G01–G08 host game-validation work as awaiting execution instruction. Its planning step made no gameplay, runtime, build or certification change. The plan and prompt are preserved unchanged; their dev17 baseline predates dev18. Use this handover for current implementation identity, and the separate chat for game-specific execution. No game result is inferred here.
