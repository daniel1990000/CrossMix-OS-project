# Recovery and offline data migration

This offshoot targets **original TrimUI Smart Pro, TG5040**, with spruceOS v4.5.4 source commit `d45ff8dfe5756147522b04ae5863d17a90e88b54`. Current implementation evidence is from host tests and a desktop preview. Device integration, source-use clearance, internal restoration, sleep/power/USB, game handoff and save integrity remain separate gates. The default package profile refuses device activation. Package selection does not install a boot hook or start the presentation.

## Preserve the working device first

Keep the working CrossMix card untouched. Use a separate branded spare card for spruce and another offline backup of all original ROMs, BIOS, battery saves, memory cards, states, screenshots, application data and configuration. Verify the copied files and a restoration before experimenting. A configuration archive is not a full-card backup. Stop emulators and synchronization before a save snapshot; never copy a live save and call it verified.

spruce's first setup can change internal storage: `trimui/app/MainUI` preserves internal `runtrimui.sh` as `runtrimui-original.sh`, installs a replacement and reboots. SmartPro initialization can copy `/bin/bash` and apply FN switch actions in `/usr/trimui/scene`. Capture exact original files, hashes, ownership and firmware-specific restoration instructions before running that installer. An SD-card swap or package rollback does not reverse these internal modifications.

The supplied read-only collector records hashes and observations, **not restoration payloads**:

```sh
python3 project/tools/inventory.py --root /path/to/mounted-root-copy --sd-root /path/to/spruce-card --profile project/packaging/profiles/spruce454-tg5040-development.json --output /tmp/smartpro-inventory.json
```

On-device collection requires an already available Python 3 and explicit output. It never instantiates PyUI list/config managers, runs launcher scripts, captures process arguments/environment, reads Wi-Fi/service secrets or collects ROM/save contents. Unknown model/firmware/source observations stay unknown; `--confirm-model`/`--confirm-firmware` retain operator-assertion provenance. Exact locked source-file hashes are checked independently of version labels. Full installed-release identity and physical qualification are not inferred from a subset of matching contracts.

## Offline presentation fallback

The project frontend and package tool share `App/PSPMode/state/force-classic`. To request classic mode without the new graphics code, place a regular file with that name on the card using a card reader. This affects the project recovery selector only when its integration is installed; it is not an upstream spruce boot flag. Foreground ownership still takes priority: a surviving game must finish or be accounted for before any UI is started. Never delete foreground handoff records to force a menu over a running game.

The package tool restores the previous package selector without touching ROMs, saves, emulators or unrelated settings:

```sh
python3 project/packaging/overlay.py rollback --card /path/to/card --public-key /trusted/release-public-key
```

Rollback first sets `force-classic`, verifies the retained signed release and writes a new selector generation. It can recover a prepared/interrupted activation or a damaged current selector using the checksummed journal/last-good record. It keeps newer gameplay saves. If a release/key is revoked or damaged, use a separately trusted recovery package or restore the verified project directory from backup; do not bypass signature checks. Keep `force-classic` until the failing release is diagnosed and an explicit tested switch is appropriate.

If `.package-lock` remains after interruption, ensure no package process is active, preserve the directory/journals, and remove only the empty stale lock with a card reader before retrying. Do not delete release/state directories blindly. FAT/exFAT directory durability and power-loss behavior still need spare-card tests.

Upstream spruce v4.5.4 runs SmartPro directly through `runtime.sh`; its optional `boot/session.sh` crash guard is only enabled for opted-in Flip by the inspected updater. Do not assume `boot_to_stock.lock` provides TG5040 recovery. Upstream updates replace files in place, with MD5 feed checks and selected configuration backup/restore; this is distinct from project signed-overlay rollback. Do not run upstream OTA and project activation concurrently. Recheck locked source contracts after any update.

For original-device firmware recovery, obtain the manufacturer's **TG5040** recovery image and instructions from <https://github.com/trimui/firmware_smartpro/releases/tag/v1.1.1>. The 20251128 recovery ZIP's published SHA256 is `b1278652eddfd0adcf7fe6733ca3ee5ddf319ee11eae77c9a8ced99d0f64b059`. Firmware restoration is a separate operation from UI recovery and may reset internal settings; no tool here flashes it. A30, Brick, Smart Pro S and Flip recovery images/instructions are not substitutes.

## CrossMix → spruce migration on offline copies

`migrate_crossmix.py` never changes its CrossMix source. It reads legacy `rompath` records from `Roms/favourite2.json` and `Roms/recentlist.json`, produces only PyUI's accepted `rom_file_path`, `game_system_name`, optional `display_name` fields, and retains original unknown fields in a separate project-owned provenance journal. Existing target entries retain their order/metadata. Missing ROMs, unmapped systems and malformed/unknown target formats become review entries; they are not pruned.

Make an explicit selection file, for example:

```json
{
  "systems": {"GBA": "GBA"},
  "battery_saves": [
    {
      "source": "RetroArch/.retroarch/saves/mGBA/Game.srm",
      "destination": "Saves/saves/mGBA/Game.srm",
      "compatibility": {
        "reviewed": true,
        "kind": "battery-save",
        "evidence": "Owner verified identical game and compatible mGBA native SRAM format on copies"
      }
    }
  ]
}
```

Per-core directory names, game identity and compatibility must be confirmed from the selected installation. No folder-name guess establishes compatibility. Preview reads no ROM contents. Battery extensions are bounded and explicit; there is no conversion/import of emulator states, `.auto`, PPSSPP states or unknown formats. PSP SAVEDATA and standalone-specific folders need their separately proved import procedure. Keep them backed up rather than renaming them to battery-save extensions.

```sh
python3 project/tools/migrate_crossmix.py preview --crossmix /path/to/crossmix-copy --spruce /path/to/spruce-spare --selection /tmp/selection.json --output /tmp/migration-preview.json
python3 project/tools/migrate_crossmix.py apply --plan /tmp/migration-preview.json --transaction import-1
python3 project/tools/migrate_crossmix.py undo --transaction /path/to/spruce-spare/App/PSPMode/state/migrations/import-1
```

Review the preview's operations and unresolved entries before `apply`. The plan binds exact source and destination hashes; stale files abort rather than overwrite. Different existing battery saves require explicit per-save `replace_existing: true` in the selection and receive hash-checked backups. A prepared journal enables undo after partial writes. Undo checks every target before writing and refuses to overwrite newer saves or other subsequent edits; preserve that newer data and resolve the conflict manually. Migration is an offline card operation, not a live emulator feature.

## Local support export

```sh
python3 project/tools/support_bundle.py --inventory /tmp/smartpro-inventory.json --diagnostic /tmp/selected-project-log.json --output /tmp/local-support.json
```

Only explicitly selected bounded files are read. The exporter strips secret fields, addresses, user-home identities, serial numbers and user-data paths, and never uploads anything. Review the output before choosing to share it. Do not attach spruceBackup archives: they can contain SSH keys, network/service configuration and other private state. The author-notification draft is also local and unsent; it does not clear the PyUI source-use gate.
