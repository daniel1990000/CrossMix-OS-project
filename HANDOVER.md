# TrimUI handover — RetroPass in the PSP UI, dev20

29 October 2026. [Draft PR #5](https://github.com/daniel1990000/CrossMix-OS-project/pull/5), branch `feat/retropass-trimui`. The user asked to adapt the actual RetroPass port into the PSP UI. This continuation follows dev19 at `39e838c92b284f4c445e69e0669f0646cfa42363`; its [historical handover](HANDOVER-HISTORY-through-dev19.md) and evidence retain their own tested identity.

Fresh standalone and qualified embedded sessions now use the PSP wave background, horizontal category crossbar and vertical game list. The GPL-scoped `retropass/psp.py` adapts source cover proportions/focus into a white PSP presentation, with a focused-game cover panel and up to five noninteractive source-backed library previews on eligible home rows. Above 120% text size the side panel yields its space to readable list text. Native keyboard/dialog controls remain directional within their modal view.

The actual translated `Playlist.cs` recent-first selector now runs in immutable snapshots. Native recent order, stable IDs, current metadata generations, favorite membership and selected-system scope determine previews. The already-loaded library is reused; previews do not add backend queries, launch capabilities or mutable collection ownership. The translated EmulationStation parser continues to supply library labels/artwork.

All 177 original upstream files are unchanged. The added GPL PSP runtime participates in signed required-module inventories and corresponding source delivery. Existing saved appearance choices are preserved. `--theme psp` explicitly previews this presentation without changing preferences. The current descriptor is `smartpro-retropass-0.1.0-dev20`.

Read [current status](project/handover/LATEST.json), [port documentation](project/docs/retropass-trimui.md) and [dev20 evidence](project/evidence/retropass-psp-dev20/). Dev19 test/build counts do not certify this continuation. New receipts identify the clean implementation and captured bytes separately from later evidence metadata commits.

The existing device/profile gates remain disabled, physical acceptance is 0/13, and no emulator binary or save location changes. Published dev16 assets are unchanged. Vice City testing remains in its separate chat. Next: review the updated host preview and then qualify the exact installed frontend on TG5040 through the existing device/recovery casebook.
