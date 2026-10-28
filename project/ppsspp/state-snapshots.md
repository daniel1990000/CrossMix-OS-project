# Optional immutable completion snapshots

Patch `0006-immutable-state-completion-snapshots.patch` applies after the locked
0001–0003 patches to pinned PPSSPP `d357e6a32934800d3d80b49f910a603e1b069751`.
Its separate [lock](state-snapshot.lock.json) records the 0003 preimage and 0006
postimage. Diagnostic statistics patch 0005 is independent. No shipped binary,
profile or release selects 0006 automatically. The packet formats and existing
qualification authorities remain unchanged.

The preceding private-session extension can lose the previously eligible
completion during an interrupted save. Native slot finalization can first move
old bytes into its Undo path; later, publication replaces `save-completed` before
`result`. The host diagnostics retain this failure separately. Atomic publication
of each individual file does not make those files one transaction.

With 0006, a successful native save first copies its finalized state into a
unique file in `.trimui-state-snapshots` beneath the request's existing state
root. The snapshot carries the same slot/game/session evidence and exact state
size and SHA-256. It is never the normal native slot or native Undo path. The
native owner checks source stability, file type, ownership, private permissions,
links and exact copied bytes; it synchronizes the snapshot file and directory
before publishing its name in a result. Native slots and their Undo behavior
continue through the existing native implementation.

The extension publishes the complete final result before replacing its positive
completion receipt. Death before that final result keeps the preceding result
and completion. Death after the result but before the new completion keeps the
older completion bounded by the newer result. A later failed copy or save also
keeps the previous completion. Those receipts refer to immutable generation
snapshots, so another save into the same native slot preserves their bytes.
An interruption after a complete new final result can make that new completed
snapshot visible to direct result consumption; that is an actually completed
state, and existing qualification checks still apply.

Snapshot retention stops at **32 files or 512 MiB in total**, including failed,
empty and interrupted copies. A new snapshot must fit both limits. The private
snapshot directory has a nonblocking exclusive native lock while checking and
creating files. Existing entries must be private regular files with one link;
unexpected links, directories or permissions reject the operation. Creation
uses bounded exclusive names and never truncates or replaces an existing file.
No referenced, incomplete or unknown file is automatically deleted. At the limit,
new completion export fails while earlier snapshots remain. Offline custody and
cleanup require an explicit operator inventory of references; this patch does
not provide a cleanup command or assume that unreferenced files are safe to
remove.

This protection applies to receipts created with 0006. **Older receipts pointing
to mutable native slots are not migrated or repaired. Load acknowledgements keep
the exact requested path/hash/slot: only loads of these immutable snapshots have
the same preservation property. Arbitrary or legacy mutable load inputs can
still be invalidated by later native writes.** Native trusted-caller
packets remain separate from authenticated frontend state adoption. The patch
does not qualify caller metadata, activate production Resume, or replace the
existing source, writer, foreground, slot, hash and freshness checks.

`tests/test_state_snapshot_patch.py` applies the locked patch and compiles its
actual functions in the existing explicit serializer/platform fixture. Tests
kill only their own child at state, copy, synchronization and result/receipt
publication boundaries, using disposable data. They check both same-slot and
separate-slot saves; copy corruption, source changes, write/fsync/rename failures;
count/byte limits including incomplete files; and foreign links/permissions.
Prior immutable bytes and eligible completion envelopes must survive, while
profile authority remains unavailable. These tests do not execute the full
emulator, validate filesystem power-loss durability, or qualify hardware.

Capture retained raw fixture evidence outside Git with:

```sh
PYTHONPATH=project:project/ppsspp/tests PPSSPP_SOURCE_ROOT=/path/to/pinned/ppsspp \
  python3 project/ppsspp/tests/capture_state_snapshot.py --output /private/new-output
```

The capture includes exact patch/harness/compiler-output identities, raw
synthetic packet and state artifacts, failed-scenario outputs and acquisition
timing. Game data and full emulator distributions remain private. Whole-emulator
interruption tests, when performed, need their own exact binary/source identities
and retained raw records; a fixture receipt does not certify that binary.
