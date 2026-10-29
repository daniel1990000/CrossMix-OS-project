# Dev20: settings and reusable host audit

This continuation starts from dev19 handover
`1ef6aa1e7856a93ed2328b60cbf04eff88dc914a` on
`build/iso-next-round-20261028`. PR #3 and its exact implementation/package
identities remain separate. No release is published or merged by this work.

## Settings clarity

The per-game choice now says **Use current global setting**. Its description and
review confirmation explain that PPSSPP can save the inherited value as a local
per-game setting after play. Local, inherited and unavailable status follows the
existing settings authority. Returning from native screens discards old dialogs
and previews and refreshes that authority without discarding Undo receipts.
Native writes to an owned option still invalidate previews and conflict with
Undo. No persistent inheritance or additional configuration writer is added.

The native-write regression first changes only the game's INI, keeping the global
INI unchanged, to prove stale-preview rejection is caused by the native write.
It then changes global settings separately to demonstrate the newly local value.
Other regressions cover refreshed display, unavailable values, out-of-order reads
and refresh errors.

## Development tooling

The [host audit collector](host-gameplay-audit.md) uses the existing gameplay
importer/comparator and process supervisor. It requires exact frozen input and
configuration identities, binds the observer to the launched PID/executable,
rejects competing runs, retains raw/late/failed observations and revalidates
reports against those raw samples. It adds no frontend runtime API or device
activation route.

The [virtual controller helper](../dev/host_virtual_controller.md) adds four
analogue axes, recorded publication/application timing, retained process start
identity and expiry neutralization. It is development source. Its original C
source is included in source exports; its binary is excluded from the runtime
payload and source ZIP. SDL host readback tests do not establish physical latency.

## State interruption diagnostic

The [retained report](../evidence/iso-next-round-20261028/native-interruption.json)
exercises ten deterministic process interruptions of real extracted native
functions with explicit serializer/platform fixtures. It preserves the initial
failed diagnostic attempt. This is not a whole-emulator kill or power-loss test.

The existing consumer rejects incomplete future receipts. However, the unmodified
native publication sequence can lose the prior completion receipt, and same-slot
replacement can invalidate the prior state's original path/hash. Only two of ten
probed windows preserved a usable prior completion. Native Undo bytes at another
path are not an authenticated checkpoint. This diagnostic does **not** satisfy
last-valid-completion preservation acceptance.

The separately locked optional [0006 snapshot extension](../ppsspp/state-snapshots.md)
addresses this defect for new saves without changing the packet format or
qualification authorities. It copies a completed native state to a verified
immutable generation beneath the existing approved root, then publishes the
final result before replacing the positive completion. The directory stops at
32 files or 512 MiB, counts interrupted copies and never deletes retained files.
Legacy mutable receipts are not migrated. Six source test methods exercise
16 interruption windows and 12 fault cases. Their
[retained fixture report](../evidence/iso-next-round-20261028/native-snapshot-fixture.json)
has separate identity from the original defect probes. A private full SDL build
with 0006 has also completed; the [whole-emulator report](../evidence/iso-next-round-20261028/native-whole/verified-summary.json)
now passes eight precise same-slot interruption windows and a fresh-process native
load of the preserved immutable snapshot, with normal exit. Independent review
verified 175 retained raw artifacts. Early setup/stop-timing attempts are retained
separately and excluded from the final matrix. This is host process interruption,
not physical power-loss durability or authenticated frontend promotion. No shipped
profile selects the patch.

## Evidence and remaining acceptance

[Startup evidence](../evidence/iso-next-round-20261028/startup.json) records remote
inspection, the failed full-clone attempt and successful exact branch recovery.
The private ISO was absent and has been recovered; its full size and SHA-256
match the owner's identity. The earlier desktop binary and private gameplay
fixtures were absent, so their recorded hashes cannot be reused as fresh evidence.

Ordinary savedata requires a fresh process using the game's Continue action with
no emulator state loading. Convenience checkpoints remain separate. Moving
on-foot, driving and action comparisons require legitimate frozen scenes and
five independent 30-second pairs per scene, followed by isolated 30-minute runs
at each resolution in the most demanding reproducible scene. No measurement is
accepted merely because the collector exists or a test passes.

Audio quality, frame pacing, latency and energy remain unavailable. Tiny native
FPS differences are not improvement claims. Host evidence cannot qualify TrimUI
presets, authenticated frontend Resume or physical acceptance. The original
register stays **14/25**, physical acceptance **0/13**, with production/device
gates disabled and published dev16 preserved.

## Final scope and owner stop — 29 October

The owner explicitly stopped game testing because of usage cost. No further
GTA gameplay, comparisons or soaks are authorized by this handover. The owned
emulator exited through native UI normally with exit code 0. Soldier was not
completed, game SAVEDATA remained empty, and ordinary fresh-process Continue is
unverified. Convenience checkpoints do not change that result. Broader scene
collection produced zero accepted runs, pairs or soaks; the collector has not
completed a live end-to-end acquisition. No performance improvement is claimed.

Exact implementation `50bbc3595c29238085d737cfe088971b0b514012` passes
1,263 strict checks, zero skips/errors/failures, against all five exact pinned
sources. Its clean development package passed installed smoke, fixture rollback,
signatures/inventories and byte-identical no-Git source-export rebuilding (68
payload files, 247 source entries). Independently read-back CI run 40787227636
passed for that head using separate merge checkout
`df2a17b2be18466ec08559007e9335df60433ea1`. Later documentation commits have
separate identities. [Final verification](../evidence/iso-next-round-20261028/verification.json)
links exact package/CI receipts. Published dev16 and all device gates are unchanged.
