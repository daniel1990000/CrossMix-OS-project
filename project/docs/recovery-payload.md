# Private backup payloads and restore rehearsals

`tools/recovery_payload.py` supplies D02 engineering for real directory-tree
copies. It uses the existing `recovery_preflight.py` inventory, manifest and
readback verifier. It does not install the project, start a program, mount a
filesystem, flash firmware or overwrite an existing destination.

D02 physical completion remains open. No owner device, actual save coverage,
independent storage, spare-card boot or internal-startup restoration was tested
while creating this tool. Every record keeps `physical_restore_tested`,
`hardware_qualified`, `independent_media_verified` and `automatic_activation`
false. These reports cannot admit a D01 candidate or enable a production profile.

## Select the three scopes separately

| Scope | Selected stopped source | Preserved comparison |
|---|---|---|
| `card-files` | Entire offline card file tree | Every regular file byte/path and empty directory |
| `saves` | Actual complete save/config tree or a reviewed selection | Every selected regular file byte/path and empty directory; no automatic save discovery |
| `internal-files` | Separately prepared actual internal-file staging tree | File bytes, directories, mode, uid and gid, including selected root metadata |

The scope label does not discover paths or establish completeness. Stop writers
through their existing authorities and take the source offline first. The tool
never changes source bytes, modes or ownership. Reads can affect access times
on a writable filesystem; use a read-only offline mount when that matters.

Symlinks, hardlinked regular files, special files and extended attributes/ACLs
are rejected rather than flattened. The existing verifier can compare symlink
text, but this copier deliberately does not create links. A real internal
backup containing links, capabilities, ACLs, partition/boot data or other
unsupported metadata needs a separately reviewed archive/image procedure.
Do not omit those files merely to obtain a passing file-tree report.

For `internal-files`, the backup filesystem and operator privileges must support
actual uid/gid/mode preservation. Permission failures stop the copy. FAT-style
unpacked staging cannot substitute for Unix metadata. Timestamps, filesystem
structure, sector contents and extended metadata are outside this payload format.

## Create a new private backup

Choose an existing trusted parent directory outside the selected source. The
output path itself must not exist, including as an empty directory or symlink:

```sh
python3 project/tools/recovery_payload.py backup \
  --scope card-files --source /offline/original-card \
  --output /private/backups/card-2026-10-23

python3 project/tools/recovery_payload.py backup \
  --scope saves --source /offline/selected-save-tree \
  --output /private/backups/saves-2026-10-23

python3 project/tools/recovery_payload.py backup \
  --scope internal-files --source /private/original-internal-staging \
  --output /private/backups/internal-2026-10-23
```

The tool creates a new exclusive 0700 container and a new `data/` tree.
Each new directory's stat identity is captured before opening it; the opened
inode and its pathname must match, remain private/owned and be empty before
any descriptor mutation or copy. Replacements at that boundary are refused.
The created data-root identity is also bound before copying begins. The parent
must be trusted against same-owner replacement before the first capture: POSIX
`mkdir` has no portable atomic create-and-open directory operation. This tool
is not a security boundary against an owner replacing its trusted parent or
program. It never treats a successful pathname open alone as proof of ownership. Files
are streamed in at most 1 MiB chunks through anchored, no-follow descriptors;
new destination names use exclusive creation. File hashes, identities and
scoped metadata are checked during copying, then both source and retained bytes
are scanned again. Unsupported extended metadata is reinspected through bounded
anchored descriptors after copying and during each fresh retained/rehearsal
readback, because the existing content manifest does not encode those attributes. The unchanged existing verifier produces `manifest.json`
and `readback.json`. File/directory writes are flushed before completion.

The default limits remain the verifier's 250,000 entries, 2 TiB of payload,
64 directory levels and 64 MiB of manifest JSON. `--max-entries` and
`--max-bytes` can lower limits. An empty source cannot establish coverage.
These directory copies do not prove a sector image or a complete card restore.

## Failure and interruption behavior

`INCOMPLETE.json` is a permanent initial intent record. It is never removed:
this tool deletes no output path. A successful operation additionally creates
`COMPLETE.json` last, binding the exact manifest/readback digests. A filename
alone is not success. Retain the command outcome and review a fresh verification.

Any caught interruption, full/read-only storage, metadata error, failed hash,
changed source/output identity, late extended metadata or flush failure returns failure and attempts an
exclusive `FAILED.json` record. Partial bytes stay private for inspection. If
storage also refuses the failure record, keep the original failure and initial
intent; do not treat a completion-looking filename from an interrupted operation
as proof of durability. Unexpected/replaced paths are never recursively cleaned,
removed, renamed back or overwritten. Retry with a new destination.

Exit **0** means the requested file-tree operation and its readback completed.
Exit **2** means invalid input, unsupported content, changed identity, limits or
an I/O failure. `KeyboardInterrupt` also retains incomplete state and propagates
the interruption. No failure branch can claim a physical recovery pass.

## Retrieve and verify retained payloads

Retain each entire private container separately, including its manifest and
records. Retrieve the bytes into another private container and record the
external transport hashes and actual storage provenance. A new directory or a
different inode is not proof of independent physical media.

The existing verifier can compare a retrieved `data/` tree without executing it:

```sh
python3 project/tools/recovery_preflight.py verify \
  --manifest /private/retrieved/card-2026-10-23/manifest.json \
  --backup /private/retrieved/card-2026-10-23/data \
  --output /private/evidence/card-retained-readback.json
```

Keep the retrieved payload container private. Extra/failed/incomplete entries,
linked records, changed completion/manifest hashes or changed data prevent the
new restore operation from accepting it. Manifests detect consistency changes;
an operator can still edit records, so independent review remains necessary.

## Restore only into a new expendable directory

The restore command refuses any existing destination. It never merges a
backup into a live card, saves directory or root filesystem:

```sh
python3 project/tools/recovery_payload.py restore \
  --payload /private/retrieved/card-2026-10-23 \
  --output /private/rehearsals/card-2026-10-23
```

It first verifies the retained container, then creates a new private container
and `data/`. It copies only supported manifest entries, checks the retained
payload again after copying, and invokes the unchanged verifier against both
retained and restored trees. `rehearsal.json` binds the original manifest and
contains the fresh comparison; completion binds its hash and input identities.
Newer or unlisted owner saves in any existing tree remain untouched.

A matching expendable directory is a file-tree rehearsal. It still needs the
actual D02 media restoration/boot/save readback and a separately rehearsed
firmware-specific internal-launcher/FN recovery route. This tool provides no
in-place internal restore command or firmware operation.

## Host checks

Thirty-seven focused tests cover real whole-tree copies, Unicode/empty entries,
internal-root metadata, restore readback, existing-target preservation, source
and destination replacements, corrupt retained bytes, concurrent changes,
interruption, full/read-only storage, failed file/completion flushes, unsupported
metadata, symlinks/hardlinks/special files, limits and incomplete-state rejection.
All fixtures are synthetic host data.

```sh
PYTHONPATH=project python3 -m unittest discover \
  -s project/tests -p test_recovery_payload.py
```
