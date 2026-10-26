# TrimUI Smart Pro implementation handover


## Next batch prepared: real-game validation — 26 October 2026

The full supplied GTA: Vice City Stories ISO is downloaded and verified.
Read [the ISO-enabled plan](project/docs/iso-enabled-roadmap-2026-10-26.md)
and [execution prompt](project/handover/ISO_EXECUTION_PROMPT.txt).
The user requested the prompt/plan now and execution afterward. No gameplay,
build, certification rerun or runtime change occurred in this planning step.

The batch targets real desktop saves/settings, patched native state evidence,
host launch/return/Continue, scene reports and fixes. It preserves existing
authorities and device gates. C01–C06 already exist; physical qualification
remains 0/13 and the original register remains 14/25 complete.
The dev17 results below remain historical evidence for their exact bytes.


## Current state: dev17 host correctness fixes

Continue on `main`. The owner still lacks device access and requested useful
independent work. We fixed delayed library replies replacing the wrong view,
recovery copy descriptor leaks and release identity mistakes under hidden Git
edits/deletions or a changed consumed lock. Clean implementation/build:
`de9ecf099a305f2623086c9d78b808fe4d14197c`. The development descriptor selects
`smartpro-psp-0.1.0-dev17`.

All **1,107 strict tests pass**, zero skips/errors/failures, against five pinned
sources. Installed smoke, signature/payload verification, fixture rollback,
same-key deterministic overlay rebuild and byte-identical no-Git ZIP rebuilds
pass. Independent review and old-code regression reproduction pass. Read
[the fix report](project/docs/host-fixes-2026-10-24.md) and
[exact evidence](project/evidence/host-fixes-20261024/verification.json).
Later documentation/evidence commits have separate source inventories.

CI run 40053305796 also passes all 1,107 checks. Downloaded artifact 12544371913
passes full signature, payload, source and checksum readback; both CI ZIPs match
the local ZIPs. Its expiry is 22 January 2027. No new independent private
retention was performed for this checkpoint.

The public dev16 preview and its fixed publication packet retain their exact
identities. This checkpoint does not publish a new release. Device gates remain
disabled; 14/25 register rows are complete and 0/13 physical areas have run.

## Published dev16 computer preview: historical exact snapshot

The owner explicitly instructed merging and publishing the completed work.
That instruction supersedes the earlier draft/unmerged hold for this host
software release. PR #1 is merged into `main` at
`87264629735e179c81c2ad360516665c1e7fd5cd`. Continue on `main`; the retained
`build/spruce-psp-experience` branch is the exact public source snapshot.
Earlier draft/unmerged statements below are historical.

[Dev16 is published](https://github.com/daniel1990000/CrossMix-OS-project/releases/tag/smartpro-host-0.1.0-dev16)
as an original-only computer-preview prerelease. Its tag and matching attached
source select `99336f6525efbd1b790a15c7de54acca3eacd1ec`, with 223 source files,
inventory `a0c9c9179528ddc0e9316a6aef2bda9c6f4d4ef24f70c91296d49c18a6ea834a`
and 66 signed payload files. This differs from the earlier a8ba317/933a1a
fix-build inventory because later documentation changed; those receipts remain
unchanged. Later main/workflow/evidence commits have separate source identities.

All **1,099 strict checks pass**, zero skips/errors/failures, against five pinned
sources. Source/provenance run 40041273891 and delivery run 40042094364 pass.
All ten provenance subjects and all eleven attached files were verified; full
uploaded bytes were read back before publication and freshly downloaded after
publication. A no-Git export reproduces both release ZIPs byte for byte, with
installed smoke and rollback passing. Development keys were deleted; GitHub
workflow provenance supplies host-download verification. Production device key
custody remains open. The shell upload limitation was resolved through the
existing Actions delivery route with a separate manual dev16 job and fixed
packet; the historical dev14 helper and release are unchanged.

See [publication report](project/docs/host-publication-2026-10-23.md),
[verification](project/evidence/host-publication-20261023/verification.json),
[receipt](project/evidence/host-publication-20261023/publication-receipt.json)
and [public readback](project/evidence/host-publication-20261023/public-readback.json).
Use the attached original-source ZIP for the matching preview source. GitHub's
automatic repository archives include inherited mixed runtime/history and are
outside the verified attached-asset scope. Native patches/engines, SDKs, games,
saves and private keys are excluded from these attached downloads.

The register remains **14/25 complete and 0/13 physical areas run**. All device/
profile gates stay disabled. Actual recovery/inventory, physical qualification,
five matched game-scene runs, 30-minute demanding profiles and measured presets
remain pending, together with precise public native distribution decisions,
production signing/custody and accepted maintenance ownership. Candidate presets
are untested; unavailable figures remain unavailable. PPSSPP/current PS1 routes,
games and memory-card locations are preserved. State galleries, named save
history and power-off Resume remain later enhancements. No author message was sent.

## Historical dev16 pre-publication fix snapshot

This continuation starts at `2d4a43dbc8eb472fbdeb98bc8e09b5432c3ef69b`.
Hardware remains unavailable. It fixes gameplay-report outputs overwriting
retained inputs/evidence, mixed measurement protocols across five repeated
pairs, and PS1 disc-reference symlink swaps after containment validation.
Existing in-card symlinks and native disc-management routes are preserved.
See [the fix report](project/docs/release-preflight-fixes-2026-10-23.md) and
[exact verification](project/evidence/release-preflight-20261023/verification.json).

Clean implementation/build: `a8ba3176e78d248162d3d40b91ec1d8b854491a9`.
**1,099 strict checks pass** (1,038 host/source plus 61 PPSSPP), zero failures,
errors or skips against the five pinned references. Seven added regression
methods reproduce the historical defects. Independent review passes all 40
focused checks, confirms legitimate symlink compatibility and finds no descriptor
leak through 1,000 repeated inspections.

Dev16 packaging verifies its signed 66-file payload, same-key determinism,
installed SDL/game-info/filter/backup smoke and fixture rollback. A no-Git source
export reproduces both ZIPs byte for byte with a new disposable signer; generated
keys are deleted. Its 223-file original-source inventory is
`5058e82140dc25e5d0b7ff429845b90566865cd804e25b92078192f953fcbd4d`.
[CI 39926662133](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39926662133)
also passes all 1,099 checks on clean merge
`933a1a5367552804cca8a78725e4c87779f9ce9b`. Downloaded artifact `12490006540`
is 5,246,728 bytes, SHA256
`96a1426c9201e8b3f27e57d531e6476c702a264749ebe6c4fa5cc6785bdc8c9a`;
all eight checksums, signature/payload and all 223 exported source files pass
fresh readback. It expires 21 January 2027; new independent owner-storage
retention was not performed. Later handover/evidence/docs commits have separate
source identities and do not inherit these exact package hashes or inventory.

The public dev14 preview, dev15 build `65fdc58` and historical evidence remain
unchanged. PPSSPP and the current PS1 route remain selected; no native code,
engine binary, game file or memory-card location changes. No playlist is generated.
The register remains **14/25 complete and 0/13 physical areas run**. PR #1 stays
draft and unmerged; all device/profile gates stay disabled. Actual recovery/
inventory, qualification, game-scene measurements and recommended presets,
precise public native distribution decisions, production signing/custody and
accepted maintenance ownership remain pending. Candidate presets are untested;
unavailable figures remain unavailable. State galleries, named save history
and power-off Resume remain later enhancements. Existing permission records
are preserved and no author message was sent.

## Historical dev15 software increments complete

The six requested additions are saved on the existing branch and draft PR #1:
per-game PPSSPP performance options/Undo, evidence-backed gameplay reporting,
game information, combined library filters, Continue/verified backup status and
read-only PS1 disc-set presentation. The original dev14 interface, launch/save
integration, native builds, retained compiler/artifacts, recovery and publishing
infrastructure remain the foundation. No native device build was needed.

Clean implementation/build commit: `65fdc58cb502d187b2259cec1691ad22482f07da`.
**1,092 strict checks pass** (1,031 host/source plus 61 PPSSPP), zero failures,
errors or skips against all five pinned references. Signature/payload checks,
same-key deterministic packaging, installed SDL/game-info/filter/backup smoke
and fixture rollback pass. The no-Git export rebuild reproduces both ZIPs byte
for byte. The clean 222-file original-source inventory is
`856aa7c97136a22cd8c7fb43b47897b7850ba6ca3f97653050ffe0c77b99326b`;
the signed payload contains 66 files. Generated disposable keys were deleted.
An initial full run rejected the displaced direct Game options shortcut; it was
restored alongside Game information before the final successful certification.
[CI run 39923557908](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39923557908)
also passes all 1,092 checks. Its actual clean PR merge checkout is
`aa1106734f392cc3506ede13fa642cdadb0a54b2`. Artifact 12488980507 was downloaded
and fully verified: 5,240,857 bytes, SHA256
`9098f9c0ceace681c1830506b87b55a635fdbab1a233d4119d20e7e60a652d24`.
All eight development checksums, signature/payload and 222 exported source files
pass readback. Its artifact expires 21 January 2027; independent owner-storage
retention was not performed for this new checkpoint. Dev14 custody is unchanged.

See the [continuation report](project/docs/release-continuation-2026-10-23.md),
[exact verification](project/evidence/release-continuation-20261023/verification.json)
and [updated active plan](project/docs/master-plan-2026-10-22.md).
The small stock desktop PPSSPP v1.20.3 save/load evidence uses existing GPL2
BlockOut II PSP software. Native logs confirm serialization, load-undo and
deserialization completion; host graphics/audio were not visually verified.
It does not exercise our native callback/Resume patches or qualify Smart Pro.
No game, emulator or state binary was added to Git. Gameplay metrics remain
unavailable; candidate presets remain untested. Native per-game writes require
live content/native-ID/preset/engine identity and existing verified INIs.

All six additions are complete as host software; actual gameplay measurement
and device acceptance remain pending. The original register stays 14/25 complete
and 0/13 physical areas run. Keep PPSSPP/current PS1 route, memory cards and game
files. No playlist generation or game movement occurs. Runtime/profile gates
stay disabled; PR #1 stays draft. Public native distribution, production key
custody and maintenance ownership remain open. State-gallery expansion, named
save history and power-off Resume follow later.

Dev14's published preview and historical receipts below retain their exact
identities and 1,011-check result. Later handover/evidence edits do not acquire
this clean implementation's 222-file source inventory or its package hashes.

## Historical dev14 baseline

The [computer preview is published](https://github.com/daniel1990000/CrossMix-OS-project/releases/tag/smartpro-host-0.1.0-dev14).
All eleven attached assets pass fresh readback before and after publication;
ten subjects carry verified GitHub workflow/source attestations. The public tag
selects clean build `ab644b93a463fe71d10cd32bb9f7fa113b30c771`, 60 signed payload
files and 207 original-source files, inventory
`b796a5e796e1de1cb180bf8769e4a45f34b551e418b389c70fd0750ba9e79eda`.
The local and CI preview/source ZIPs match; a no-Git export reproduces both ZIPs
and the signed overlay with the same subsequently deleted disposable signer.
CI run 39893214010 passes the exact build; run 39894762504 passes the later
workflow and verifies the published release again without release writes.
The earlier denied tag-publication attempt remains documented; the connected
repository application completed the exact tag/publication after full readback.

Dev14's CI archive, 14-file review handoff and complete provenance/publication
proof are retained in owner-only Drive and freshly retrieved. The compiler's
previously unrun empty-daemon restore now passes, including offline C/C++ link
smoke. Current native static coverage is in
[the supplemental source/asset report](project/docs/nondevice-native-coverage-2026-10-23.md).
No missing third-party grant is inferred from those inventories.

The attached allowlisted source ZIP is the matching source for the host preview.
GitHub's automatic repository archives include inherited mixed source/runtime
and historical engines; they are outside this verified attached-asset scope.
Later workflow, native-coverage and documentation/evidence heads have their own
source identities; they do not acquire the public build's source inventory.

The owner's instruction is **complete all remaining items that do not need the
Smart Pro**. Read [the nondevice completion report](project/docs/nondevice-completion-2026-10-23.md)
and its exact verification receipt. Dev14 adds recovered-key possession
verification, current upstream review and original-only host provenance/delivery.
The restored dev13 baseline passes 989 checks; the new software passes **1,011**
(950 host/source plus 61 PPSSPP), with no skips, failures or errors. Exact clean
build and CI identities are retained separately from that local development run.

The exact dev13 CI artifact now also has independent owner-only retention and a
fresh complete readback in
[its custody receipt](project/evidence/nondevice-completion-20261023/dev13-retention-readback.json).
Earlier records describing its absence of retention remain historical.

The owner does not have a signing/recovery destination to provide and need not
manage keys for the host preview. Use GitHub's exact workflow/source attestation
for host downloads. No persistent Ed25519 device-release key was created; actual
owner-controlled production custody/recovery remains open. Never ask the owner
to send a private key or password. Do not send another author notice.

Original-only host delivery is distinct from a device release. The original
register remains **14/25 rows complete and 0/13 physical areas run** until the
remaining exact grant, operational and hardware criteria are met. The PR stays
draft and unmerged, both runtime selectors return None, all production gates
remain false, and no native binary/upstream patch is selected. Dev13 and older
build/source/CI evidence retains its own exact snapshot identity.

## Historical dev13 continuation


The owner confirmed **no device access; continue software work** on 23 October
2026. The current original-only descriptor is `smartpro-psp-0.1.0-dev13`.
[Software validation fixes](project/docs/software-hardening-2026-10-23.md)
close reproduced source-certification, disposable-probe, evidence-chronology,
revocation and report-publication defects, with regression tests and independent
review. Exact validation/build/CI records are in
[verification](project/evidence/software-hardening-20261023/verification.json).

Strict local certification passes **989 checks** (928 host/source and 61 PPSSPP),
with zero skips, failures or errors against all five exact sources. Clean build
commit `7d21f63d8b8803b2d6af9dcb703cca429f50c3b5` has a verified 60-file signed
payload and 198-file original-source inventory
`ab91840f50415fd9468c06f54d88c3efb8994da5cfc57cbb62a268696092ba65`.
The source export reproduces both ZIPs byte for byte with the same disposable
development signer; the signer was deleted. Packaging verifies installed SDL,
navigation/settings/classic contracts and fixture rollback. These are host
results; exact CI/artifact identities are saved separately in verification.
[CI run 39891041396](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39891041396)
also passes all 989 checks on clean merge `ae1d11ea1b0c52bda8f579039183697cb3d811f9`.
Artifact `12474603842` was retrieved and fully verified against the provider
checksum; expiry is 21 January 2027. Later documentation/evidence edits preserve
these exact build identities and do not acquire their source-inventory digest.

The project remains **14 of 25 scoped rows complete; zero of 13 physical areas
tested**. The remaining rows require actual hardware, precise public native
distribution decisions or operational release evidence. Both shipped selectors
still return `None`, and no native binary or upstream patch is selected. PR #1
remains draft and unmerged. R05 private noncommercial permission remains
owner-confirmed; no further author notice is needed or authorized. Historical
dev12 receipts below retain their exact artifact/source identities and do not
certify changed dev13 bytes.

Current ephemeral setup: `/workspace/TrimUi`, Python
`/workspace/trimui-venv/bin/python`; pinned roots under
`/workspace/trimui-sources/{spruce,ppsspp,ra,ports,portmaster}`.
Set `PYSDL2_DLL_PATH=/workspace/scratch/trimui-host-libs/usr/lib/x86_64-linux-gnu`.
Use all five explicit source variables with `project/dev/check.sh` as documented
in `project/README.md`. Scratch is temporary; resume from GitHub evidence.

## Historical dev12 checkpoint

Checkpoint: **23 October 2026**. Active branch: `build/spruce-psp-experience` in `daniel1990000/CrossMix-OS-project`. [PR #1](https://github.com/daniel1990000/CrossMix-OS-project/pull/1) remains draft and unmerged. Continue the original TG5040 spruceOS/PyUI project under `project/`.

## Historical completion — dev12

The user's latest request is **“Finish everything.”** The owner is busy and
cannot provide device/card/SSH/operator access now. The owner also confirms
that the authors were already notified and gave permission. No further notice
or permission request is needed. No message was sent by the assistant. That
owner-confirmed private noncommercial decision and its freshly retrieved private
attestation satisfy R05 for this scope; independently inspected correspondence,
commercial/SDK/public-native grants are not claimed.

Read [the completion report](project/docs/completion-2026-10-23.md),
[LATEST.json](project/handover/LATEST.json) and
[verification](project/evidence/completion-20261023/verification.json).
**14 of 25 scoped rows are complete:** the earlier 12 host engineering rows,
D01 conditional software and R05 owner-confirmed private source use. The remaining
11 rows retain physical, precise distribution or operational criteria.
**Zero of 13 physical acceptance areas have run.** Do not turn the new tools or
synthetic cases into device passes.

Clean implementation/build commit:
`b8a5fd665076ecde1cd42c54aa232ffb757f583b`,
tree `4a6325a7b587920e52995aaaa902315999e57c6b`.
**974 strict checks pass** (913 host/source + 61 PPSSPP), with zero skips,
failures or errors against all five exact source checkouts. Independent review
verified 128 focused checks and the exact failure reproductions. A failed early
isolated-discovery run was corrected; the final strict run and CI both pass.

The original-only `smartpro-psp-0.1.0-dev12` build verifies its signature,
60-file payload, same-key determinism, installed SDL/navigation/settings/classic
smoke and fixture rollback. Both ZIPs reproduce byte for byte from the no-Git
source export. The 197-file source inventory SHA-256 is
`bd4b8affa77296a1d1583983ba1e5639e7ab4c0b623eeac842475c135923a27d`.

[CI run 39883665932](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39883665932)
passed all 974 checks on actual clean merge
`fba239bcd793000faca805fa22dacb306504bdcb`, for source head `b8a5fd6`.
[Artifact 12471113691](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39883665932/artifacts/12471113691)
was fully retrieved: 5,091,243 bytes, SHA-256
`6be0bd6d136011af623254fdc1d9b6840886a8eeb166ce07f12fb2ef5e5d75cf`.
Expiry: 21 January 2027, 01:22:56 UTC. All eight development checksums,
signature/payload and actual exported source bytes pass readback. Later
handover/documentation/evidence edits preserve these exact snapshot identities;
they do not acquire this exported-source inventory digest.

The CI evidence archive, original-only review handoff and private scoped source
candidate were also retained in owner-only Drive and freshly retrieved. All
three full archive hashes and every member pass. The private candidate applies
five patch records to 11 upstream source files, verifies the signed original
overlay, and has a separately verified source restoration with all 11 preimages.
It was never executed or installed. [Retention](project/evidence/completion-20261023/retention-readback.json)
and [private integration](project/evidence/completion-20261023/private-source-integration.json)
keep the identities separate. No private source archive, author correspondence,
SDK, native binary, signing key or owner data was committed to Git. Storage
readback is verified; permanent availability is not guaranteed.

Completed software boundaries:

- [D01 private runtime](project/docs/experimental-runtime.md) connects the existing
  source configuration, initialized owners, embedded UI, dispatcher and principal/
  resident boundary. Real host subprocess tests cover positive release, replay,
  denied writes, retained staged commands and overdue cleanup. Signed deadlines
  shorten at return-start; actual kernel `ECHILD` remains required. Interrupted
  startup/fallback health is preserved before any private view starts.
- [D02 backup payloads](project/docs/recovery-payload.md) copy selected offline
  card/save/internal file trees into new private containers, then verify retained
  and separately restored bytes. Unsupported metadata/links and partial writes
  fail without deleting uncertain owner paths. Physical coverage/recovery is unrun.
- [D05/D06/native/Resume/ports review](project/docs/qualification-review.md) adds
  scoped structured observations to the existing recorder, exact runtime/source/
  raw hashes, per-context cycle thresholds, save policy and bound reviewer
  statements. Host data cannot qualify a device or generate production profiles.
- [R06 exact review](project/docs/component-resolution-2026-10-23.md) uses freshly
  retrieved native sources/builds and SDK inputs, actual static archive selection,
  exact GCC package provenance, inline/font/SDK notices and current dev12 archive
  inventories. Public native distribution still needs its narrow remaining
  incorporated-component/source/notice decision.
- [O01/O02 handoff](project/docs/release-handoff.md) verifies independent trust/
  checksum inputs, actual signed payload/source/notices and published local bytes.
  The 14-file original-only review bundle was retained and verified again from
  retrieved storage. Operational production key custody/public device hosting
  remain open. Existing [O03 drift/maintenance work](project/docs/upstream-maintenance.md)
  stays pinned; no upstream revision changed.

## Next work when the device is available

1. D02: actual complete card/save/necessary internal backups, independent retained
   readback and physical expendable-media restore/classic recovery rehearsal.
2. D03: actual original TG5040 firmware/filesystem/runtime/writer and kernel/tool
   inventory. Do not assume a connection or authorize a firmware flash.
3. D05/D06: provide those real reviews to the completed D01 harness; run the
   bounded core casebook through existing owners, retain failures and obtain
   independent review before any narrow production configuration.
4. Qualify selected native engines, same-boot Resume or individual ports only
   under their additional scopes. Complete public distribution/key/hosting and
   maintenance requirements for the exact supported release.

The shipped `qualified_runtime.configuration()` and
`experimental_runtime.configuration()` still return `None`. Actual device
factory reviews are absent and all production/runtime/profile/source-use gates
remain false. No native candidate/upstream patch is selected in the public host
preview, and Celeste remains unselected. No physical recovery, device FPS,
battery improvement or Resume durability is established. PR #1 stays draft and
unmerged. Reuse completed R04 custody instead of rebuilding it as new progress.

All workspace/scratch paths remain temporary. The five-source/venv/SDL_image
setup in LATEST and the historical sections remains valid. Current scratch
outputs use `/workspace/scratch/trimui-dev12-*`. Continue from the versioned
receipts; do not send another author notice or ask the busy owner to repeat
permission already given.

---

## Historical dev11 continuation, before the completion work and owner permission update

The requested batch adds **10 host engineering items** across D01, D03, R06, O01 and O03. Read [the item register](project/docs/continuation-2026-10-23.md), [LATEST.json](project/handover/LATEST.json) and [the master plan](project/docs/master-plan-2026-10-22.md). These are portions of five open plan rows. **12 of 25 host tasks remain complete; zero of 13 physical areas have run.** Do not count the ten items as ten additional completed plan rows.

Clean source/build commit: `0585e1de62b1e38b291a96eed7793464c4f272e1`. Strict local checks pass **833 tests** (772 host/source + 61 PPSSPP), with zero skips, failures or errors against all five exact source checkouts. The original-only `smartpro-psp-0.1.0-dev11` build verifies its signature, 59-file payload, same-key determinism, installed SDL/navigation/settings smoke and fixture rollback. Both ZIPs reproduce byte for byte from the no-Git export. Its 177-file source inventory SHA-256 is `179b85ec30396c3031431fe59da0a588fe9311d717f8350c622c994e2ca04df9`. Later handover/evidence edits retain this exact snapshot; they do not acquire its source-inventory identity.

[CI run 39877124999](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39877124999) **passed all 833 checks** on actual clean merge checkout `71d2c19dcdaa78782ccfaa98c464801c00dd98a5`, for source head `0585e1de62b1e38b291a96eed7793464c4f272e1`. [Artifact 12469330647](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39877124999/artifacts/12469330647), 4,970,680 bytes, SHA-256 `7e6cbbf345417d97f2390ae424a285001f943de75fa4f5284e60ef08428f1110`, was completely retrieved. All eight inner checksums, development signature/payload and actual 177-file source export pass readback. Expiry: 21 January 2027, 00:16:26 UTC. [Readback receipt](project/evidence/continuation-20261023/ci-readback.json) records the exact scope; permanent private retention was not performed. See [verification](project/evidence/continuation-20261023/verification.json), [local certification](project/evidence/continuation-20261023/certification.json) and [build report](project/evidence/continuation-20261023/build-report.json).

New engineering boundaries:

- [Host admission and journal](project/docs/experimental-admission-host.md): independent hashes, boot/principal identities, one-shot expiry, view-only actions, cooperative return and durable redacted evidence. The factory admits synthetic host cases only. Fixed device entry and real action wiring remain absent.
- [Principal observations](project/docs/principal-deadlines.md): timeout keeps descendant ownership through actual `ECHILD`, then refuses completion. The optional policy is not selected by shipped runtime configuration.
- [D03 probe](project/docs/device-probe.md): read-only copied-root or explicitly selected live-host metadata, exact tool/helper identities and isolated kernel probes. A host helper cannot prove target support.
- [R06 audit](project/docs/component-audit.md): joins component/custody/source/patch identities and retains seven primary-file notice observations. Recipe/IGM/SDK and distribution review remain open.
- [Key rehearsal](project/docs/trust-rehearsal.md) uses disposable keys and existing package APIs; operational custody remains open. [Upstream review](project/docs/upstream-maintenance.md) queues 230 in-scope and 374 outside-scope changes from the previously inspected Development revision. No pin was updated.

## Next work and unchanged limits

1. D01: bind the reviewed policy and bounded stop requests at the fixed principal/embedded device entries; prove actual action restrictions and fail-closed return. The host helpers alone cannot admit hardware.
2. D02/D03: when the original TG5040 and operator are available, complete actual card/save/necessary internal backups, retained retrieval and restoration rehearsal, then observe the real firmware/filesystem/runtime/writers and kernel/tool identities.
3. R05/R06: retain actual notification delivery/scope evidence and finish exact selected component permissions/source/notices. The PyUI notice remains **unsent**; no instruction authorizes contacting anyone. Native use must bind the existing exact retained R04 set.
4. O01/O03: establish actual key custody/recovery and a maintenance owner; review each upstream change and qualify the supported scope after the first pilot.

No device was connected or probed, emulator executed, firmware changed or owner data edited. All production/profile/runtime/source-use gates stay false; selected upstream patches/native binaries remain empty and Celeste remains unselected. No physical recovery, device performance/battery gain or Resume durability result is established. Reuse R04 receipts; do not rebuild completed native custody as new work.

The existing five-source setup under “Verification and workspace continuity” below remains valid. Current local build/export paths use `/workspace/scratch/trimui-dev11-*`; all are temporary. Resume from the versioned handover and exact receipts.

---

## Historical dev10 checkpoint, 22 October 2026

Checkpoint: 22 October 2026. Active branch: **`build/spruce-psp-experience`** in `daniel1990000/CrossMix-OS-project`; [PR #1](https://github.com/daniel1990000/CrossMix-OS-project/pull/1) remains draft and unmerged. Active code is `project/` for the original TG5040 on pinned spruceOS v4.5.4/PyUI. The CrossMix/C++ material and prior checkpoint next-work suggestions are historical.

## Start the next chat here

Read [LATEST.json](project/handover/LATEST.json), [the continuation prompt](NEXT_CHAT_PROMPT.txt), [README](project/README.md) and [master plan](project/docs/master-plan-2026-10-22.md). **12 of 25 tasks are complete as host engineering:** R01–R04, U01–U04, D04, P01–P03. **Zero of 13 physical areas have run.** R04 is newly complete; do not repeat the prior five-task batch or native rebuilds as new work.

**R04:** both native replacements were completely cross-built, paired with actual matching source/build archives, independently reviewed, privately retained and freshly retrieved. All seven native/compiler artifacts, 18 owner-only Drive parts and full reassembled hashes pass. The original dev9 and handover host artifacts are also retained and retrieved; the new dev10 CI archive has its own receipt. See [custody/recovery](project/docs/artifact-custody.md), [native rebuild](project/evidence/artifact-custody/native-rebuild.json), [independent source review](project/evidence/artifact-custody/native-source-review.json) and [private retrieval index](project/evidence/artifact-custody/native-retention.json).

| Current dev10 item | Exact identity/evidence |
|---|---|
| Clean local source/build | `a0e6f8af7fe3354c1c82a662b3969e2824717bf3` |
| Source head certified by CI | `a0e6f8af7fe3354c1c82a662b3969e2824717bf3` |
| Clean PR merge actually built by CI | `1609c5358ee04010f8e5e873064d53e5fc03eccc` |
| Strict host/source checks | **710 passed**, 649 host/source + 61 PPSSPP; zero skips/failures/errors/expected failures/unexpected successes |
| CI | [Run 39871706495](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39871706495), success; [download/readback receipt](project/evidence/device-preparation/ci-readback.json) |
| Deliverable | `smartpro-psp-0.1.0-dev10`, original-only host preview; selected patches/native binaries empty |
| Original-source inventory | 158 files, SHA-256 `f05a5036a04fa3291bfb230b68c81a853096d1d6143d93504288ec53d2f9789d`; signed payload 57 files |

[Dev10 CI artifact](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39871706495/artifacts/12466212738) ID `12466212738` is 4,882,634 bytes, outer SHA-256 `9a6c7650bd49bfa2ed868ac57e656d7224968de98c438b5be2f60cc752d91305`; expiry **20 January 2027, 23:25:44 UTC**. The complete artifact and all eight inner checksums, development signature/payload and actual exported source bytes were verified. It was privately retained in Drive and freshly retrieved with the same hash. The source-inventory digest above is a different digest. Local packaging passes same-key rebuilds, installed-payload SDL/navigation/settings smoke and fixture rollback; its no-Git export reproduces both ZIPs byte for byte. The generated signer was deleted. A new signer changes signed bytes. See [verification](project/evidence/device-preparation/verification.json).

New private binaries: PPSSPP **19,934,560 bytes**, SHA-256 `f65f88f15ea415399f16f7b53fcfc254efbb822c52379760ba77e39cf3d05773` (16-object SDK audit); RetroArch/IGM **15,182,848 bytes**, SHA-256 `26324b64ec0adb9bde359291f1c2fb396a629a53259a5afdc00bf46650cab349` (23-object SDK audit). They were never executed. Historical `a93f7d…`/`118146…` binaries were not recovered. Both new builds use image `sha256:15ef8c75094bd51d1116ad4218846b6949821f545c053ddda89b8bfbba85f51b`. The repository RA lock keeps the old image; a separately retained build context changes only its image pin. Recover the new context/image from the native receipt instead of silently changing the historical lock. The private SDK image's saved blobs/config are verified; Docker-save outer bytes were not deterministic and restore into an empty daemon was not exercised.

**D01 design is prepared, not implemented:** [trusted route](project/docs/experimental-device-route.md) identifies exact candidate/owner admission, bounded observation/stop requests and recovery. The current shipped entry returns unavailable, and existing descendant wait is unbounded. No card JSON/flag or report grants production qualification. **D02/D03 preparation is ready:** [read-only verifier and operator procedure](project/docs/device-recovery-preflight.md), 20 focused tests and [independent review](project/evidence/device-preparation/review.json). Review found and fixed internal-root metadata, interscan rename and failed-fsync publication gaps. This tool does not copy/restore files or prove physical backup coverage. **R06** now has a [16-scope component ledger](project/docs/native-component-ledger.json); actual FFmpeg IJG link membership/credit is retained, but exact recipe/IGM/SDK grants and remaining source/notices remain open.

Next work:

1. **D02 physical recovery:** complete actual card/save/necessary internal-file payloads, retained readback and restoration rehearsal on expendable media. Overlay rollback, card restoration and internal launcher/FN scene recovery stay separate.
2. **D03 actual inventory after D02:** observed original TG5040 firmware/filesystem/runtime/loader/writers, kernel APIs, process identity and trusted tools. Firmware 1.1.1/FAT32 remains proposed, not observed or permission to flash.
3. **D01 implementation/pilot:** implement and review the designed admission/stop behavior without weakening shipped gates. Activation needs actual R05 evidence and D02/D03 readiness; native admissions bind the exact retained R04 artifacts.
4. **R05/R06 external/component evidence:** the PyUI notice is UNSENT; no send instruction exists. Do not contact anyone. Notification and commercial permission are separate. Continue independent engineering/review meanwhile.

No device was connected or probed. All production/profile/runtime/source-use gates remain false; optional Celeste remains unselected, installed engines and owner data unchanged. No device-ready image, performance/battery benefit, real recovery, physical save paths or same-boot Resume durability is established. PR #1 stays draft/unmerged.

## Current workspace and continuity

The clean source checkout is `/workspace/CrossMix-OS-project`. The five pinned reference roots, isolated Python/SDL dependencies and strict command under [verification and workspace continuity](#verification-and-workspace-continuity) below remain current; native/scratch paths in older snapshots are historical. Current local dev10 output is `/workspace/scratch/trimui-dev10-clean-development`, no-Git export/rebuild under `/workspace/scratch/trimui-dev10-source-export` and `/workspace/scratch/trimui-dev10-source-rebuild`. New native scratch is `/workspace/scratch/trimui-native-r04`. All are ephemeral. Recover durable host/native bytes using their private file IDs, part order and exact hashes in the versioned receipts. Never copy full native/source/SDK archives, owner data or private keys into Git or host preview artifacts.

This continuation's later handover/evidence commits do not inherit the exact CI identity above. The historical snapshots below retain their own counts, release IDs, hashes, temporary paths and next-work suggestions; use the current section and LATEST.json first.

## Historical dev9 handover snapshot

The handover records the completed host work and the remaining device and release work. Read the [current status record](project/handover/LATEST.json), [continuation prompt](NEXT_CHAT_PROMPT.txt), [project README](project/README.md) and [master-plan register](project/docs/master-plan-2026-10-22.md). Resume from the register; do not repeat completed batches or restart the historical CrossMix/C++ plan.

**11 of 25 tasks are complete as host engineering work:** R01–R03, U01–U04, D04 and P01–P03. The latest requested five were U04, D04, P01, P02 and P03. The other 14 tasks remain open. **Zero of 13 physical acceptance areas have been run.** The owner confirmed an original TG5040 exists on 22 October, but it was unavailable for testing that day; actual firmware, filesystem and installed runtime identities remain unknown.

| Verified item | Exact evidence |
|---|---|
| Runtime implementation and clean local dev9 build | `02999f4aa16b08c028e61861b8721c3905b7086e` |
| Source branch head used by verified CI | `e030677199884441096d90382121b86cfef81796` |
| Clean PR merge checkout actually built by CI | `6b4b59cfbdb0597c0dd2c23dea5d904256eeda70` |
| Strict local and CI checks | **690 passed**, 629 host/source + 61 PPSSPP; zero skips, failures, errors, expected failures or unexpected successes |
| CI result | [Run 39864873828](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39864873828), successful; [download readback receipt](project/evidence/host-batch3/ci-readback.json), [actual certification](project/evidence/host-batch3/ci-certification.json) and [build report](project/evidence/host-batch3/ci-build-report.json) |
| Deliverable | `smartpro-psp-0.1.0-dev9`, original-only host preview; selected upstream patches and native binaries are empty |

The [verified CI artifact](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39864873828/artifacts/12463233054) is `host-preview-evidence`, ID `12463233054`, 4,836,083 bytes, SHA-256 `a8cfc638853f2030fc5e6561a74bdd80ba9e44c1ab47c8085bc5272e8d29b03e`. GitHub lists expiry as **20 January 2027, 22:25:40 UTC**; retention is not permanent custody. The complete downloaded ZIP, all eight inner checksums, changed runtime bytes, development signature and 57-file payload inventory were verified. The [150-file original-source inventory](project/evidence/host-batch3/ci-release-source.json) has SHA-256 `627251e9c22a6b37740b8d3bfd223540969806c4add1deaf33ba6e19402385eb`; this is a different digest from the outer artifact. Development signing establishes package integrity, not production trust.

This handover adds documentation and evidence after that verified snapshot. It does not claim CI tested a future documentation commit. The historical dev9 receipts retain their exact build identities; compare the recorded source inventory before reusing them for a later revision. See [current setup and workspace recovery](#verification-and-workspace-continuity) below.

Next work, in dependency order:

1. **R04:** retrieve and hash-check, or rebuild, the exact private native binaries with matching source/build archives; prove retrieval from retained storage. Retain the original-only host preview before expiry. A GitHub host artifact does not recover the earlier private native outputs.
2. **D01:** design the trusted private experimental harness/manual route, bounded exit, candidate identity and recovery. Design can proceed now; derivative assembly/activation requires R05 evidence, and native candidate use also requires R04. Editable card JSON or a flag must never grant production qualification.
3. **D02:** prepare and then perform verified card/save/necessary internal-file backups and restore rehearsal on expendable media. Overlay rollback, whole-card restore and internal startup/scene recovery are separate procedures.
4. **D03:** after D02, record actual TG5040 firmware/filesystem/runtime, kernel APIs, process identity and probe tools. Firmware 1.1.1/FAT32 is a proposed qualification matrix, not an observation of the owner's device or authorization to flash it.

**R05** actual PyUI notice delivery/scope evidence and **R06** exact native component/recipe/IGM/SDK terms and corresponding-source review remain open. The notice draft is unsent; no author contact has been authorized. Continue independent preparation while these or hardware are unavailable. PR #1 remains draft and unmerged. Production/device/runtime/source-use gates remain false; no emulator replacement, owner-data change, public device image or release tag has been performed. The optional Celeste patch is unselected, and all port save paths still require physical verification.

## Five-task batch U04 / D04 / P01–P03 — 22 October 2026

All five requested tasks are complete as host engineering work. The [master plan](project/docs/master-plan-2026-10-22.md) now records 11 of 25 tasks complete. See [the exact batch evidence](project/evidence/host-batch3/verification.json), [measurement methods](project/docs/host-measurement.md) and [port preparation/save contracts](project/docs/ports-preparation-and-saves.md).

U04 adds a synthetic 10,000-entry corpus, complete pagination/focus/Unicode checks and a bounded live model cache cleared on explicit refresh. The unchanged baseline rebuilt every entry for every query (~6 seconds on this host); corrected warm page/search queries are in tens of milliseconds. These are synthetic host workloads, not device gains. Empty files remain review-only and malformed individual entries do not hide valid games. Existing upstream managers, preset conventions and execution ownership remain intact.

D04 records real standalone SDL presentation-return timings, separate render/present durations, bounded samples and fixed navigation scenes. The read-only PID sampler now records child CPU and optional PSS while retaining identity and truncation limits. Physical video/audio/energy methods are specified separately; unmeasured hardware metrics remain unavailable.

P01 inspects the actual PortMaster package/class/registration, legacy marker and pending self-updates without executing them. Sonic includes Game.so/libogg; helpers, local libraries and managed Mono are inventoried. P02 reproduces Celeste's false success and checks the exact optional fix against pinned source, with failed repack/mount/bind/full-storage, retry, cleanup and pipeline failure fixtures. P03 distinguishes generated Render96 resources from a consumed input ROM and keeps Celeste owner files mandatory. Scoped external save backups, reviewed transactional restores and undo preserve unlisted slots. All save paths still need physical readback before uninstall; the inventory tool never deletes ports.

The full strict run passes **690 checks** (629 host/source + 61 PPSSPP), with zero skips, failures, errors or expected failures. Certification and CI now require **five** untouched pinned checkouts: SPRUCE_SOURCE_ROOT, PPSSPP_SOURCE_ROOT, SPRUCE_RA_SOURCE_ROOT, PORTS_SOURCE_ROOT and PORTMASTER_SOURCE_ROOT. The first full attempt caught a refresh regression in retained model bindings; its failed result is retained separately. The original assertion was preserved and the corrected implementation passes.

The descriptor selects **dev9**, an original-only host preview. The optional Celeste source diff remains unselected, all runtime/rights/device flags remain false, all 13 physical acceptance areas remain unrun, installed engines/owner data are unchanged, and PR #1 stays draft and unmerged. Next: R04 artifact custody, D01 experimental-route design and D02/D03 operator preparation, alongside actual R05/R06 evidence. No author communication is authorized by this continuation.

Implementation [`02999f4`](https://github.com/daniel1990000/CrossMix-OS-project/commit/02999f4aa16b08c028e61861b8721c3905b7086e) is the clean local dev9 build source. The signed package passes inventory/signature checks, same-key deterministic rebuilds, installed-payload rendering/settings/navigation smoke and fixture rollback. Rebuilding the exported source without Git produces byte-identical preview/source ZIPs. All eight artifact checksums and both changed runtime modules were read back. Local artifacts: `/workspace/scratch/trimui-host-batch3-dev9`; durable hashes and reports are in the batch evidence.

## Earlier checkpoint ledger

The checkpoint summaries below retain their original counts, release IDs and temporary paths. Their suggested batches are historical; use the current status and next steps above. Current setup instructions appear under “Verification and workspace continuity.”

## Interface batch U01–U03 — 22 October 2026

The next three [master-plan](project/docs/master-plan-2026-10-22.md) tasks are complete as host engineering work. PNG, JPEG, BMP, static WebP and QOI now work through both decode paths. An original bounded QOI decoder avoids a new device dependency. Header checks bound native decoder allocation; malformed/oversize data and missing codecs produce the existing placeholder. [Format evidence and limits](project/docs/artwork-formats.md) distinguish actual host codec tests from untested target libraries.

**Games → Refresh library**, also available through F5, invalidates source metadata and positive/negative artwork caches. Refresh preserves the page and focused game or nearest surviving neighbor, clamps a removed page, and rejects stale asynchronous completions. Live integration retains initialized PyUI managers and the existing scanner/launch authorities.

The keyboard now has 50 keys, title punctuation and wide action keys. Text, field, actions and controller help scale through 1.75. Physical hints follow South/East Confirm and show Cancel/Delete/Find; long text shows its suffix and end cursor. The standalone preview's external Unicode input stays bounded to 128 code points. Embedded text entry follows the existing PyUI input route, including remapped buttons. [Accessibility notes](project/docs/interface-accessibility.md) define entry, deletion and font limits. The new `ui/keyboard.py` is mandatory in the signed source inventory.

The full local strict run passes **621 checks**: 560 host/source and 61 PPSSPP, with zero skips, failures, errors or expected failures. This includes 40 new format, refresh and keyboard checks, including the actual embedded input route under both Confirm conventions and inverse button remaps. [Normal keyboard](project/evidence/ui-polish/keyboard.png), [maximum-size keyboard](project/evidence/ui-polish/keyboard-large.png) and [QOI cover](project/evidence/ui-polish/artwork.png) captures are actual SDL host renders with original synthetic data. The capture script and [verification record](project/evidence/ui-polish/verification.json) are retained.

A preceding full run passed 620 of 621 checks and failed while waiting for a test orphan to publish its PID. The unchanged test passed all 20 predetermined diagnostic attempts, and a controlled 3.25-second setup delay reproduced the same three-second readiness failure. The fixture now publishes readiness atomically and waits with a six-second deadline and helper-liveness checks; production ownership logic and assertions are unchanged. All 21 synchronized diagnostic attempts and the 21-test principal suite pass. The failed certification is retained separately; the original host delay was not conclusively located.

The descriptor now selects **dev8**. Development artifacts at `/workspace/scratch/trimui-interface-dev8` pass signature/inventory verification, same-key deterministic rebuilding, installed-payload rendering/settings/navigation smoke and fixture activation/rollback. The no-Git source export reproduces the preview and source ZIPs byte for byte. All artifact checksums, changed runtime bytes and retained MIT/OFL notices were read back. The host uses Pillow 11.1.0 and isolated SDL_image 2.8.8. No device runtime library, installed engine or qualification gate changed; all 13 physical areas remain unrun. Source-use/distribution evidence and private native artifact custody remain open; PR #1 stays draft and unmerged.

Implementation [`c42c003`](https://github.com/daniel1990000/CrossMix-OS-project/commit/c42c003a147c614788c1e22b58be3e573f6901a3) passes [GitHub CI run 39858609637](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39858609637): all **621 checks**, zero skips/failures/errors/expected failures, dev8 packaging and upload. The clean PR merge checkout is `77b26c92b1dece2e114aa2097aef3b461b58b73c`; signed metadata records that identity. [Download host-preview-evidence](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39858609637/artifacts/12460398356), artifact ID `12460398356`, SHA-256 `6f01d358a84bcce58bd88fdf4bd6fca531e06d2a258c29c5182ef4c0966e8aea`. The complete download and all eight inner artifact checksums were verified; the source inventory matches the local build. Later evidence/handover text changes preserve the tested implementation hashes and packaged source inventory.

At that checkpoint the suggested next group was **U04** large-library fixtures, **D04** measurement tooling and **P01** port dependency inventory. Those tasks are now complete above; physical qualification remains a separate stage.

## Previous release tooling batch R01–R03 — 22 October 2026

The first three tasks in the [master plan](project/docs/master-plan-2026-10-22.md) are complete. The inherited CrossMix release workflow is archived byte for byte in `docs/historical/`, outside Actions discovery. The remaining host workflow has read-only repository permissions and no tag/release trigger; release tags must use a revision containing this isolation change.

`project/dev/check.sh` now requires all three explicit pinned source roots. Certification checks their commits and materialized bytes before and after testing, rejects skipped/empty/incomplete suites and expected failures, and writes actual counts/identities to `dist/certification.json`. CI watches `docs/spruce-source-lock.json` and uploads failure records.

At this checkpoint `project/packaging/current-release.json` selected **dev7**. CLI and CI use the descriptor by default. Signed metadata and the build report record the exact frontend commit, modified-source status and a SHA-256 inventory. Exported original source retains that provenance and rejects changed bytes when rebuilding. Native binary hashes are historical references only; no upstream patch or native binary is selected.

The complete local certification passes **581 checks**: 520 host/source and 61 PPSSPP, with zero skips, failures, errors or expected failures. The unchanged baseline also passed all 561 checks in this workspace. See [batch evidence](project/evidence/release-tooling-batch1.json) for the actual certification and development package results. This session validates host behavior; all 13 physical acceptance areas remain unrun.

Implementation [`9a8e772`](https://github.com/daniel1990000/CrossMix-OS-project/commit/9a8e77232cd2b6908c4e5cae17312e4a2d942068) passes [GitHub CI run 39853492605](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39853492605): all **581 checks**, zero skips/failures/errors/expected failures, dev7 packaging and upload. GitHub tested its clean PR merge checkout `b31f7e4d96bb7a6bf33b286d9f6e3699a11469dc`; the signed package records that exact frontend identity. [Download host-preview-evidence](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39853492605/artifacts/12457629490), artifact ID `12457629490`, SHA-256 `d37d8396fe7dd5ac060dd65faccee9fc020b422b1b580588340f3a57c0a7ee9b`. The complete download and all inner artifact checksums were verified. Local no-Git export rebuilds reproduce the preview and source ZIPs exactly. Later evidence/handover/master-plan text changes preserve the tested implementation hashes.

At this earlier checkpoint the suggested batch was **U01–U03**, now completed above. R04 artifact custody, device preparation and external source-use/distribution evidence remain open. Keep PR #1 draft and unmerged. These prior private artifacts are under `/workspace/scratch/trimui-release-tooling-dev7`; they may need rebuilding after environment replacement.

## Inherited integration checkpoint

The current checkpoint completes the host software integration, common settings, PPSSPP state protocol/Resume route, native menu extensions, source composition/restoration tools and private source builds. Read the final records in [project/evidence](project/evidence/) for actual host counts, build fingerprints and development packaging results. Host fixtures, complete native cross-builds and physical qualification remain separate claims.

The inherited software checkpoint passed **527 host checks with zero skips or failures**: 466 Python/SDL/source-integration checks and 61 PPSSPP C++/build-tool checks. The **dev4** original-only development artifacts pass signature/inventory verification, deterministic rebuilds, installed-payload rendering and fixture activation/rollback.

**On 22 October 2026, the owner confirmed an original Smart Pro is available, but not for testing that day.** Physical acceptance has not been performed. PyUI notification delivery and exact recipe/SDK redistribution review remain open. Installed emulators are unchanged; runtime/profile activation stays disabled, and engine binaries/full recipe archives stay private.

## Latest source study and menu polish — 22 October 2026

Implementation: [`8768ab0`](https://github.com/daniel1990000/CrossMix-OS-project/commit/8768ab042da2c89c0087d068453bfd58f68445f5). The complete local run passes **561 checks** (500 host/source and 61 PPSSPP), with zero skips, failures or errors. Exact-commit [GitHub Actions run 39822730380](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39822730380) also passes all **561 checks**, with zero skips/failures/errors, dev6 packaging and artifact upload. [Download the current host-preview-evidence](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39822730380/artifacts/12445751282), artifact ID `12445751282`, SHA256 `764c8ed367185094a3c876a926c67869da4aa5eb80e4fc7fcac8f410265556ed`. Subsequent handover/evidence-only commits do not change this tested implementation.

The owner asked for deeper study of the three supplied repositories. The [source study](project/docs/psp-source-study.md) and exact-file traces cover their active menu/navigation/text/artwork paths; this is not a whole-repository audit or binary-decompilation claim. Source-backed fixes now snap pagination/reordered rows correctly, retain the nearest row after a Favorite disappears, explicitly reset newly opened Settings views, reuse glyph textures across tint/shadow/alpha changes, and mark repeated/blank paragraph overflow correctly. Options titles use two measured lines, with full overflow titles retained in message pages.

Review the fresh [home](project/evidence/source-study/home.png), [library](project/evidence/source-study/library.png), [long-title options](project/evidence/source-study/options.png) and [maximum-text options](project/evidence/source-study/large-text-options.png). These are actual SDL host captures with original synthetic metadata and the actual host clock. The capture script is included. The original [Sony PSP comparison](project/evidence/psp-design/comparison.png) remains available for the unchanged overall composition.

The deterministic glyph probe drops raster/uploads from **165 to 1** and cached data from **7,470,540 to 45,276 bytes** for 100 alpha changes of one text shape. These are host scenario counts, not whole-application/device measurements. The original-only **dev6** package at `/workspace/scratch/trimui-deep-study-development-final` passes signed inventory verification, deterministic rebuilds, installed-payload rendering/settings/navigation smoke and fixture rollback. Overlay SHA256: `11e97ec0b974707e782d518dfd1542a841c9f02680a3e4fac48f6d63deab52e4`; all published checksums and the three changed runtime modules were read back. See [verification](project/evidence/source-study/verification.json).

The first full run exposed a cross-view focus regression and a preexisting fake-readiness ordering race. New-view focus is now explicit; an existing principal-shell fixture waits for its actual resident-start marker with a deadline. Production principal behavior and exact assertions remain unchanged. The failed run is retained outside the passing count; 20 repeated readiness cases and all 21 principal checks pass. No emulator binary, shipped activation gate or owner data changed. Physical TG5040 acceptance and prior external release evidence remain open; PR #1 stays draft and unmerged.

## Classic PSP visual overhaul — 22 October 2026

Verified implementation: [`86509e1`](https://github.com/daniel1990000/CrossMix-OS-project/commit/86509e12ccccc3df4d69c95257efabb294752f03). [GitHub Actions run 39818966902](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39818966902) passes all **542 checks** (481 host/source and 61 PPSSPP), with zero skips/failures/errors, dev5 packaging and artifact upload. [Download the current host-preview-evidence](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39818966902/artifacts/12443392152), artifact ID `12443392152`, SHA256 `0da80fe550c8ab7829952798a88f9c766a42757e60303b67b807be0e1acb0b32`. Subsequent screenshot/evidence/handover-only commits do not change this tested implementation.

The frontend now follows the original PSP XMB composition: anchored horizontal categories, a vertical item column, selected-only category labels, original white pictograms, a brighter blue color field, two broad wave surfaces, flat options and a clean keyboard workspace. The actual coordinator clock appears at top right. Cover loading now handles queue pressure, cache eviction and reduced-motion completion reliably. SDL version/backend fallbacks retain the existing graphics runtime.

The owner explicitly requested use of PPSSPP, JohnnyCollado/PlayFieldPortal and sashkinbro/EmuCoreA. Their exact revisions and applied layout/motion/cover/native-theme decisions are in [visual design notes](project/docs/psp-visual-design.md). The PPSSPP palette matches the azure frontend through supported native fields; gameplay/config authority and native layouts remain with their existing owners.

Review the [new screens](project/evidence/psp-design/gallery.png), [actual Sony PSP comparison](project/evidence/psp-design/comparison.png), [individual home capture](project/evidence/psp-design/home.png) and [verification record](project/evidence/psp-design/verification.json). Captures are SDL host renders, not physical-device photos. The Sony reference is comparison evidence outside the development payload.

Local validation passed all 479 host/source and 61 PPSSPP checks with zero skips/failures/errors, followed by all 44 final UI checks and 40 final principal/source-binding/release checks. The two added rendering cases cover the clean keyboard and older/unsupported SDL paths. The dev5 original-only package passes signature/inventory, deterministic rebuilds, installed-payload smoke and fixture rollback. The final exact-code CI run also passes all 542 checks. Physical TG5040 acceptance and previously recorded external release evidence remain open; no installed emulator or activation gate changed. Both new rendering modules are now mandatory in the verified module inventory. A preexisting CI race fixture was made deterministic by serializing only its real preflight health reads; production locks and exact one-use consumption assertions are unchanged. The final dev5 package is at `/workspace/scratch/trimui-design-development-final`.

## Continuation — 22 October 2026

The acceptance recorder now retains a selected save that disappears after the baseline as explicit `missing=true`, `unchanged=false` evidence, including a missing save directory. It never recreates or restores that save. Reports expose the comparison; baseline saves remain mandatory, and symlinks/special files/inconsistent observations still fail collection. Five regression tests cover these cases.

Support export now redacts whole strings containing ROM/save paths and path-keyed entries, preventing filename fragments with spaces, quotes or newlines from leaking. Two regression tests cover structured and raw diagnostics. Unrelated structured status fields remain available; a plain-text log containing a private path can be redacted entirely.

The [continuation rights review](project/docs/continuation-rights-review.md) records exact outstanding evidence and absent historical private artifacts. No device was attached or tested, no notification was sent, and no gate, installed emulator or owner save changed. Private native binaries/source archives must be recovered and hash-verified or rebuilt before use; historical SDK audit results have not been rerun here.

Local validation: 21 acceptance tests and 13 inventory/support tests pass. The full host run attempted all 473 tests, with 14 failures and 22 errors in process-identity/lifecycle tests in this sandbox: Python's PID differs from `/proc/self` and `/proc/<pid>/stat` is absent. This is not a full passing run. Do not weaken identity checks or count those failures as skips. The continuation passes all **534 checks in GitHub CI** (473 host/source and 61 PPSSPP), with zero skips/failures/errors; see the exact commit and run below. Original-only development packaging passed signature/inventory, deterministic rebuild, installed-payload smoke and fixture rollback at `/workspace/scratch/08e013647ad3/development-continuation`.

The recreated private source-review kit is `/workspace/scratch/08e013647ad3/source-review-continuation`; verification with the external development public key passed. The fresh `/workspace/scratch/08e013647ad3/device-acceptance-ready` session has all 13 areas `not_run`. These paths are temporary workspace outputs, not a claim that previous private native archives survived. See [continuation evidence](project/evidence/continuation-acceptance-hardening.json).

## Previous verified checkpoint — acceptance hardening

- Implementation commit: [`37c330c6ebf8dd2e846003ee072eb2e0cf7f1bb1`](https://github.com/daniel1990000/CrossMix-OS-project/commit/37c330c6ebf8dd2e846003ee072eb2e0cf7f1bb1).
- [GitHub Actions run 39812635602](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39812635602): **success**, all **534 checks**, zero skips/failures/errors, development packaging and artifact upload. Host job `119942691297` reports 473 and 61 tests.
- [Updated original-only development artifact](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39812635602/artifacts/12441400284): ID `12441400284`, SHA256 `4fa98d8ec5d17850e885122adaf851e31a675cc574666d25a75b3ab5ddcfbc91`. No native engine/SDK binary is included. Later evidence/handover-only commits do not change the tested implementation.
- PR #1 remains draft and unmerged. Next milestone: original-device acceptance and actual source-use/distribution evidence, not additional host tests as a proxy.

## Inherited build checkpoint

- Software/build commit: [`42c83f699225a57251e9322f351fbda72c053830`](https://github.com/daniel1990000/CrossMix-OS-project/commit/42c83f699225a57251e9322f351fbda72c053830).
- [GitHub Actions run 39810880610](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39810880610): **success**, including all 527 checks, development packaging and artifact upload. Host job `119936465324` reports 466 and 61 tests, with zero skips.
- [Download `host-preview-evidence`](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39810880610/artifacts/12440875335), artifact ID `12440875335`, SHA256 `53f50c8691d8059baa5884b146f60a7fef41e0dccd31b1e09d55fafce29bf200`. It contains the original-only preview, scoped dev4 overlay, original source ZIP, checksums and build report. No native engine or SDK binary is included. GitHub currently lists expiry as 20 January 2027; rebuild from source if unavailable.
- [Draft PR #1](https://github.com/daniel1990000/CrossMix-OS-project/pull/1) records final scope, validation and remaining external evidence. It is open and unmerged.
- [Next-chat prompt](NEXT_CHAT_PROMPT.txt) is ready to paste into a new chat. Documentation-only commits after the software SHA above do not change the tested code; run the checks again after implementation changes.

## User direction and start point

Build a polished PSP-inspired whole-system experience for the **original TrimUI Smart Pro TG5040**, extending spruceOS v4.5.4 and its shipped PyUI. Retain existing device support, emulators, settings, games and saves. Reuse maintained projects, research beyond supplied links, work autonomously with parallel agents, and retain implementation/evidence/handovers in GitHub. Do not resume the superseded CrossMix/C++ runtime architecture.

Read [project/README.md](project/README.md), the active part of [TRIMUI_PLAN.md](TRIMUI_PLAN.md), [coverage](project/docs/feature-coverage.md), [binding](project/bridge/README.md), [state integration](project/ppsspp/state-session.md) and [release qualification](project/docs/release-qualification.md). Review PR checks at the exact branch SHA; a previous green run does not cover later edits. Keep the PR draft until the device and release evidence is available.

A lightweight checkout avoids the large historical payload:

```sh
git clone --filter=blob:none --sparse --branch build/spruce-psp-experience https://github.com/daniel1990000/CrossMix-OS-project.git trimui
cd trimui
git sparse-checkout set --no-cone /project/ /.github/workflows/ /docs/ /HANDOVER.md /NEXT_CHAT_PROMPT.txt /AGENTS.md /TRIMUI_PLAN.md /README.md /.gitignore /.gitattributes
```

## Implemented source

| Path | Current behavior |
|---|---|
| `project/psp_shell/ui/`, `app.py` | Original SDL interface, four categories, library/search/favorites, dialogs, accessibility, waves, original assets and headless/desktop preview. Checkpoint verification times appear only from authenticated backend records. |
| `project/psp_shell/adapters/spruce.py`, `library.py` | Read-only source snapshots or already initialized PyUI models, existing platform/preset filtering, exact ROM identity and token-bound original callbacks. |
| `project/bridge/process_source.py`, `principal.py`, `principal_integration.py` | Exact-source initialized model/menu/game/principal seams; Linux child-subreaper ownership including double-fork/setsid descendants; sealed staged commands preserving `$0`; correlated foreground completion. Fixed `qualified_runtime.py` defaults to `None`. |
| `project/psp_shell/hardware_settings.py`, `embedded.py` | Common brightness/volume/radio controls through existing initialized authorities, shared writer window, stale previews and configuration readback; fixed Wi-Fi/Bluetooth/controller/power/USB/apps/collections/advanced/per-game routes. Source menus retain their own layouts and hardware behavior. |
| `project/psp_shell/controls.py`, `ppsspp.py` | Separate frontend/game/menu policies, standard RetroArch and spruce IGM adapters; one PPSSPP controls/appearance transaction with five-file journal, stopped-writer checks, verified per-game override inventory, recovery and protected Undo. |
| `project/psp_shell/state_evidence.py` | Private session creation by the principal owner, exact native save/load validation, independently stopped writers and boot-bound authenticated capability transfer to fresh UI processes. Typed Resume uses the original game callback; arbitrary card JSON cannot grant it. |
| `project/ppsspp/` | Pinned native controls, completion API, private session protocol and checked save-and-quit patches; real C++ source acceptance; full PPSSPP/FFmpeg candidate build, ABI audit and retained corresponding-source tooling. Separate GPL scope. |
| `project/retroarch/` | Actual spruce IGM independent raw Confirm/Back extension, source parser/action acceptance, source locks/notices and full original-TG5040 candidate builder. Separate GPL scope. |
| `project/patches/`, `integration/` | Four reliability fixes plus separately selected PPSSPP wrapper forwarding; exact source inventory, original overlay verification, all-or-none private composition, signed expanded-module binding and exact-preimage restoration to a new output. No live installation command. |
| `project/psp_shell/ports.py`, `profiles/ports*` | Pinned launch-script/metadata contracts, owner-data import/staging/backup/Undo, read-only installed engine/Mono/support inventory and original spruce launch-token reuse. GTA III/VC, Sonic Mania, Celeste and Render96 remain candidates; San Andreas is disabled/experimental. |
| `project/tools/`, `packaging/` | Read-only installed-runtime probe, migration/support/benchmark tools, signed scoped original-only overlays, deterministic rebuild/smoke/fixture rollback, and private operator device acceptance recording. |

The legacy retained-thread/cooperative-audio source experiment remains available for comparison. **Select one integration mode; never apply it together with the process-boundary patch.** Process exit preserves all existing PyUI threads and releases their descriptors as one owned process subtree. No helper may kill or ignore an unknown child to announce successful return. A shell exit, missing command or arbitrary serialized receipt is insufficient.

## Exact source and build identities

- Spruce stable **v4.5.4**: `d45ff8dfe5756147522b04ae5863d17a90e88b54`; PyUI tree `4d0bdb3111d9226fbacbea6c89d65e540620e21e`. The complete stable archive was independently hashed: 1,652,634,074 bytes, SHA256 `4623f1cd824ac1d01e7663d11ca40a8d3ad874c5f071e692f4392957d2159cfd`. Ten selected integration/licence files match Git; see [release-source audit](project/evidence/release-source-audit.json).
- PPSSPP **v1.20.3**: `d357e6a32934800d3d80b49f910a603e1b069751`; spruce PowerVR recipe `9f770cb984fd8ffcc8f91d24fcbca859439c2e9b`. New state/API/recipe-override locks are separate from the original menu-only lock.
- Current complete PPSSPP candidate: **19,934,560 bytes**, SHA256 `a93f7db82692c4b95dcb15282d8d73080d51a8912fc8e435adb3b6dfe30c165d`. It compiles project patches 0001–0004, all ten selected spruce patches and pinned FFmpeg. The recursive **16-object SDK audit passes**, requiring only GLIBC 2.17. FFmpeg's actual configuration is LGPL-2.1-or-later with GPL/nonfree/version-3 options disabled; 55 named component notices are retained. See [complete state build](project/evidence/ppsspp-complete-state-build.json). No target executable was run.
- Earlier PPSSPP build attempts remain evidence: [initial build](project/evidence/ppsspp-candidate-build.json) linked against too-new libc symbols; [corrected menu-only build](project/evidence/ppsspp-sdk-search-build.json) fixed GCC9/SDK searches and rebuilt pinned FFmpeg. Their hashes/results do not describe the later state-session binary.
- The [first state-session build](project/evidence/ppsspp-state-session-initial-build.json) passed compilation/SDK checks but lost the first successful checkpoint's export after a later failure in the same request. The later retained-success protocol fixes that source behavior and has separate binary/source identities.
- RetroArch **v1.22.2**: `69a4f0ea1e8aaf442ae4858f2e7f2b31a1776576`; actual spruce IGM recipe `71d84da4dc88945177a3eb34268013355c705dbd`. The new IGM controls patch SHA256 is `39ecc22a4b43bf210132df9d30c6a7c8869b19afca4953ec9585807bcbbec5a6`. [Native build instructions](project/retroarch/build-candidate.md) record original-target SDK adaptations separately from source acceptance.
- Current complete RetroArch/IGM candidate: **15,182,848 bytes**, SHA256 `118146e2aed90c5ccbc416e4c7e01acc8ec7abb7462e1d43f97e8734f113df1d`. The recursive **23-object SDK audit passes**. Original-target adaptations disable unavailable Vulkan, preserve bundled compatibility-header precedence and link the proved GCC9 C++ runtime statically. Earlier configure/link/audit failures are retained separately. See [complete IGM build](project/evidence/retroarch-igm-build.json). The private binary and source/build archives live under `/workspace/scratch/retroarch-igm-tg5040-final`. No target executable was run.
- Bundled stable executable observations are separate: PPSSPP SHA256 `d0635cdb73e046cf8c62a92a4c59194cf9a80dfabbe08a0c9a0cb4628a1c96d7`, embedded v1.20.3; `ra64.universal` SHA256 `bd96dd8f10c479d17ff4a5db943a6828ccb0b74c6eb463faeb99d941fa16d550`, embedded 1.22.2. Version strings do not establish exact source correspondence or installed-device identity.

## Verification and workspace continuity

Scratch outputs, virtual environments and source clones are temporary. After workspace replacement, use the lightweight branch checkout above, recreate the dependencies from `project/requirements-dev.txt`, and recreate all **five** untouched pinned references. The [CI workflow](.github/workflows/smartpro-offshoot.yml) records the exact sparse checkout paths and host package setup; avoid downloading complete base distributions. Source-dependent skips do not count as a complete pass.

| Environment variable | Repository and exact commit | Current temporary checkout / lock |
|---|---|---|
| `SPRUCE_SOURCE_ROOT` | [spruceUI/spruceOS](https://github.com/spruceUI/spruceOS), `d45ff8dfe5756147522b04ae5863d17a90e88b54` (v4.5.4) | `/workspace/spruce-baseline`; `docs/spruce-source-lock.json` |
| `PPSSPP_SOURCE_ROOT` | [hrydgard/ppsspp](https://github.com/hrydgard/ppsspp), `d357e6a32934800d3d80b49f910a603e1b069751` (v1.20.3) | `/workspace/ppsspp-reference`; `project/ppsspp/source-lock.json` |
| `SPRUCE_RA_SOURCE_ROOT` | [spruceUI/RA](https://github.com/spruceUI/RA), `71d84da4dc88945177a3eb34268013355c705dbd` | `/workspace/spruce-ra-reference`; `project/retroarch/source-lock.json` |
| `PORTS_SOURCE_ROOT` | [PortsMaster/PortMaster-New](https://github.com/PortsMaster/PortMaster-New), `444778f3ae29facbd97b823dc3ca7270b3ebe499` | `/workspace/ports-reference`; `project/ports/celeste-fix.lock.json` |
| `PORTMASTER_SOURCE_ROOT` | [PortsMaster/PortMaster-GUI](https://github.com/PortsMaster/PortMaster-GUI), `ccea6b746827d0ae3a1cad744f6e8ccc5a032041` | `/workspace/portmaster-reference`; `project/profiles/ports-sources.lock.json` |

From the repository root, the current local full-check command is:

```sh
PYTHON=/workspace/smartpro-venv/bin/python PYTHONPATH=project \
SPRUCE_SOURCE_ROOT=/workspace/spruce-baseline \
PPSSPP_SOURCE_ROOT=/workspace/ppsspp-reference \
SPRUCE_RA_SOURCE_ROOT=/workspace/spruce-ra-reference \
PORTS_SOURCE_ROOT=/workspace/ports-reference \
PORTMASTER_SOURCE_ROOT=/workspace/portmaster-reference \
PYSDL2_DLL_PATH=/workspace/scratch/trimui-host-libs/usr/lib/x86_64-linux-gnu \
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
sh project/dev/check.sh --report /workspace/scratch/trimui-next-certification.json
```

The current host uses Python 3.12.14, PySDL2 0.9.17, Pillow 11.1.0 and system SDL2/libsodium. Its isolated SDL_image 2.8.8 directory is the `PYSDL2_DLL_PATH` above; a fresh host can use the packages pinned by CI. Source tests need Git, host C/C++ compilers and binutils. CI checks out all five exact sources and uploads original-only development artifacts; it does not publish native emulator/SDK outputs. Keep target SDL/system libraries unchanged. Future actual test counts may increase; do not hardcode 690 as the runner's success criterion.

Build the current original-only preview from its descriptor with a new output directory:

```sh
PYTHONPATH=project \
PYSDL2_DLL_PATH=/workspace/scratch/trimui-host-libs/usr/lib/x86_64-linux-gnu \
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
/workspace/smartpro-venv/bin/python project/packaging/dev_release.py \
  --output /workspace/scratch/trimui-next-development \
  --include-source --smoke-python /workspace/smartpro-venv/bin/python
```

The earlier private PPSSPP checkpoint used `/workspace/scratch/ppsspp-complete-checkpoint-final`: `output/PPSSPPSDL_TrimUI` and `candidate-corresponding-source.tar.gz`. Its exact source archive size and SHA256 are recorded in `project/evidence/ppsspp-complete-state-build.json`. The earlier 640ce8 binary/archive used `/workspace/scratch/ppsspp-complete-state-final`, and the RetroArch checkpoint used `/workspace/scratch/retroarch-igm-tg5040-final`. These historical paths do not establish current custody; the prior native outputs were not established as recoverable in the replacement workspace. R04 must prove retrieval or rebuild matching inputs and outputs. Keep engine binaries, complete upstream source distributions, SDK blobs, owner data and private keys out of Git/public preview artifacts.

Current local dev9 artifacts are at `/workspace/scratch/trimui-host-batch3-dev9`; its source-export rebuild is at `/workspace/scratch/trimui-dev9-source-rebuild`. The downloaded CI ZIP is `/workspace/scratch/trimui-dev9-ci-evidence.zip`. To recover without those files, retrieve artifact `12463233054`, verify its outer SHA-256 above and all eight entries in `development/SHA256SUMS`, then compare its certification, frontend identity and source inventory with the versioned receipts. If expired, rebuild from the exact historical commit and pinned inputs; a new signer produces a new signature, so retain its new provenance rather than claiming the old signed TAR digest. The exported original-source ZIP can reproduce the preview/source ZIPs without Git; strict five-source certification and upstream/native work still need the repository and source locks.

Historical dev4 artifacts/review kits used `/workspace/scratch/trimui-development-20261022-dev4-ready`, `/workspace/scratch/trimui-source-review-20261022-dev4-ready` and `/workspace/scratch/trimui-tg5040-acceptance-ready`. Their review observations are retained in [review evidence](project/evidence/source-integration-review.json). Recreate private review kits or empty acceptance sessions when needed; none establishes source-use permission or a physical pass. All 13 areas remain `not_run`.

## Remaining external work

1. **When the original TG5040 is available**, use the [device runbook](project/docs/device-test-runbook.md) on a spare/restorable setup. Capture firmware, filesystem, installed source/engine/loader/library identities and complete writers; prove original-card/internal-launcher/scene restoration before experimenting. The recorder retains selected save hashes and append-only operator observations; checksums do not authenticate a hardware claim or enable a profile.
2. Test built-in/external input, held keys, real display readiness, native menus/themes and per-game overrides. Test normal launch/quit, complete descendant ownership, state save/failed-save/Resume/load acknowledgement, battery saves, suspend/wake/audio/low battery, save-aware poweroff and clean-unmount USB. Preserve lexical launch paths and newer saves. Measure fixed scenes before claiming speed, memory or battery improvement.
3. Prove FAT/exFAT interrupted transactions, update coexistence, classic fallback and recovery. Package rollback, whole-card restore, internal startup/scene restore and vendor firmware recovery are different procedures.
4. Complete [source-use and distribution evidence](project/docs/release-rights.md). The concrete PyUI [notification draft](project/docs/author-notification-draft.txt) names both pinned recipients and a proposed public project contact. **It is unsent.** Do not use tools to contact anyone without an explicit send instruction. A fixture review object, development signature or arbitrary JSON cannot complete notification or grant redistribution rights. The exact PPSSPP/IGM recipe sources and SDK/runtime grants remain unresolved; retain per-component notices and matching source privately.
5. Review each installed port's exact engine/runtime/data rights and physical input/graphics/save behavior. San Andreas has no verified target contract; do not label it supported or fabricate performance.

Only reviewed evidence for the corresponding feature may change `hardware_qualified`, `runtime_verified`, `source_use_verified`, installed fingerprints, state formats or writer profiles. Do not merge/release/activate merely because host checks and cross-builds pass.

## Critical contracts

- Existing PyUI stages `/tmp/cmd_to_run.sh`; the principal owns foreground execution. Preserve the normal device/model/controller callbacks and initialized favorites/recents managers. Their constructors can rewrite/prune histories; use snapshots or existing instances.
- Preserve lexical `Emu/<system>/../../spruce/scripts/emu/standard_launch.sh`. Canonicalizing the invoked path breaks `$0`-based system detection. Validate containment separately.
- Per-game preset keys include the ROM extension; duplicate basenames can share overrides. Unknown presets must not silently select another engine.
- PPSSPP platform INIs under `Saves/.config/ppsspp/PSP/SYSTEM/` remain authoritative; preserve spruce copy-in/copy-back. Manually authored per-game INIs can override global keys, so common changes require the complete independently verified override inventory.
- Keep `enableButtonWatchers=false` and the existing `save_poweroff.sh`. No second input/power owner, global graphics/libc upgrade, guessed state path, fake clean shutdown or Resume from a recent entry.
- Completed-state callback, process-tree completion, stopped config writers and durable storage are separate facts. A failed later save leaves an older authenticated checkpoint's original verification timestamp. Verification time is not the save-completion time and must not be labeled as such.

Original Python/assets use MIT, Noto Sans uses OFL, PPSSPP source patches/fixtures use their separate GPL-2.0-or-later scope, RetroArch patches/fixtures use GPL-3.0-or-later, and spruce/PyUI retain their own noncommercial/notification terms. Do not describe the combined project as wholly MIT or infer a root licence for every component.
