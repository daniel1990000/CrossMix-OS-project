# Recovering a signing key without the Smart Pro

O01 does not require device access to establish signing-key custody. It does
require an owner-controlled trust root and a recovery recipient. The current
environment provides GitHub access and owner-only Drive retention, but no
designated release key, owner wrapping public key or separately controlled
recovery service. No production key was created. Uploading a raw private key to
Drive, or storing a generated backup password beside its encrypted archive,
would not supply the missing independent recovery control.

The existing [disposable lifecycle exercise](trust-rehearsal.md) covers active,
retired and revoked keys through the real package verifier. It does not establish
custody of a persistent release identity. The new
[`operational_trust.py`](../tools/operational_trust.py) verifies possession of an
exact recovered key using a challenge selected by an independent verifier.
It accepts an existing key and never creates or exports a key.

## Exact recovery proof

The verifier keeps the public-key fingerprint from the previously approved trust
root. After a separate operator retrieves and decrypts the retained backup, the
verifier creates a fresh challenge bound to the retained envelope digest and an
opaque custody record. The challenge contains a random 256-bit nonce. Keep its
returned SHA-256 separately from the challenge file.

```sh
PYTHONPATH=project python3 project/tools/operational_trust.py challenge \
  --expected-fingerprint INDEPENDENT_PUBLIC_KEY_SHA256 \
  --retained-envelope-sha256 RETRIEVED_ENCRYPTED_BACKUP_SHA256 \
  --custody-reference owner-key-recovery-record-123 \
  --output /private/review/challenge.json
```

On the recovery workstation, the raw libsodium Ed25519 secret must contain 64
bytes, have mode 0400 or 0600, and reside in an owner-only directory outside Git.
The tool refuses links and changes during readback. Its signature covers a fixed
recovery-only domain and the complete challenge.

```sh
PYTHONPATH=project python3 project/tools/operational_trust.py prove \
  --private-key /private/recovered/release.key \
  --public-key /private/independent/release.pub \
  --challenge-file /private/review/challenge.json \
  --expected-challenge-sha256 INDEPENDENT_CHALLENGE_SHA256 \
  --output /private/review/recovery-proof.json
```

The verifier checks the public proof against their own fingerprint and challenge
digest. An older proof fails under a fresh challenge. Reusing a challenge would
reuse its proof, so the external verifier must consume it only once. Historical
offline verification deliberately has no wall-clock expiry; a successful check
does not establish the time at which recovery occurred.

```sh
PYTHONPATH=project python3 project/tools/operational_trust.py verify \
  --proof /private/review/recovery-proof.json \
  --public-key /private/independent/release.pub \
  --expected-challenge-sha256 INDEPENDENT_CHALLENGE_SHA256 \
  --expected-fingerprint INDEPENDENT_PUBLIC_KEY_SHA256
```

The proof contains a public key, challenge and signature. It contains no private
key bytes, key paths or recoverable backup. Signing reads the secret into the
Python process; this tool provides no locked-memory or secure-erasure guarantee.
Reports use the existing fsynced, no-replace publication and exact readback path.
CLI failures do not echo secret paths or exception values.

## Remaining operational inputs

The owner or release maintainer must designate the trust root and provide the
recovery recipient through their existing secret-management process. Retain an
encrypted backup, remove the working recovery copy, retrieve it through the
designated recovery access, decrypt it and produce the fresh challenge proof.
Keep storage ACL/retrieval records separate: a signature proves key possession,
but it cannot establish the location from which the key was obtained or who
else can retrieve it.

Use the existing external registry for rotation and revocation, with separately
retained expected hashes. Publish the public root and registry through the
reviewed release channel and record independent readback before relying on
them. Retired keys must continue to verify retained rollback packages; revoked
keys must fail. Keep a replacement trusted recovery package ready before
revoking the only eligible rollback identity. Actual installed-device trust
updates and recovery remain part of physical qualification.

All possession proofs keep operational designation, retained-storage provenance,
independent recovery access and hardware gates false. They do not change runtime
configuration or clear distribution rights. O01 remains open until the actual
owner-controlled custody and recovery evidence exists.

## Validation

Twelve focused tests pass with real libsodium signatures. They cover corrupted
secret/public pairs, public-key substitution, challenge replacement and replay,
signed-field modification, unsafe key modes/links, concurrent key mutation,
scope inflation, existing output preservation and subprocess proof verification.
Test keys are temporary fixtures removed with their test directories. No
persistent candidate key or retained key backup was created during this work.
See the [verification record](../evidence/nondevice-trust-20261023/verification.json).
