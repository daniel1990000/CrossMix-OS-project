# Dev18: library discovery and offline backup history

Dev18 improves everyday browsing and makes retained backups visible without changing emulator save ownership. The batch also fixes reproduced Undo, asynchronous-view and release-identity defects. Dev16 remains the published computer preview with its original assets and source identity.

Exact certification, build, review and CI receipts are recorded in [the dev18 evidence directory](../evidence/dev18-library-backups-20261026/). A receipt applies to its recorded commit and inventory. Later documentation commits do not inherit that package identity. The [current handover](../../HANDOVER.md) identifies the latest saved development checkpoint.

## Independent starting review

The review began from `main` at `9dfa857fec43c165b2b8836406012f1b38cfed87`, including the dev17 implementation at `de9ecf099a305f2623086c9d78b808fe4d14197c`. A fresh baseline certification reproduced all 1,107 passing checks against the five pinned sources, with no skips. The existing development package passed installed smoke/rollback and both ZIPs reproduced from a source export without Git.

Six parallel lanes examined everyday use, actual SDL renders, save/recovery reliability, native architecture, delivery and offline history. Findings were checked against code, source contracts and focused reproductions. Passing historical checks did not cover every integration boundary: review found partial-Undo conflicts, optional-capture failures blocking normal launches, incomplete runtime module coverage, stale view/receipt handling, and page/focus limitations. Device-only performance, hardware recovery and Resume qualification were not inferred from those host findings.

## Behavior delivered

| Area | User behavior and boundaries |
|---|---|
| Library discovery | Search, system filter, sort, paging and letter jump share one scope: All games, Favorites, Continue or one collection. System selection covers the available inventory. Continue retains native ordering by default. Surprise samples available games from the complete scoped result; Pick another avoids the previous result when alternatives exist. Selection opens a card before any launch. |
| Native collections | Existing collections are browsable through the initialized native authority or read-only mounted-card data. Creating collections and editing membership remain native operations. Returning from native menus refreshes cached metadata and artwork. |
| Navigation and asynchronous work | Navigation schema 2 persists page, game identity and scope; schema 1 remains readable. Refresh anchors the selected game after reordering, or clamps a removed selection. Old reads, errors and dialogs cannot replace a newer view. Mutation results remain available in Recent actions after navigation. |
| Readability and help | Text choices include 175%. Footer, status and physical-button hints scale; dialogs are opaque, with independent text/action overflow cues. Long selected titles wrap. Game warnings precede optional information; detailed information remains separately reachable. Controls & help and contextual empty-result actions explain the available routes. |
| Offline backup history | Names, notes and check receipts refer to existing verified recovery payloads. The UI lists, inspects, renames, removes catalog entries and starts/cancels a fresh byte check. Removing an entry preserves its payload. The external CLI registers payloads and restores only to a new directory outside protected roots. |
| Save and launch reliability | Undo checks each destination against its recorded before/after bytes, preserves later writes/deletions and supports partial retries. Optional state capture may be skipped when ineligible without blocking a valid normal launch. Explicit Resume still fails closed on missing or stale game/profile/state evidence. |
| Source and installed identity | Packaging captures original source bytes, descriptor and lock together, then builds from that snapshot. Git replacement objects cannot alter the recorded commit. Installed build information derives from the selected descriptor and metadata. The runtime requirement inventory covers every shipped Python module. |

Bulk Continue listing labels an authenticated recorded checkpoint as requiring verification. Selecting it performs the full check, and executing Resume validates again. Initial capability-store loading still authenticates retained evidence; this batch does not claim that all startup hashing has disappeared.

## Interfaces and data

`library.query` accepts `source`, `collection_id`, `system_id`, `search`, `sort`, `available_only`, `offset`, `limit`, `jump` and `focus_game_id`. `library.collections` exposes stable collection identity, label and count. `library.random` accepts the same result scope and `exclude_game_id`. Invalid combinations fail before native actions; letter jumps use ascending title order. The existing unextended query contract remains supported.

Navigation schema 2 is application UI state outside inspected cards. It contains no emulator state or save data. Refresh after native menus preserves identity while changing the view generation, so late results from the old view are discarded.

Backup catalog schema 1 is bounded to 1 MiB and 1,000 entries. UUID entry IDs, labels, notes, normalized payload paths, manifest identity, generation and separately named capture/registration/check timestamps live outside payloads. Labels are bounded Unicode text; mutation requests require the expected generation. Catalog edits use the existing private journal/transaction mechanisms and explicit recovery. Browsing does not create a catalog.

The adapter exposes `backup.history`, `backup.detail`, `backup.rename`, `backup.remove`, `backup.verify`, `backup.job` and `backup.cancel`. UI requests use opaque entry/job IDs, never caller-supplied paths. Verification runs as one bounded worker with progress and cancellation; superseded jobs are cancelled, shutdown joins the worker, and native ownership transfer waits for quiescence. A blocked worker refuses transfer instead of being abandoned. Failed, cancelled or superseded verification cannot produce a successful receipt. No UI restore or live-save discovery endpoint exists.

See [the README](../README.md#named-offline-backup-history) for registration and preview commands. The catalog supports named retained saves when those saves already exist in a recovery payload; it is not an emulator save-state gallery or an automatic version history.

## Review and validation

Authors and independent reviewers had separate ownership. Save/Undo changes were reviewed by native and delivery lanes; backup catalog changes by the reliability lane; native discovery/identity changes by reliability; UI flows by the visual lane; root dispatcher/lifecycle and signed module integration by delivery. Review corrections included containment across all registered payloads, terminal job errors, retry after a paused worker, native identity collisions, dropped asynchronous request bookkeeping and signed tools-module scope.

The complete certification includes the existing foundations and compiled pinned-source probes, not only new unit tests. Installed-package checks cover build identity, scoped discovery beyond the first page, read-only collections, backup CLI/history/check/cancellation, help screens and rollback. Source-export rebuild checks compare both ZIPs byte for byte. Render evidence uses actual SDL/Pillow and SDL_ttf paths, six text sizes, both Confirm positions and both contrast modes; representative captures and the capture script are retained with source hashes.

The first candidate run correctly rejected three assembly errors from the newly complete module inventory and one Games-root ordering regression. These failures are recorded separately from the final certification. No skipped or expected-failure suite counts as a pass.

## Remaining work

All device/profile qualification gates remain disabled. The original master register remains 14/25 complete and physical acceptance remains 0/13. This batch adds host functionality without closing physical or operational criteria.

Actual Smart Pro controller feel, native-menu return, I/O latency during large backup checks, sleep/power behavior, save interruption, recovery, Resume and gameplay require the device and the existing casebook. Matched game-scene measurements, battery evidence, recommended presets, production signing custody and public native-distribution decisions remain open. Vice City emulation/testing is being handled separately at the owner's request; this batch has no dependency on a game image and makes no real-game claim.

Native save-state thumbnails, automatic named state history and power-off Resume remain deferred until capture provenance, storage lifecycle and device behavior are established. Saved filter presets and collection editing in this frontend are also deferred; the current scoped tools and native collection ownership provide a smaller coherent batch.
