TRIMUI SMART PRO - WINDOWS CARD HELPER

This is for preparing your existing card for our custom RetroPass PSP interface.
It is NOT a CrossMix installer and does not activate the development OS.

1. Extract this folder on your Windows laptop.
2. Connect the Smart Pro with a data-capable USB cable and open its existing USB
   Storage app. Leave it in that app; do not run games/sync while Windows has the
   card mounted. A microSD card reader also works if you have one.
3. Open This PC. Check the card drive letter and capacity. If Windows asks to
   format the card, cancel. If no card drive appears, stop and resolve the cable,
   port or USB Storage connection first.
4. Double-click START-HERE.cmd. Select that drive letter and confirm it.
5. Choose 2 to back up ALL files, then press Enter to use your Documents folder,
   or enter another existing folder on the laptop. You need enough free space for the used
   card space, plus 5% or 1 GiB spare. Large collections may take hours: every
   source file is copied and both source and copy are read for SHA-256 checking.
6. Wait for BACKUP VERIFIED. Keep the entire new TrimUI-date folder. Its
   card-files folder contains the exact relative file layout, including hidden
   files. Reports are alongside it. A failed/partial backup is never success.
7. Safely eject the drive in Windows, then exit the handheld USB Storage app.

Choose 1 instead for a quick layout inventory. This reads names/counts, not ROM,
save or configuration contents. It does not make a backup. Both modes only read
from the card. The helper never formats, deletes, renames or writes card files.
No administrator account, Python, installation or Internet connection is needed.
The CMD uses a process-only PowerShell execution policy; it does not change the
machine policy. Company policy can still prevent running it.

Keep backups and reports private. Backup files can include network credentials
and other personal configuration. Reports may identify games by their paths.
Nothing is uploaded. Do not share the whole backup or private manifest.

Limits: this copies accessible card files, not internal handheld firmware,
partitions, boot sectors, NTFS permissions or alternate data streams. It stops
on unreadable files, links/junctions, errors or detected source changes. If a
protected folder cannot be read, it does not silently skip it. A verified copy
is not proof that a restored card boots or that all saves load. A card-layout
clue cannot establish the exact OS, model or firmware. Save folders are clues,
not an automatic migration map. Existing PSP/PS1 saves remain in their original
locations inside the backup; no conversion or remapping is performed.

With only one card and no reader, complete the backup but do not reformat or
install the development OS. A boot failure could remove USB Storage access.

Developer check: powershell -NoProfile -File tests/Test-Card-Helper.ps1
The functional fixture suite is designed for PowerShell 5.1+; Linux PowerShell
results do not certify the Windows shell or the physical USB connection.
