# Work completed without the Smart Pro

The dev14 continuation covers native distribution research, signing-key recovery
verification, upstream maintenance review and retained original-only host delivery.
The exact build, CI, hosting and storage results belong to
`project/evidence/nondevice-completion-20261023/verification.json`; an absent
result is pending work, never a pass. The dev13 receipts keep their original
source and artifact identities.

The retained compiler was also recovered into an observed empty container daemon.
Its restored toolchain compiled and linked original AArch64 C/C++ smoke programs
without network access; target executables were not run.
[Exact compiler recovery](nondevice-compiler-2026-10-23.md) closes that previously
unrun custody check.

The shipped runtime selectors remain unavailable. No native binary, upstream
patch, firmware, SDK, commercial game data or owner saves enter the original-only
host downloads. PR #1 remains draft and unmerged. No device is connected or
activated, and no author message is sent.

## Completion boundaries

| Register row | Work available without hardware | Remaining completion requirement |
|---|---|---|
| R06 | Exact incorporated-component and notice/source packet, with retained-source readback; current original-only distribution scope | Explicit unresolved native recipe/IGM/SDK grants or replacement of those inputs for a selected public native release |
| O01 | Independent recovered-key challenge and possession verification; workflow provenance for host artifacts | Owner-selected operational signer, protected independent recovery access, and actual production custody/revocation distribution |
| O02 | Stable original-only host downloads, exact hashes, source, notices, support instructions, retained retrieval and provenance | Qualified supported device matrix and operational trust for a device release |
| O03 | Current scoped upstream comparisons and dispositions, maintenance matrix, bug triage and clean host rebuild | Named ongoing maintainer and the first physical pilot, followed by affected device requalification |
| D02/D03/D05/D06/N01/N02/P04 | Existing recovery, inventory and qualification tooling remains ready | Actual device/card/runtime/save observations, restoration and scoped physical qualification |

These are the original register criteria. Host downloads and review tooling do
not turn a partially completed device-release row into a complete one. The
master total remains 14/25 until a row's remaining evidence exists; physical
acceptance remains 0/13.

See the [distribution review](nondevice-distribution-2026-10-23.md),
[key recovery](nondevice-trust-2026-10-23.md) and
[maintenance review](nondevice-maintenance-2026-10-23.md) for the exact scope.

## Verify host downloads

Download the original-only host preview ZIP, original-source ZIP, checksum index,
build report, source report and certification from the dev14 host prerelease.
Its release notes and verification receipt identify the exact source commit,
workflow run and attestation bundle. Follow `START-HERE.txt` on a computer.

With a current GitHub CLI, verify each downloaded artifact against the expected
repository, signer workflow, source ref and source commit:

```sh
gh attestation verify ARTIFACT \
  --repo daniel1990000/CrossMix-OS-project \
  --signer-workflow daniel1990000/CrossMix-OS-project/.github/workflows/smartpro-offshoot.yml \
  --source-ref refs/heads/build/spruce-psp-experience \
  --source-digest EXPECTED_IMPLEMENTATION_COMMIT \
  --deny-self-hosted-runners
sha256sum -c SHA256SUMS
```

For retained offline provenance, add `--bundle host-preview-provenance.jsonl`
after obtaining the bundle and expected source identity independently. Online
verification also checks current repository identity. GitHub's attestation
binds artifact digests to a workflow invocation and source revision. It supplies
no physical qualification, private Ed25519 key custody, upstream endorsement or
native distribution grant. The overlay continues to use the existing
independent signing and registry system.

The provenance job runs only after a successful manually selected repository
build. Pull-request validation keeps read-only permissions. Actions are pinned
to commit identities. Artifact storage and public hosting have their own fresh
readback evidence; availability has no permanent guarantee.
