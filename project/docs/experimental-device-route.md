# Private TG5040 experimental route

D01 design prepared on 22 October 2026 against repository commit
`bc80ff272a5c851f3c0dc1ad1832b33ca74148bc`. This document specifies work still
needed before the first private device pilot. It supplies no executable harness,
device result or admission to run a candidate. D01 remains open. The source
review and its file hashes are recorded in
[d01-design.json](../evidence/device-preparation/d01-design.json).

The first pilot should retain the installed engines and existing spruce
authorities. Use a spare card whose contents and necessary internal files have
passed the D02 restoration rehearsal. Record the actual device in D03 before
choosing a firmware/filesystem matrix. Firmware 1.1.1/FAT32 remains a proposed
matrix; this design grants no firmware-flash instruction.

## Existing boundaries and the execution gap

The following behavior is present in the inspected source:

| Source | Present contract | Consequence for a pilot |
|---|---|---|
| [qualified_runtime.py](../bridge/qualified_runtime.py) | `configuration()` returns `None` | The shipped integration cannot admit a device candidate. |
| [process_source.py](../bridge/process_source.py) | `ProcessSourceConfiguration.assert_safe()` requires source-use, runtime, hardware and process-exit qualification; its host-fixture mode rejects `/mnt/SDCARD` | A host fixture or an invented true profile is not an experimental device route. |
| [embedded.py](../psp_shell/embedded.py) | `qualification()` separately enforces device gates; `EmbeddedRunner` reuses existing Display and Controller objects | Changing only the principal configuration cannot authorize presentation. |
| [principal.py](../bridge/principal.py) | `run_owned_tree()` adopts descendants and waits for kernel `ECHILD`; command bytes are sealed and consumed against their captured identity | A timeout, shell exit or changed PID cannot be substituted for foreground completion. The wait currently has no deadline. |
| [resident.py](../bridge/resident.py) | A private boot-bound lifetime and dirty guard block uncertain restarts; a resident owner retains delegated shared services | A pilot must retain the dirty guard and account for shared services separately. |
| [principal_integration.py](../bridge/principal_integration.py) | One exact-source process-exit patch uses the literal `/mnt/SDCARD/App/PSPMode/integration/app` root | No card field may supply code paths; the retained-tasks alternative cannot be installed with it. |
| [pyui_entry.py](../bridge/pyui_entry.py) | `maybe_run_main_menu()` can continue the existing classic MainMenu only when the foreground and resource-restoration checks allow it | Classic fallback must use that existing initialized session or a proven subsequent session. |
| [release.py](../integration/release.py) | Private composition requires a retained `SourceUseReview`; verification keeps device activation and qualification false | A development signature or review-kit manifest does not authorize assembly or activation. |

Production checks must remain intact. A future experimental route needs its own
reviewed admission type and a fixed entry point, with explicit handling at both
the principal and embedded boundaries. Neither exists in this checkpoint.
Creating this document or a casebook cannot change that fact.

## Candidate and admission identity

Prepare the candidate record on a trusted workstation, outside the test card.
The expected inventory comes from the reviewed build and source composition,
before comparison with installed bytes. Do not populate expected hashes by
reading the same card that is being admitted. The admission review must bind:

- Frontend commit, actual original-source inventory, release descriptor and
  signed package bytes, plus the public-key fingerprint obtained through the
  trusted workstation. The dev9 historical implementation is
  `02999f4aa16b08c028e61861b8721c3905b7086e`; its recorded CI source head and
  merge checkout remain `e030677199884441096d90382121b86cfef81796` and
  `6b4b59cfbdb0597c0dd2c23dea5d904256eeda70`. A later candidate receives its
  own exact identity. A signer change receives a new signed-package digest.
- Spruce commit `d45ff8dfe5756147522b04ae5863d17a90e88b54`, PyUI tree
  `4d0bdb3111d9226fbacbea6c89d65e540620e21e`, every selected patch, source
  preimage and resulting file, retained notices and restoration preimages.
  Include all paths in `SOURCE_BLOBS` and `REQUIRED_PROJECT_MODULES` at the
  candidate revision, including transitive imports. Do not use the historical
  module count as an allowlist.
- Complete installed pilot imports, launcher/principal/service scripts, trusted
  Python and native loader/library identities. Include the independently
  reviewed fixed experimental entry code itself. A source inventory of selected
  text contracts does not identify an entire installed spruce distribution.
- D02 backup and restore evidence, D03 observed original TG5040 model,
  firmware, filesystem, kernel/tool availability and actual baseline engine
  identities. Static ELF inspection and live mapped-object observations retain
  their different provenance.
- The private R05 delivery/scope reference and reviewer decision. Notification
  evidence and commercial permission remain separate. The prepared notice is
  unsent; no communication is authorized here.
- Session identifier, boot ID, principal PID/start identity, media observation,
  allowed stage/actions, admission expiry, exit/recovery procedure and durable
  evidence destination. Use a fresh admission for a new boot or candidate.

If a native candidate is later selected, also bind its exact binary,
corresponding-source and build archives, retrieval proof, SDK/dependency
inventory and applicable R06 review. R04 historical hashes alone cannot admit
that candidate. Enhanced Resume stays outside the first core pilot.

The proposed admission is a typed in-memory capability constructed by fixed,
reviewed code after a real operator review and live checks. A serialized record
is evidence to inspect, never executable authority. There is no proposed
`--enable-device`, `--qualified`, card JSON or environment-variable override.
Its only effect would be permission to attempt the listed experimental cases;
it must leave `hardware_qualified`, `runtime_verified`, production-profile and
distribution gates false. Successful cases cannot automatically promote it.

This protects against stale or accidentally altered inputs. The SD card remains
editable and the device may run privileged code. It does not provide a security
boundary against an owner replacing the program, kernel or trust root. A
self-signed package copied alongside its own public key cannot establish an
independent trust decision.

## Stages and bounded decisions

The times below are proposed pilot limits to review against the observed
baseline, not measured target behavior or commands implemented by this design.
The existing principal remains the foreground owner. Do not wrap it in a shell
`timeout` that kills the helper and then starts classic.

| Stage | Scope and limit | Exit and retained outcome |
|---|---|---|
| Preparation | R05 review, D02 restoration rehearsal and D03 observation must be complete for the selected scope; compare all expected/installed identities | Any unknown requirement records `blocked` before a candidate starts. |
| Admission | One named case, one boot, at most 60 seconds between the final live identity check and first source startup | Expiry before startup consumes/refuses the admission; no candidate starts. A replacement owner, changed hash, dirty lifetime or staged command also refuses it. |
| View-only pilot | At most 120 seconds in the existing PyUI process; browse original synthetic metadata or copied owner content. No game, tool, advanced menu, settings write, USB or power-transition action | A source-owned timer requests the ordinary classic return. The existing Controller supplies the normal user exit action. The timer never opens input or runs a hardware script. |
| Cooperative return | Allow 5 seconds after a requested pilot exit for the existing event loop/resource callbacks to report a safe return | A successful in-process return uses `release_for_fallback()` and records observed classic frame/input readiness separately. Expiry records `blocked`; it cannot assert completion or start another UI. |
| Launch/return pilot | Later admission: one reviewed registered action through initialized PyUI and the original launcher, unchanged engine and copied disposable saves; proposed 10-minute observation window | Normal native quit remains the primary exit. The principal must observe `ECHILD`, consume the exact staged command and complete the correlated lifetime before another source starts. Timeout records failure and closes admission to new actions. |
| Optional features | New admissions for settings writes, native candidates, state operations, sleep/USB and ports | Each uses its own case evidence and recovery method. Omitted features remain unavailable. |

A frame count bounds iterations, not elapsed time. `EmbeddedRunner.run()` already
accepts `max_frames`, but that cannot bound a blocked SDL call, source startup,
input callback or native process. The proposed wall-clock stop request and
action restriction still need implementation and tests. Check the deadline
between calls in the existing event owner and recheck admission immediately
before each handoff. Never interrupt a write and label the resulting file
durable.

Once a foreground descendant survives the exit deadline, the helper must keep
its ownership and dirty state. The experimental decision is bounded: stop
admitting actions, retain an explicit blocked result and use the prepared
operator recovery. Guaranteed process termination and real clean recovery are
not established by a timer. Killing a helper or deleting a handoff journal
would destroy evidence while leaving possible display/input/save owners alive.

## Manual session sequence after prerequisites

1. Verify the retained backup by reading it back, rehearse restoration to the
   expendable card and capture the actual device baseline. Keep a separately
   available recovery terminal or other reviewed firmware-specific exit route.
   If early failure cannot be recovered independently of PyUI, the pilot is
   blocked. Existing power/sleep and `save_poweroff.sh` remain the only normal
   power authorities; do not add a daemon or raw sysfs power writer.
2. After actual R05 evidence, compose the reviewed private source tree through
   `assemble_private_candidate` and verify/restore it on the host. Compare the
   final inventory with the admission record. The current API does not install
   or execute it. Preparation alone does not satisfy this step.
3. Perform a separately reviewed offline application to the expendable card.
   The application procedure still needs implementation/review. Preserve exact
   source preimages, modes, unrelated data and lexical launch paths. No rootfs,
   internal launcher/FN scene, engine or global SDL/libc replacement belongs to
   the core pilot. Do not enter an already running principal/UI session by
   starting another one from SSH.
4. Reconnect through the established boot/runtime route and observe that exactly
   one principal/PyUI session owns the display/input. Require existing managers'
   readiness and `enableButtonWatchers=false`, with the existing
   `/mnt/SDCARD/spruce/scripts/save_poweroff.sh` route. Recheck expected hashes
   and owner identities before the fixed experimental entry admits its one
   case. Missing/corrupt preferences stop admission.
5. Run view-only first, then prove ordinary return to classic through the
   current initialized owners. Copy the evidence off the card and read it back.
   Failure or unknown restoration blocks launch/return admission.
6. A later launch/return case keeps the existing game builder, registered
   action, per-game preset semantics, exact `RomInfo`, staged command and
   principal. Preserve lexical
   `Emu/<system>/../../spruce/scripts/emu/standard_launch.sh`; containment checks
   must not normalize the invoked path. Keep state/Resume callbacks absent and
   forbid unlisted tool/settings actions for this admission.
7. Stop after the admitted case. Compare observed save/config changes with
   their reviewed scope and retain newer/unlisted data. Restore source/package
   preimages only where the current bytes still match the candidate. Unexpected
   later edits require conflict review, never blanket overwrite.

All steps describe a future operator session. None has run on the owner's
device. This document provides no shell command that starts an unqualified
candidate.

## Recovery by failure phase

| Failure phase | Required response |
|---|---|
| Before any candidate/source spawn | Record rejection; the existing classic route can continue only after existing ownership checks permit it. |
| Optional view fails before a handoff | Use the current source exception/fallback path. Paired resource restoration, matching owners and a positive idle check are required. A fallback selection is not proof of a working classic frame. |
| Staged command, uncertain source closure, surviving descendant or dead helper | Keep foreground/dirty records and block another UI/game. Use the separately rehearsed operator exit/recovery route; preserve the failure evidence before any permitted shutdown. No generic process-name kill or journal deletion. |
| Card cannot complete a transaction | Stop further writes, retain the card image/logs and use the offline card reader. `force-classic` is a project presentation request; it cannot clear live ownership or repair internal files. |
| Source/package bytes need restoration | Restore exact preimages through the reviewed new-output/source or signed-overlay route. Verify classic behavior separately. Package rollback does not restore the card or rootfs. |
| Internal startup/FN scene changed or boot is lost | Use only the D02 firmware-specific internal-file/stock-launcher recovery. An original card alone cannot undo internal changes. Vendor recovery/firmware flashing is a separate owner-reviewed operation. |

The pinned SmartPro startup bypasses the Flip supervisor. A `boot_to_stock.lock`
or a copied `session.sh` cannot be credited as tested TG5040 recovery. Preserve
the known-good boot procedure until real evidence supports a change. See
[recovery.md](recovery.md) for the separate scopes and private-data limits.

## Durable evidence and acceptance of the route

Use the existing [device acceptance recorder](device-test-runbook.md) for
append-only case outcomes and before/after observations. The session record
also needs the trusted candidate/admission digest, phase transitions,
monotonic deadlines, actual start/exit reason, boot/principal/helper identities,
observed resource return, staged-command correlation and the recovery result.
Keep shell environment, Wi-Fi credentials, process arguments, owner content and
full private correspondence out of shared logs. Existing selected save hashes
do not copy saves and cannot replace D02 backup payloads.

Flush local records and copy each completed/blocked case to independent private
storage before reboot or USB export; retrieve that copy and compare hashes.
`/tmp` is volatile, and a report kept only on the test card is vulnerable to its
failure. Lack of durable evidence blocks the next admission. Content checksums
detect accidental edits; operator statements still need review.

Before calling D01 complete, add and review the experimental entry/admission,
bounded exit requests, stage restrictions and fail-closed behavior at every
existing gate. Host acceptance must cover changed hashes/owners, untrusted
admission records, expiry/replay/cross-boot use, dirty lifetimes, missing
preferences, source initialization failure, blocked renderer/input calls,
partial restoration, surviving setsid/double-fork descendants and helper death.
It must also show that the shipped production entry remains unavailable, that
host fixtures still reject the device card and that failed cases cannot enable
classic over a live foreground owner. Then obtain the real D02/D03 observations
and rehearse the physical stop/recovery route. An admission record, signature or
all-pass case report cannot replace D06 independent qualification review.
