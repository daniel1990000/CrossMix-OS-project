# Software validation fixes, 23 October 2026

The current candidate is **smartpro-psp-0.1.0-dev13**, an original-only host
preview. This continuation fixes reproducible validation and cleanup defects
found after dev12. The owner confirms that no device is available and requests
continued software work. No physical acceptance result is added.

## Fixed defects

- **R02 source certification:** a deleted consumed source file could disappear
  from checking when Git's assume-unchanged flag hid it. The runner now checks
  the index against the committed tree, permits missing blobs only when the
  sparse index excludes them, and verifies the owner executable bit. It also
  disables replacement objects and filesystem monitor commands while querying
  source identity. Valid sparse checkouts remain supported.
- **D03 disposable probes:** a successful helper could leave a background child
  after closing its output pipes. The runner now observes the root's exit
  without reaping it, stops its disposable process group while the root PID
  remains reserved, then checks the root's exit status. This covers children
  in that group; it is not containment of arbitrary untrusted code.
- **D05/D06 evidence review:** a passing retest could predate the failed attempt
  it replaced, and numbered cycles could run backwards. Retests now follow
  the superseded attempt, and first executions must have nonoverlapping times
  in numbered order. A later retest of an earlier cycle remains valid.
- **O02 revocation receipts:** an unknown signer or corrupt substituted package
  could be credited as proof of revoking the reviewed signer. The diagnostic
  path now verifies that exact signer's package, source, notices and host-only
  support scope before testing rejection by the external revoked registry.
  This diagnostic verification grants no activation authority.
- **O01 trust reports:** report publication could return the digest of buffered
  bytes after the published file changed. The writer now reads the published
  file and checks its identity, bytes and parent pathname before returning.
  A concurrent unrelated replacement is retained and reported as failure.

These changes have regression tests and independent review. Exact local and CI
results, source/build identities and package checks are recorded in
[the validation evidence](../evidence/software-hardening-20261023/verification.json).
Historical dev12 receipts continue to describe their original artifacts.

## Completion limits

The register remains **14 of 25 completed scoped rows**, including 13 host
engineering rows and owner-confirmed R05 private source use. **Zero of 13
physical areas have run.** A larger host test count does not complete a physical
or operational criterion.

| Open work | Required evidence or decision |
|---|---|
| D02 | Complete actual card/save/necessary internal backups, independently retained readback and expendable-media restoration/classic recovery. |
| D03 | Actual TG5040 firmware, filesystem, runtime, writers and kernel/tool observations after D02. |
| D05/D06 | Core physical casebook, failures and retests, independent review and a deliberately scoped production configuration. |
| N01/N02/P04 | Separate native-engine, same-boot Resume and per-title device qualification, with owner content and applicable rights. |
| R06 | Exact public native component terms, corresponding sources and combined notices for any selected native distribution. |
| O01 | Operational key custody, independent trust distribution and real recovery/rotation/revocation evidence. |
| O02 | Device-qualified support scope and stable hosting of the actual reviewed release. |
| O03 | Maintenance owner, first pilot, scoped drift decisions and requalification practice. |

Both shipped runtime selectors remain unavailable. Production, profile,
runtime and source-use gates remain false; no native binary, upstream patch or
Celeste patch is selected. PR #1 remains draft and unmerged. No author message,
device installation, firmware operation or public release is performed.
