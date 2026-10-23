# Maintenance decisions without the device

The five pinned sources stay unchanged. Current upstream references were read on
23 October 2026, and every changed path in the three moving sources has an exact
hold decision. This finishes the present source-update decision and the software
maintenance procedure. O03 still needs the first physical pilot and accepted
ongoing maintenance ownership before the full plan row can close.

The [reference and review index](../evidence/nondevice-maintenance-20261023/reviews.json)
binds the commits, complete path lists, decisions and their hashes. These are
metadata coverage checks plus the focused source review described below. They do
not claim a behavioral audit of every changed upstream line. No proposed code was
executed and no source pin, installed engine or runtime gate changed.

| Source | Observed reference | Changed paths from pin | Inside / outside existing scope | Decision |
|---|---|---:|---:|---|
| spruceOS | Development `4a9754c2076b4ff48cbb4b24fc7a96988c48d805` | 635 | 244 / 391 | Keep v4.5.4; the changed lifecycle and frontend need a separate integration candidate |
| PPSSPP | master `902e5ccd8c1400b4387b73942491cded655e5f9c` | 1,699 | 909 / 790 | Keep v1.20.3; broad native/config/save/dependency changes invalidate reuse of its evidence |
| spruce RA recipe | main `71d84da4dc88945177a3eb34268013355c705dbd` | 0 | 0 / 0 | Already pinned; no source update |
| PortMaster-New | main `c987872a65daf42ea1dacab6a5eed3a70f174fe2` | 111 | 0 / 111 | Celeste source unchanged; hold other titles and new runtime |
| PortMaster-GUI | main `ccea6b746827d0ae3a1cad744f6e8ccc5a032041` | 0 | 0 / 0 | Already pinned; no source update |

There are 2,445 changed paths across the current comparisons. The earlier spruce
`cb6210aa` queue is preserved separately: all 230 scoped and 374 outside paths now
have a hold disposition. Its 604 paths overlap the current comparison and are not
added to that total. The new Development revision adds 70 changes relative to
that earlier revision, including changes to paths already in the old queue.

## Findings behind the decision

The [focused findings](../evidence/nondevice-maintenance-20261023/findings.json)
retain primary source paths, old/new object identities, the observed changes and
required tests. Source contracts examined include:

- **Boot and return:** principal adds a bounded CPU-lock wait and asynchronous
  LED work; runtime changes device-init waits, watchdog startup, swap/zram work
  and startup ordering. The embedded/principal/resident seams target the pinned
  source. Reusing their old tests for the new loop would omit changed owners.
- **Input and rendering:** controller input adds idle waits and redraw wakeups;
  held-input repeat moves into `last_input()`. Display adds frame-change tracking,
  fallback fonts and device-created windows. The in-game menu loop explicitly
  selects a 0.1-second input timeout. These changes affect both the classic UI
  and the shared-renderer route; source integration and physical input/return
  checks must move together.
- **TrimUI settings and loaders:** upstream removes OSD startup/hotkey selection
  and stops starting `musicserver`. A new glibc binding script can replace stock
  runtime libraries using RAM copies, while SmartPro `setsid` becomes a shell
  wrapper selecting `/tmp/glibc/setsid` or BusyBox. An old ELF/helper hash cannot
  qualify these different executed paths. Keep the existing base and repeat
  actual loader, audio, display, input, mount and cleanup inventory on any update.
- **Power and USB:** stage 2 adds card-dependent mount IDs, mapped-file/loop and
  swap handling, a static shell and uptime-based shutdown waits. The USB gadget
  helper also adds an empty-storage-device guard. They need real clean-unmount,
  full/read-only-card, interrupted-session and recovery cases. Reports from
  another platform do not establish original TG5040 behavior.
- **Native defaults:** SmartPro PPSSPP defaults change anisotropy and hardware
  tessellation; RetroArch defaults change menu scale, history paths and other
  settings. Keep baseline measurements and save/config identities tied to the
  actual installed defaults. Optional native candidates remain separate.
- **PortMaster:** shared launch changes include `XDG_DATA_HOME`, persistent
  PortMaster selection and Python bind handling. Exact installed-generation,
  managed-runtime, save and cleanup observations must be repeated if adopted.
- **PPSSPP development:** `Core/Config.cpp` migrates legacy frame-rate settings
  toward alternate-speed percentages and adds load-state confirmation settings.
  SaveState, key mapping, SDL and NativeApp files also change. `.gitmodules`
  removes naett and adds frametests/oboe; other dependency identities change.
  The retained v1.20.3 build, GPL patch preimages, source bundle, SDK audit and
  save/session evidence cannot certify this new branch.
- **PortMaster-New:** neither pinned Celeste launcher nor `repack.src` changes.
  The 111 outside-scope paths belong to other titles and a .NET 3.1.32 aarch64
  runtime/registry addition. A zero Celeste delta does not approve that runtime
  or the unrelated title binaries.

Each review also contains a required-input comparison. Changed source entry
points remain visible even when other files or licences are unchanged. New
fonts, demo ROMs, engine binaries and notices are held with the rest of the base;
none enters the original-only payload through this review.

## Maintenance matrix

The repository administrator remains `daniel1990000`. That is an access/decision
authority, not evidence of an accepted response time or continuing on-call duty.
The engineering role below can be performed in a future authorized session.
There is no new background schedule or external message.

| Area / responsible role | Trigger | Required record and action |
|---|---|---|
| Source updates / engineering | Proposed base, engine, PortMaster or port update | Exact old/new commits and every changed-path hold/review; inspect dependencies and licences; accept only a separate deliberate candidate |
| Host defects / engineering | Reproduced fault in supported host preview | Small failing reproduction, affected release/hash, fix and appropriate strict host/source checks; record recovery outcome |
| Packaging / release maintainer | Any selected payload, source, notice or build-input change | New descriptor/build identity; signature/payload readback, same-key determinism, source-export reproduction, installed smoke and retrieval evidence |
| Trust / release maintainer | Key loss, compromise, expiry or rotation | Existing key registry and trust-rehearsal/handoff checks; reject revoked packages; retain operational custody/recovery evidence outside Git |
| Device incidents / operator plus engineering | Failed boot, return, input, save, USB, sleep or update | Stop the affected candidate, retain raw failure and exact inventory, follow the verified restore route; requalify affected cases before restoring support |
| Native engines and Resume / engineering plus operator | Binary, SDK, config/state format or source seam changes | R04/R06 new source/build custody; N01 controls/save/return/performance; N02 real same-boot save/load, stale/replay and benign INI-write cases |
| Ports / engineering plus operator | Launcher, engine, data, helper, managed runtime or save-path change | P01/P03 inventory/readiness/backup; P04 per-title prepare/launch/save/reload/failure/cleanup; retain exact exclusions |
| Support and retention / release maintainer | Bug report or new artifact | Existing redacted support export, independent complete archive readback and per-member checks; record expiry and original snapshot identities |

## Bug triage and requalification

Every issue record needs the release and payload hashes, base/source/binary
identities, host or device context, expected/observed result, smallest available
reproduction, raw evidence and whether data/recovery was affected. Remove
credentials and personal paths with the existing support exporter before sharing.
A symptom report is retained as unconfirmed until reproduced or independently
reviewed; a host fixture stays labelled as a host fixture.

Use these dispositions:

| Class | Scope and handling | Exit evidence |
|---|---|---|
| Recovery, data integrity, trust or ownership failure | Block the affected candidate; retain failure; restore with the established route | Reproduction fixed, fault/recovery checks pass, and device cases rerun where physical behavior was involved |
| Core host regression | Keep current device gates unavailable; fix the supported host behavior | Appropriate regression and strict five-source certification; new packaging evidence if bytes changed |
| Optional engine, Resume or title failure | Exclude that exact feature/candidate; avoid widening the supported scope | Relevant N01/N02/P04 casebook, exact source/runtime identity and separate review |
| Unsupported platform, firmware or content | Record the exclusion; request no blanket promotion | Deliberately scoped source/runtime/device programme before any support claim |
| Upstream change or issue lead | Keep the source pin; preserve the primary reference and assessment | New candidate review and all affected qualification, or a documented decision to stay pinned |

Changing source seams, engine/runtime/helper bytes, firmware/filesystem or shared
writers invalidates the affected physical evidence. Configuration or defaults
that change controls, saves, performance or loaders also require the relevant
cases again. Text-only documentation can retain earlier artifact identities
when it clearly identifies the exact older snapshot. Signatures, test counts and
review reports never promote a device automatically.

The current upstream findings above are update holds, not reproduced defects in
the shipped host preview. No upstream issue was filed or author contacted.

## Reproduce the review

The existing drift queue remains available. The new
[`maintenance_review.py`](../tools/maintenance_review.py) validates explained
holds against the complete raw Git delta, including paths outside configured
scopes. It avoids expanding unchanged large trees: PortMaster-New's full tree
exceeds the older review tool's 16 MiB metadata bound, while its actual changed
path list is small. It checks exact commits, added/deleted/mode/gitlink identities,
duplicate/omitted paths and stale review packets. It never imports upstream code,
changes a pin or authorizes adoption.

```sh
PYTHONPATH=project python3 project/tools/maintenance_review.py \
  --source PORTS_SOURCE_ROOT \
  --repository /path/to/ports-with-both-exact-commits \
  --candidate c987872a65daf42ea1dacab6a5eed3a70f174fe2 \
  --review project/evidence/nondevice-maintenance-20261023/ports-current-review.json \
  --output /tmp/ports-review-new.json
```

The output must be new and outside the inspected source repository. Ten focused
regression tests pass, including omitted outside-scope paths, changed modes,
stale identities, replacement objects and attempts to change a hold to approval.
All six retained packets were run through the CLI; their reports match the saved
validation bytes. [Verification](../evidence/nondevice-maintenance-20261023/verification.json)
records that scope. The continuation's full certification and clean package/source
rebuild are recorded separately by the integrating agent; earlier dev13 build
receipts keep their original identity.
