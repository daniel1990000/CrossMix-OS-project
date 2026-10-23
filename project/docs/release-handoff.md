# Original-only release review handoff

`tools/release_handoff.py` finishes the host packaging and custody-receipt
workflow for O01/O02. It produces a durable, independently readable review
directory using the existing overlay signature and trust-registry authorities.
It does not generate keys, sign a new release, upload files, create tags, deploy
software, install on a device or promote production/source-use qualification.
Operational custody and public device delivery remain evidence-dependent.

## Prepare an exact reviewed bundle

Use an already reviewed output from `packaging/dev_release.py --include-source`
with its completed host smoke. Supply the trust key and expected fingerprint
through a separate reviewed channel. The key inside the artifact directory is
informational and is refused as the independent trust input.

The artifact checksum index must also be supplied independently, with its own
expected SHA-256. This is necessary because the signed overlay does not
authenticate its adjacent screenshot and outer instructions. For a retained CI
artifact, the previously reviewed `inner_checksums` receipt supplies those
expected entries; do not generate expectations by trusting a newly received
directory. The tool checks every artifact, signature, payload and source join
after the independent index comparison.

```sh
PYTHONPATH=project python3 project/tools/release_handoff.py prepare \
  --artifacts /private/reviewed-development \
  --public-key /private/independent-trust/development.pub \
  --expected-fingerprint PUBLIC_KEY_SHA256 \
  --trust-reference private-review-record-123 \
  --reviewed-checksums /private/independent-trust/development-SHA256SUMS \
  --expected-checksums-sha256 CHECKSUM_INDEX_SHA256 \
  --stable-url https://example.org/review/smartpro-preview \
  --output /private/smartpro-review-handoff
```

The HTTPS URL is supplied metadata only. Credentials, query tokens, private IP
addresses, traversal and local hostnames are refused. The tool performs no
network request and records availability/publication as unverified. A valid URL
does not establish durable hosting or authorize publication.

Inputs must be bounded regular files. ZIP entries are read without extraction,
with per-entry/total byte budgets, fixed roots, case-sensitive and case-folded
duplicate rejection, no links/special entries and no encryption. Signed source
inventory entries must match actual exported source bytes. The preview ZIP must
match the exact signed payload. The original MIT project and Noto Sans OFL
notices must match the corresponding source export. Scope excludes upstream
source distributions, native engines, commercial data, saves and signing keys.
Only explicitly inventoried original source enters the source ZIP; an unrelated
directory is never recursively copied into the bundle.

The result contains the eight verified development artifacts, generated
install/update/rollback instructions, an explicit host-only support matrix,
known limitations, trust-review metadata, a pending custody checklist and a
minimal redacted support summary. All files receive SHA-256 identities in
`index.json`. The returned index digest must be retained independently. A
checksum index placed beside its own files is not an independent authority.

Publication to a new local directory uses fsynced files/directories and Linux
`renameat2(RENAME_NOREPLACE)`. Existing or concurrently created destinations are
never replaced. This host tool uses the current Linux/Python 3.11+ development
environment. An unavailable atomic-publication primitive refuses publication.
Any failed preparation/publication retains its `.handoff-*` staging directory
or uncertain published bundle for manual review. The tool never recursively
deletes a failed pathname, even after an identity check: that name could be
replaced between the check and deletion. A failed final directory fsync returns
failure and does not claim successful durable publication.

## Fresh readback

```sh
PYTHONPATH=project python3 project/tools/release_handoff.py verify \
  --bundle /private/smartpro-review-handoff \
  --expected-index INDEPENDENT_INDEX_SHA256 \
  --public-key /private/independent-trust/development.pub \
  --expected-fingerprint PUBLIC_KEY_SHA256 \
  --trust-reference private-review-record-123
```

This repeats file, signature, source, notice, support-scope and instruction
checks. Added files, changed bytes, source/preview drift or an invented device
gate are refused. An optional `--registry /private/trust-registry.json` uses the
existing external active/retired/revoked rules. Every nonrevoked key referenced
by that registry must also remain outside the supplied bundle/artifact tree.
Neither the tool nor a reference string authenticates how the operator obtained
the independent key, checksum or index; the reviewer owns that trust decision.

## Custody, readback, rotation and revocation receipts

`custody-receipt` creates a new immutable JSON observation outside the bundle.
It accepts no private-key input. Each receipt binds the independently expected
index, public fingerprints, a selected external registry hash, an opaque private
evidence reference and an optional previous receipt hash. It does not copy full
private correspondence, local key paths, secret files or arbitrary operator
notes into the bundle.

```sh
PYTHONPATH=project python3 project/tools/release_handoff.py custody-receipt \
  --bundle /private/smartpro-review-handoff \
  --expected-index INDEPENDENT_INDEX_SHA256 \
  --public-key /private/independent-trust/development.pub \
  --expected-fingerprint PUBLIC_KEY_SHA256 \
  --trust-reference private-review-record-123 \
  --step readback --evidence-reference independent-retained-retrieval-456 \
  --output /private/receipts/readback.json
```

- `readback` actually repeats exact bundle/signature verification. It does not
  itself establish that these bytes came from independent retained storage.
- `key-custody` and `recovery` retain the owner's external evidence reference.
  The result explicitly says the operator statement is not independently
  proven. The tool never asks to read or export a recovered private key.
- `rotation` requires an actual external registry with the package signer
  retired and a different selected active primary. The old package must verify
  under that registry. It does not generate the replacement key or prove its
  custody.
- `revocation` requires that the actual registry revokes this package's signer
  and that the existing overlay verifier rejects these exact package bytes.
  The independently retained index binds the otherwise no-longer-trusted
  artifact. Revocation is not a physical rollback, does not remove installed
  code and may remove eligibility to roll back to an older package.

Use `--previous /private/receipts/previous.json` to hash-chain observations for
the same bundle. The chain detects changes relative to separately retained
receipt hashes; the records are not signatures or authenticated statements.
All receipts keep `production_trust_established`, private-key custody proof and
actual key-recovery proof false. The checklist remains pending until a reviewer
evaluates the real external evidence. No automatic accumulation of receipts
qualifies a device or clears R05/R06.

This is a complete host engineering route for a reviewable original-only
deliverable. O01 operational completion still needs the owner's actual trust
root, custody controls, retained recovery and revocation distribution. O02
device-release completion still needs D06, applicable source/distribution
review, approved hosting and the supported physical matrix. None is supplied by
a development signature, a synthetic health receipt or a successful host build.
