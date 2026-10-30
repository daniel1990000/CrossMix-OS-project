# First Smart Pro device session from Windows

The custom project is **RetroPass for TrimUI, dev20**, with the PSP interface on
pinned spruceOS/PyUI. The repository's CrossMix name is inherited. This guide
prepares the actual handheld; it does not install ordinary CrossMix or call the
computer preview a device image.

## What to do now

1. Back up the **entire current microSD** to Windows while no game is running.
   Use the preparation kit's copy-and-verify operation. Keep every game's files,
   saves, BIOS, images, emulator configurations and hidden files together. Do not
   format the card or rename game/save files.
2. If using USB Storage, leave the handheld in that mode while Windows copies.
   A cable must support data, and the storage must appear in File Explorer.
   A charge-only cable or the wrong USB port cannot expose the card.
3. Once the backup verifies, copy the supplied **Apps/SmartProCheck** folder into
   the card's existing **Apps** folder, producing
   **Apps/SmartProCheck/config.json**. Do not replace any existing folder of that
   name. Only this new app folder is added; no boot hook or OS file is replaced.
4. Safely eject the handheld's drive in Windows, then exit USB Storage through
   its existing controls. Open **Apps → Smart Pro Check** on the handheld.
   It may briefly show a blank screen and then return to Apps. It needs no
   network connection or Python installation. Do not start USB Storage while
   the check is running.
5. Reopen USB Storage. Open **Apps/SmartProCheck/reports/session-…** in Windows
   and copy the **whole session folder** onto the laptop. Each run creates a new
   folder, so previous results remain intact.
6. Share **baseline.txt only** for the next device step. Keep the
   **PRIVATE-internal-recovery** directory on your laptop; it can contain private
   configuration and should not be uploaded. If the session still contains
   **INCOMPLETE.txt**, the archive did not finish: retain the result and report
   that status instead of proceeding with installation.

The app definition follows the existing stock/CrossMix `Apps/*/config.json`
format (`label`, `icon`, `iconsel`, `launch`, `description`) reviewed from this
repository's inherited FileManager, Terminal and Reboot apps. The new launcher
uses `/bin/sh` and common BusyBox commands, with no inherited binary or hardware
script. Its host fixture tests pass; its actual target App launch and tools must
still be observed. If the app does not appear or does not produce a session,
report that result; do not run a different installer to make it appear.

## What the check collects

`baseline.txt` contains bounded model/firmware/kernel observations, card/root
filesystem types, presence of existing software directories, existence of
Python/readelf without executing them, and selected startup-file hashes. It
contains no ROM/save contents, process command lines, network settings, account
names or serial-number collection.

The private tar preserves existing `/usr/trimui/bin/runtrimui.sh`,
`runtrimui-original.sh`, `MainUI`, `/usr/trimui/scene` and `/bin/bash`, including
symlink text and tar metadata. `selection.txt` also records absent paths. These
are the startup/switch/shell inputs identified from pinned spruce v4.5.4's
`trimui/app/MainUI` and `SmartPro.sh`. The original app is archived only, never
executed or changed. Archive growth is capped by a shell file-size limit;
failures retain partial private data and an incomplete marker.

This is a selected **live-file preservation archive**, not a full internal flash
image or proof of consistent restoration. Symlinks are not dereferenced; their
targets and any additional installer write scope need separate review. No games,
emulators, firmware, radio services, clocks, input owners or boot files are
changed. The only output is the new app-local report directory.

The included original PNG icon depicts a check mark. The app's source is MIT.
The `--fixture-root` collector option is solely for host tests and labels all
results `host-fixture-not-device-evidence`; it cannot produce device evidence.

## What follows the baseline

The next step depends on the actual firmware, current card layout and recovery
access. The laptop's verified copy protects files, but recovery from a device
that cannot boot or expose USB needs a **microSD reader**. With only one card and
no reader, do not replace the current boot setup. Obtain a reader and preferably
a spare name-brand card before the custom device pilot. The original card can
then remain unchanged while a restored spare proves boot and save readback.

Pinned spruce first setup can modify the internal launcher and FN-switch files.
An SD-card swap does not reverse those changes. Review the collected original
files and a firmware-specific restoration route before that setup. Keep the
private original archive and the verified full-card backup off the handheld.

After actual recovery and runtime observations are reviewed, prepare the fixed,
exact-identity private runtime from [experimental-runtime.md](experimental-runtime.md).
Its first case is **view-only**: browse the PSP interface through the existing
PyUI owners, then return to classic. It admits no game launch, settings writes,
Resume or USB/power transition. The production profile remains disabled. Later
cases test an unchanged PSP/PS1 engine and copied saves, followed by the remaining
[device casebook](device-test-runbook.md).

No amount of Windows copying or host test success substitutes for those device
results. At this checkpoint no device boot, controls, return or restore result
has been recorded.
