# Disposable host trust lifecycle rehearsal

O01 now has an executable host exercise using the existing overlay signer,
external trust registry, verifier and rollback implementation. It accepts no
existing key, package or card. It creates an explicitly marked host fixture,
original Python payload and two disposable Ed25519 keypairs outside Git. All
keys, signed packages and fixture contents are removed before the report is
returned. Removal is ordinary filesystem cleanup; it is not a secure-erasure
claim. The generated keys must never become production identities.

```sh
PYTHONPATH=project python3 project/tools/trust_rehearsal.py \
  --output /tmp/trimui-trust-rehearsal.json
```

The destination must be new, with an existing parent. Reports publish only after
file and directory fsync, refuse symlink parents and existing destinations, and
contain public fingerprints, registry/package/manifest hashes and fixed outcome
labels. They contain no private key bytes, key paths or signed package bytes.
Random keys mean a new run has new fingerprints and signed-package hashes.

Publication also reads back the actual report bytes, checks the file identity
and reopens the requested parent to detect directory replacement. A changed
file or parent returns failure. Unrelated replacement files are preserved.

The exercise verifies:

- Active signing and exact package payload verification, including same-key
  deterministic rebuilding.
- Rotation to an independently selected new primary key: the old key is retired
  and still verifies existing packages, but fails the signing-status gate.
- Unknown signing identities, changed public bytes, duplicate registry entries
  and a tampered signed archive payload are rejected.
- An unfinished activation can roll back to a retained old package whose retired
  key is still trusted. A newer synthetic save remains unchanged.
- Revoking that old key rejects its package and blocks rollback to it. The
  current selector and newer save remain unchanged, and the existing
  `force-classic` request remains present. That request is not evidence that
  classic actually displayed or that physical recovery worked.
- A new recovery fixture package built from the pristine original fixture with
  the current active key and a nondecreasing security epoch can be staged and
  selected without restoring trust to the revoked key or overwriting the save.

The trust registry is an **external caller authority**. The existing
`load_trust_store(..., signing=True)` gate must run before signing;
`create_archive()` itself accepts a keypair, not a registry. A registry loaded
once is an in-memory snapshot. Re-read the independently controlled registry at
each operational decision; these tests do not implement distribution of trust
updates or invalidate previously loaded snapshots. Revocation changes future
verification decisions; it does not stop already installed code or authenticate
older reports.

O01 remains open. This fixture does not establish an operational trust root,
private-key custody, independently retained key recovery, access controls,
revocation distribution, actual incident response or original-device restore.
Its synthetic health receipts are explicitly host-only and are never device
qualification. Production/profile/runtime/source-use gates remain false.
Operational adoption still needs an owner-reviewed custody/rotation/revocation
procedure, separate recovery access and an actual retained-restoration exercise.
