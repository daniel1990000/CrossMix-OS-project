# Continuation review: retained evidence and release blockers

Reviewed 22 October 2026 from repository checkpoint
`3c665e4b3003864457f0fddd05eb4e5ca12b060d`. This is a review of the checked-in
records and packaging source, not a new licence determination, notification
receipt, binary rebuild or device observation. No recipient was contacted and
no qualification flag was changed.

The [distribution register](distribution-register.json),
[release-rights summary](release-rights.md), engine notices and final build
records agree that combined/native distribution is **not cleared**. Their
historical build successes do not contradict that status. Original-only
development packaging remains a separate scope.

## Workspace continuity finding

The following historical paths were absent in the continuation workspace when
this review was performed:

- `/workspace/scratch/ppsspp-complete-checkpoint-final`
- `/workspace/scratch/retroarch-igm-tg5040-final`
- `/workspace/scratch/trimui-source-review-20261022-dev4-ready`
- `/workspace/scratch/trimui-development-20261022-dev4-ready`

The checked-in hashes describe previous retained outputs; this review did not
reverify those bytes. Do not promise a download of an absent native candidate
or use a hash record as a substitute for its matching source archive. Recover
private outputs from an independently available copy and verify them against
the records, or rebuild from the pinned inputs. A rebuilt output with a
different digest needs its own evidence and matching source; retain the old
record as history. Original-only development artifacts and the review kit can
be regenerated independently without enabling device use.

| Historical retained output | Expected SHA-256 | Evidence |
|---|---|---|
| PPSSPP `candidate-corresponding-source.tar.gz`, 177,983,212 bytes | `2b437d761edd97081e57d82792f45e3d154dc3380656bb0a126a90a28684c4ae` | [Final PPSSPP record](../evidence/ppsspp-complete-state-build.json), `corresponding_source` |
| RetroArch `source-inputs.tar.gz`, 143,630,943 bytes | `ee37594defe5824e58c30fec6eb2f59db7d56c50a5f7875efc3c6ca4b336ae74` | [Final IGM record](../evidence/retroarch-igm-build.json), `retention.source_inputs` |
| RetroArch `build-records.tar.gz`, 552,133 bytes | `b4c2c640abf5b18ec7c934a85a548598aa95a09e6388591cda17941cf1d074b3` | [Final IGM record](../evidence/retroarch-igm-build.json), `retention.build_records` |

These complete source/build archives remain private while the existing review
is unresolved. Rebuilding them does not itself clear their distribution.

## Evidence required to resolve each blocker

| Area | Existing evidence | Next concrete evidence needed |
|---|---|---|
| PyUI use and derivatives | Exact outer/nested licence hashes, two pinned recipients, prepared unsent notice | Explicit owner send instruction or owner-supplied delivery evidence; retain the exact sent text, recipients, date and delivery reference privately, then review scope. A prepared public GitHub contact is not proof of delivery. |
| PPSSPP recipe and modifications | Pinned recipe `9f770cb…`, exact selected patches and recipe assembly | A reviewed grant or applicable terms covering the exact recipe and selected third-party modifications. The project modification's GPL label does not resolve an external recipe's missing grant. |
| RetroArch IGM source and recipe | Pinned recipe `71d84da…`, source hashes and project modification notice | Reviewed terms for the exact shared IGM code and recipe, separately from RetroArch's upstream licence. |
| Native dependencies and toolchain runtime | SDK ABI inventories; exact GCC9 static C++ runtime hash; retained FFmpeg configuration | File/component-level terms and scope for the actual distributed bytes, including statically incorporated runtime code and any bundled SDK libraries. Distinguish build-only tools, code incorporated into the executable, bundled dynamic libraries and dependencies expected on the device. |
| Exact native source availability | Historical archive sizes/hashes and recorded notice inventories | Recover/rebuild the matching private archives and verify their inventories before any future distribution decision. Keep source/build identity paired with the exact candidate, not merely its version string. |
| Ports | Per-title source/runtime profiles and no owner data bundled | Review the exact selected engine/runtime and data requirements for each title; there is no blanket PortMaster grant. Physical acceptance remains separate. |

The PPSSPP record's 55 named notice files are an inventory, not 55 reviewed
component grants. For example, the inventory includes notice implementation
files and empty nested `build/LICENSE` files. Use retained upstream/component
terms and the actual compiled configuration to resolve scope; do not count
filenames as clearance. The ABI audits also cannot establish distribution
rights or the loader's actual device choices.

## Packaging boundary checked

`project/packaging/dev_release.py::original_source_entries` excludes spruce
patch directories, all PPSSPP directories except original theme data, and the
RetroArch source-patch directory. It excludes the unsent notification draft
from the optional original-source ZIP. These exclusions apply to generated
development artifacts; the draft and separate licence-scoped patches are
already tracked in the repository. Do not describe those tracked files as
private merely because the ZIP omits them.

Continue original host tooling and acceptance preparation. Keep the draft PR
unmerged and all runtime, source-use, hardware and combined-distribution gates
disabled until their corresponding evidence is independently reviewed.

The continuation subsequently regenerated original-only development artifacts and a verified private review kit at the new paths in [HANDOVER.md](../../HANDOVER.md). It did not recover or rebuild the native candidates or matching native source archives. The historical paths above remain absent.
