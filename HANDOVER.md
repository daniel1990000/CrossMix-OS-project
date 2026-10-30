# TrimUI handover — RetroPass in the PSP UI, dev20

## Windows/USB preparation — 30 October 2026

The owner is ready with an original Smart Pro and Windows laptop; their games
are on their only microSD. They have no card reader or spare card. USB Storage
support is documented by TRIMUI, but their actual cable, mounted drive and
firmware have not yet been observed. Do not mistake this for an attached device.

Start with [the Windows helper](project/windows/README.txt) and
[the actual-device steps](project/docs/windows-device-pilot.md). The new
`project/windows/START-HERE.cmd` backs up and SHA256-checks every accessible
card file onto the laptop without writing to the card. It also provides a
read-only layout inventory. The optional `Apps/SmartProCheck` collector under
`project/device-preflight/` records baseline observations and preserves selected
internal startup files in a separate private archive. The guide stages only
this new app folder after the backup; it does not install or activate dev20.
Keep private archives on the owner's laptop; request only `baseline.txt`.

Existing dev20 was freshly certified from clean `c4550eec4e784dd67a620336fcee40599593b726`:
all 1,254 strict checks passed, package smoke/rollback passed and the source
inventory matches the prior dev20 exactly. The new preparation tools have
10 PowerShell fixture checks and 6 shell-collector fixture checks; actual
Windows 5.1/USB and target BusyBox remain untested. See
[preparation evidence](project/evidence/windows-preparation-20261030/).

Next external input: USB-mounted card backup outcome and actual device baseline.
Obtain a microSD reader before replacing the current boot setup; prefer a spare
card for restore/boot tests. The rebuilt dev20 remains a computer preview, and
all device/profile gates and physical 0/13 status remain unchanged. No custom
OS, base distribution, firmware or emulator has been installed on the owner's
handheld. No game/save migration has occurred. The following is the retained
dev20 implementation handover.

29 October 2026. [Merged PR #5](https://github.com/daniel1990000/CrossMix-OS-project/pull/5), merged into `main` at `da4b54b522cdeb94fa06909654475c7f8c5b3e14`. The merge tree exactly matches the checked PR head; GitHub host checks and package build passed in [run 40817261850](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/40817261850). [Merge evidence](project/evidence/retropass-psp-dev20/merge-record.json) preserves the exact identities. The user asked to adapt the actual RetroPass port into the PSP UI. This continuation follows dev19 at `39e838c92b284f4c445e69e0669f0646cfa42363`; its [historical handover](HANDOVER-HISTORY-through-dev19.md) and evidence retain their own tested identity.

Fresh standalone and qualified embedded sessions now use the PSP wave background, horizontal category crossbar and vertical game list. The GPL-scoped `retropass/psp.py` adapts source cover proportions/focus into a white PSP presentation, with a focused-game cover panel and up to five noninteractive source-backed library previews on eligible home rows. Above 120% text size the side panel yields its space to readable list text. Native keyboard/dialog controls remain directional within their modal view.

The actual translated `Playlist.cs` recent-first selector now runs in immutable snapshots. Native recent order, stable IDs, current metadata generations, favorite membership and selected-system scope determine previews. The already-loaded library is reused; previews do not add backend queries, launch capabilities or mutable collection ownership. The translated EmulationStation parser continues to supply library labels/artwork.

All 177 original upstream files are unchanged. The added GPL PSP runtime participates in signed required-module inventories and corresponding source delivery. Existing saved appearance choices are preserved. `--theme psp` explicitly previews this presentation without changing preferences. The current descriptor is `smartpro-retropass-0.1.0-dev20`.

Read [current status](project/handover/LATEST.json), [port documentation](project/docs/retropass-trimui.md) and [dev20 evidence](project/evidence/retropass-psp-dev20/). Dev19 test/build counts do not certify this continuation. Clean checked implementation: `25d594c5ca26b9d1b927d32d44f04cef0697c420`. All 1,254 strict checks pass with zero failures/errors/skips against five exact pinned source trees. The 255-file installed preview and 429-file source inventory build/smoke successfully; both ZIPs rebuild byte-identically without Git. The installed probe verifies PSP default and actual calls into both GPL PSP rendering and source landing selection. New receipts identify these captured bytes separately from later evidence metadata commits.

The existing device/profile gates remain disabled, physical acceptance is 0/13, and no emulator binary or save location changes. Published dev16 assets are unchanged. Vice City testing remains in its separate chat. Next: qualify the exact installed frontend on TG5040 through the existing device/recovery casebook.
