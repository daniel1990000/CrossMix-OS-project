# Host correctness fixes, 24 October 2026

The device remains unavailable. We fixed three reproducible defects in the
existing interface, recovery copier and release tooling.

* A delayed Games response could populate Favorites, and a delayed Favorites
  response could replace All games. The model now checks the active view before
  replacing that page. Favorites caches and filter serial checks remain active.
* If opening a recovery destination or one of its parents failed, the copier
  leaked the source descriptor it had opened. The copier now acquires the second
  descriptor inside the cleanup scope for the first.
* Packaging could label modified or incomplete source as clean when Git index
  flags hid edits or deletions. It also missed changes to the consumed spruce
  lock outside `project/`. Packaging now compares the complete export scope and
  its bytes with committed Git blobs. Export collection and comparison share
  the existing allowlist; inherited/native/evidence exclusions retain their scope.

Seven regression methods produce nine assertion failures on baseline
`17339c0575791914cf5c869addc034ae5c90a745` and pass on the fixes. One additional
compatibility test checks omitted files outside the source export scope.
Independent review caught the hidden deletion case before completion and passed
the revised code. Fault injection through 1,000 failed copies kept file handles
stable and preserved source contents.

The complete five-source certification passes **1,107 tests**, with zero skips,
errors or failures. The clean implementation and build select
`de9ecf099a305f2623086c9d78b808fe4d14197c` and development descriptor
`smartpro-psp-0.1.0-dev17`. The package contains 66 signed payload files and 224
original-source inventory entries, SHA-256
`bd52faec9e9e08c0b1ffaf2603a907409017835bf8bc3eae44a4797d6ac81f91`.
Installed SDL smoke, signature/payload verification, deterministic same-key
overlay rebuild and fixture rollback pass. A source export without Git reproduces
both ZIPs byte for byte using another disposable signer. The builders deleted
their generated private keys.

The [verification receipt](../evidence/host-fixes-20261024/verification.json)
links the exact checks, source and build reports. The [CI run](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/40053305796)
also passes all 1,107 checks. We downloaded its 5,251,166-byte artifact and
verified the provider digest, eight inner checksums, signed payload and complete
source inventory. Both CI ZIPs match the local ZIPs byte for byte. The artifact
expires 22 January 2027; this checkpoint adds no independent private retention.
Later handover/evidence commits have their own source inventories.

The latest public download remains the published dev16 computer preview. This
checkpoint does not publish another release or alter its fixed packet. The
register remains 14/25 complete and 0/13 physical areas run. Device/profile gates
stay disabled. Actual recovery/inventory, game-scene measurements, device
qualification, precise native distribution decisions and operational custody
remain open.
