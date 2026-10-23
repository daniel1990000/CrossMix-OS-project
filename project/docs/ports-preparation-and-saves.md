# Port inventory, preparation and save preservation

P01–P03 are host engineering work. No game, runtime or owner data was installed,
no real mount was performed, and no title is physically qualified.

## Installed generation and dependencies

```sh
PYTHONPATH=project python project/tools/port_inventory.py --sd-root /path/to/card --port sonic_mania --output /tmp/sonic-inventory.json
```

The inventory writes only the external report. It never sources a shell file,
imports installed Python, mounts/unpacks anything, or creates card state.
It hashes named launcher, helper, engine and managed-runtime inputs, and records
a bounded directory inventory of local libraries. Static headers and presence
are observations; system loader dependencies and graphics compatibility remain
unqualified. Launcher selection stays with spruce/PortMaster.

PortMaster generation detection parses bounded Python source with `ast`.
It distinguishes the old single-file class, the modern class in
`platform/miyoo.py` plus `spruce` registration in `platform/__init__.py`, and
the comment-only `platform.py` marker. A pending `pylibs.zip` is reported
separately without extraction. Removing it or changing platform source is
observed on the next inventory. The exact reference generation is locked at
`ccea6b746827d0ae3a1cad744f6e8ccc5a032041`; its newer device metadata is not
assumed to exist in spruce v4.5.4. Native runtime support remains unverified.

Sonic Mania needs `sonicmania`, `Game.so` and the shipped `libs/libogg.so.0`;
the pinned BUILDING.md identifies both engine/game outputs. GTA records both
graphics engine alternatives and its `libs` directory without selecting one.
Render96 records its installer, engine, architecture-specific libraries and
generated `res/base.zip`, `res/demos`, `res/texts`. After preparation the
launcher can consume the imported ROM; generated resources are a separate stage.
Celeste records Mono squashfs, repacker, FNA patches/libraries and helpers.
Its empty `.astc_done` marker does not replace `Celeste.exe` or Content.

Readiness stages describe observed data/preparation, with missing-component
blockers. Every result keeps `launch_qualified=false`, measured FPS null,
source/binary correspondence unverified and distribution clearance false.
The port's existing save capability is labelled `in-game-save`; none gains
emulator state Resume from this inventory.

## Celeste preparation fix

The optional [locked source patch](../ports/celeste-fix.lock.json) targets
PortMaster-New `444778f3ae29facbd97b823dc3ca7270b3ebe499`. Tests reproduce
the original false success after a nonzero repacker, then apply/check the exact
diff and execute the patched scripts with fake helpers in disposable storage.

The patch captures repacker/progressor status before another command can replace
it, checks completion-marker writes, propagates pipeline/game failure, and
cleans up only Mono/save mounts created by that invocation. Existing mounts are
refused. Tests cover failed mount/bind, full/read-only completion writes, retry,
second launch, cleanup failure and a game error hidden by `tee`. These are
failure injections, not a real mount, storage-fault or device-runtime result.
`mountpoint` and the selected runtime/control helpers must be qualified on the
target before applying this patch. It remains unselected in the host preview.

## Save registry and external backup

| Port | Preservation scope | Source/evidence limit |
|---|---|---|
| Sonic Mania | Root `*.bin` user files, including `SaveData.bin` | Pinned SaveGame.c names SaveData.bin; the wider pattern preserves additional engine user files. Compiled source correspondence is unknown. |
| GTA III / Vice City | Root `*.b` / `*.sav` files | Conservative slot preservation candidates; exact installed-engine paths require device readback. |
| Render96 | Entire `conf/`, recursively | Launcher passes `--savepath ./conf/`; includes settings and progress. |
| Celeste | Entire `savedata/`, recursively | Launcher redirects the native Celeste savedata location here. |

All registries keep `device_paths_verified=false`. An external backup verifies
the declared scope, not undiscovered save paths. Game files, firmware and other
unlisted files are untouched. Use idle maintenance with the game/writers stopped.

```python
from psp_shell.ports import PortsManager

ports = PortsManager('/path/to/mounted-card')
backup = ports.snapshot_saves('sonic_mania', '/path/outside-card/sonic-backup', confirm_idle=True)
preview = ports.preview_save_restore(backup)
# Review every current/snapshot hash before this explicit overwrite operation.
transaction = ports.restore_saves(backup, preview, confirm_idle=True, confirm_overwrite=True)
# If needed, Undo refuses unrelated later changes rather than overwriting them.
ports.rollback_import(transaction, confirm_idle=True)
```

Backups require a new external directory, hash/copy every selected regular file,
recheck the live inventory, and write a completion receipt last. They reject
symlinks, special files, absent saves and oversized inventories. A failed copy
removes its partial backup and leaves live files unchanged. Restore validates
every backup checksum, registry path and live preview before journaled writes;
it preserves unlisted/new slots and provides undo. A verified backup can be
retained across a PortMaster uninstall/reinstall, then explicitly restored to
the same reviewed mapping. Keep owner originals separately.

Uninstall stays with PortMaster; this tool has no deletion operation. Verify the
actual device save locations and rehearse external recovery before removing a
port. Do not remove an unverified directory on the strength of a source inventory.
