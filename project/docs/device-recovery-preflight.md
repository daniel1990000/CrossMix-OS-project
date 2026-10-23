# Backup verification and device preflight

D02/D03 preparation for the original TG5040. No owner device was connected or
inspected for this work. Physical backup coverage, spare-card restoration,
internal recovery and the actual firmware/runtime inventory remain unrun.
Firmware 1.1.1/FAT32 is the proposed matrix; collect the installed values first.

`tools/recovery_preflight.py` compares real file bytes in separately prepared
offline trees. It copies no files, changes no settings and runs no device command.
Its JSON reports cannot activate a profile or satisfy physical acceptance.
Keep reports and backup payloads private; relative file names can identify games,
and an internal/configuration backup can contain credentials.

## Keep separate recovery payloads

| Scope | Payload to retain privately | Rehearsal and remaining proof |
|---|---|---|
| Project overlay | Signed current/previous project payload, separately trusted public key, selector/journal and project state | Existing signed rollback and offline `force-classic`, with the foreground fully ended before a frontend starts |
| Card | Offline copy of every card file, plus a verified sector/partition image if needed to reproduce its filesystem and boot structure | Restore to expendable media, compare bytes, boot and read actual owner save copies through their existing engines |
| Saves | All native save data, states, memory cards, port/application saves and authoritative configuration paths identified from the actual installation | Read back the copied saves after a real save/quit/reload cycle; retain the original copy throughout |
| Internal files | Original launcher/FN scene files, relevant shell and firmware-specific metadata, including recorded absence | Restore through a separately available firmware-specific method, then demonstrate original startup and FN behavior |
| Vendor firmware recovery | Exact manufacturer TG5040 image, instructions and verified digest | Separate operation with its own operator decision and recovery evidence |

Overlay rollback, card restoration and internal startup restoration require
separate results. An SD-card swap leaves internal modifications in place. The
existing [recovery guide](recovery.md) gives the current rollback boundary and
manufacturer reference; this preparation does not authorize firmware flashing.

Before copying, stop emulators and synchronization through their existing
interfaces and take the card offline. A stable hash read does not prove every
writer was stopped. Use an independent backup destination and retain the source
card unchanged. Keep a second copy in retained storage and read it back.

Pinned spruce [SmartPro initialization](https://github.com/spruceUI/spruceOS/blob/d45ff8dfe5756147522b04ae5863d17a90e88b54/spruce/scripts/platform/device_functions/SmartPro.sh#L43)
can install `/bin/bash` and change `/usr/trimui/scene` through
`apply-switch-action --now`. The installer also changes the internal launcher.
Before any such first setup, retain the actual owner's
`/usr/trimui/bin/runtrimui.sh`, any `runtrimui-original.sh`, related launcher
executable, `/usr/trimui/scene` tree and `/bin/bash`, with modes, uid/gid, link
text and absence observations. Record the actual firmware's restoration route.
Do not replace an existing original backup with another distribution's wrapper.
The list is a source-informed starting point; verify the actual installer's
complete write scope and firmware before considering coverage complete.

For internal files, use a metadata-preserving archive/filesystem. An unpacked
FAT tree cannot preserve Unix ownership and modes. The checker accepts an
unpacked staging copy with those metadata preserved; retain the original archive
and its hash too. Hardlinked files, special files, xattrs/ACLs, partition tables,
boot sectors and filesystem damage require a separately reviewed image/archive
procedure. This file-tree checker cannot verify them.

## Compare backup bytes before changing anything

First make the backup with the owner's chosen trusted copying/imaging tool.
These commands only inspect directories and create new reports outside them:

```sh
python3 project/tools/recovery_preflight.py record \
  --source /offline/original-card --backup /private/backup/card-files \
  --scope card-files --output /private/evidence/card-backup-manifest.json

python3 project/tools/recovery_preflight.py record \
  --source /offline/selected-save-tree --backup /private/backup/selected-save-tree \
  --scope saves --output /private/evidence/save-backup-manifest.json

python3 project/tools/recovery_preflight.py record \
  --source /private/original-internal-staging --backup /private/backup/internal-staging \
  --scope internal-files --output /private/evidence/internal-backup-manifest.json
```

Use the entire actual save tree or a reviewed complete selection. The `saves`
label does not discover save paths or assert coverage. Preserve directory layout,
unknown/newer slots and all original owner files. The original card tree and
backup must be separate nonoverlapping directories. Each report records hashes
and sizes; `internal-files` additionally compares mode, uid and gid, including
the selected root directory. Symlink
text is compared without opening its target, including absolute targets such as
`/bin/bash`. Input paths and their directory ancestors cannot be symlinks. Source,
backup and restored roots stay anchored by open descriptors across each scan
batch; changed/aliased root identities and renamed supplied paths are rejected.

An initial mismatch produces a report and exit status **1**. Do not continue on
that result. Fix the backup selection/copy independently and create a new report,
retaining the failure. Status **2** means invalid inputs, unsafe files, concurrent
changes, exceeded limits or an output error. Reports are exclusive 0600 files;
an existing report is never overwritten. Complete bytes are staged in an owned
temporary file, flushed and published atomically without replacing an existing
report, then the parent directory is flushed. Failed writes/publication/flushes
remove the owned temporary/published file. The report destination must support
hardlink publication and file/directory `fsync`; unsupported storage fails.

The scan reads at most 250,000 entries, 2 TiB of payload bytes, 64 directory
levels and 64 MiB of report JSON. Files are streamed in 1 MiB chunks. The checker
rejects special files and multiply linked regular files rather than flattening
them silently. Report limits can stop a very large card; split it into reviewed
nonoverlapping scopes or use the image/archive procedure and document coverage.

## Read back retained storage and a restored spare

Retrieve the backup payload and its original manifest from retained private
storage into new directories. Keep a separately recorded manifest hash with the
backup record. Rehash the retrieved bytes:

```sh
python3 project/tools/recovery_preflight.py verify \
  --manifest /private/retrieved/card-backup-manifest.json \
  --backup /private/retrieved/card-files \
  --output /private/evidence/card-retained-readback.json
```

Restore only expendable media using the reviewed copying/imaging procedure.
Then compare the independently mounted restored tree and retained backup with
the same manifest:

```sh
python3 project/tools/recovery_preflight.py verify \
  --manifest /private/retrieved/card-backup-manifest.json \
  --backup /private/retrieved/card-files \
  --restored /offline/restored-spare-card \
  --output /private/evidence/card-spare-readback.json
```

Repeat for saves and internal staging. Missing, changed and unlisted files are
reported separately. Unlisted/newer save files remain intact; inspect the result
rather than replacing them with an older backup. A receipt binds the exact
manifest SHA-256 and current host filesystem identities. Those identities do
not identify physical media or prove independent storage. Checksums detect
accidental changes, and a person who rewrites a manifest can rewrite the claim.
The reports always retain `hardware_qualified=false`,
`physical_restore_tested=false`, `independent_media_verified=false` and
`automatic_activation=false`.

A matching restored file tree still needs a physical boot and save readback on
the intended expendable setup. Record card identity, filesystem, restore method,
expected/actual result and recovery behavior in the existing
[acceptance recorder](device-test-runbook.md). Retain external evidence through
reboot and card export before marking any physical case passed.

## Inventory the actual device after D02

Use the existing read-only collectors. Keep mounted filesystem copies distinct
from live observations, and keep all output outside the inspected trees:

```sh
python3 project/tools/inventory.py \
  --root /private/root-copy --sd-root /offline/card-copy \
  --profile project/packaging/profiles/spruce454-tg5040-development.json \
  --output /private/evidence/device-inventory.json

python3 project/tools/installed_runtime.py \
  --root /private/root-copy --sd-root /offline/card-copy \
  --executable /mnt/SDCARD/Emu/PSP/PPSSPPSDL_TrimUI \
  --readelf /trusted/host/bin/readelf \
  --output /private/evidence/installed-ppsspp-static.json
```

Static ELF inspection executes the trusted host `readelf`, never the inspected
engine or loader. It cannot establish live mapped libraries or rendering. When
normal device operation has already started an engine and its process identity
is verified, the existing recorder's `capture --pid EXISTING_PID` can collect
live mapped-object evidence. Do not start an engine simply to fill a report.

Prepare these observations before a candidate session:

| Observation | Source of evidence / completion condition |
|---|---|
| Original TG5040, actual firmware/kernel/filesystem | Owner device and installed files; labels and operator assertions retain provenance; no inferred upgrade |
| Tool availability | Exact trusted Python/readelf paths and hashes, versions, working storage and retained output route; host tools do not establish target availability |
| Runtime identity | Engine, interpreter and actual dependency hashes; live process start identity and maps separated from offline copies |
| Kernel process boundary | Bounded isolated child-subreaper/adoption/wait test matching `bridge/principal.py`; no real game process or service involved |
| Immutable staged commands | Actual `memfd_create`, sealing and inherited-descriptor behavior; unsupported calls remain blockers until a reviewed alternative exists |
| Local peer identity | Actual Unix peer credentials with known isolated processes; reject wrong peer and stale/reused PID |
| `/proc` identity | Boot ID and process start ID readable/consistent in the actual runtime; no PID-only ownership assumption |
| Source/device ownership | Existing principal, foreground descendants, input/display/audio services and config writers identified; no competing watchers |
| Offline recovery | Operator can recover classic mode and separately restore card/internal state without the experimental frontend |

The kernel tests in this table are preparation requirements; this work adds no
on-device probe executor and records no target results. Source constants or host
unit tests cannot prove kernel support on the owner's device. D03 stays open
until bounded target probes and actual identities are retained and reviewed.
D01 assembly/activation still needs its source-use evidence and physical
readiness; no editable report turns on the shipped runtime.
