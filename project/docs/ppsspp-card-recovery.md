# PPSSPP startup and button inspection

The owner reports that the original Smart Pro boots into PPSSPP, X/O do not
work, and the suggested power hold only sleeps the screen. The actual firmware,
card layout and active emulator have not been inspected. Do not infer card
corruption, erase the card, or install a different OS to discover the cause.

When the microSD reader is available, fully shut down the handheld, mount its
card in Windows and make the verified full-card backup with `START-HERE.cmd`.
If Windows requests formatting, cancel. Work from that backup's `card-files`
folder when possible.

Run **INSPECT-RECOVERY.cmd** (or choose recovery inspection in the setup menu).
Select the card root or backed-up `card-files` folder, then a laptop folder for
the report. The tool writes `recovery-inspection.json` in a new folder outside
the inspected tree. It never edits, renames or executes a file on the card.
The `.cmd` uses a process-only PowerShell policy and needs no administrator,
Python, Internet or working handheld menu.

The report lists bounded known config paths and hashes, selected numeric
Cross/Circle/Pause/navigation bindings, and known resume markers. It does not
emit ROM/save contents, recent-game filenames, achievement tokens, passwords,
unknown settings, startup-script contents or absolute source paths. Review the
report before sharing. Unknown startup hooks and per-game configurations are
outside its scope; finding one candidate does not establish that it is active.

## What source inspection establishes

| Installation clue | Source-established behavior | Recovery implication |
|---|---|---|
| `System/etc/crossmix.json` | The inherited CrossMix System Tools “Resume at boot - disable” action changes `RESUME AT BOOT` to numeric `0`. | If the actual installation and launcher confirm this route, a reviewed change to this one setting may disable resume. Keep the original file; do not replace its whole JSON with an empty/default config. |
| `spruce/flags/save_active.lock` and `lastgame.lock` | Pinned spruce runtime calls auto-resume when `save_active` is present. The helper stages the prior command from `lastgame.lock` for principal execution. | Only after confirming spruce and backing up, a reversible rename of the specific trigger can be reviewed to bypass one startup attempt. Never execute the marker's command from Windows and never delete a game/state file as a substitute. |
| `Saves/.config/ppsspp/PSP/SYSTEM/controls-SmartPro.ini` | Pinned spruce copies platform-specific controls and settings to `controls.ini`/`ppsspp.ini` on launch and copies them back afterward. | Deleting only `controls.ini` may do nothing. Preserve both active and platform-specific files; review the actual platform and known-good matching defaults before a reset. |
| `Emus/PSP/PPSSPP_<version>/.config/ppsspp/PSP/SYSTEM/` | Inherited CrossMix version launchers change into a selected PPSSPP directory and set `HOME` there. | Multiple configurations may coexist; the chosen launcher must identify which one actually governs the failing menu. |
| `ppsspp.ini` `AutoRun` | PPSSPP has its own `General.AutoRun` setting, distinct from the OS boot process. | `AutoRun=True` alone is not evidence of why the handheld boots into PPSSPP. Do not claim that changing it fixes boot. |

The scanner also checks several common stock-style locations as **candidates**.
Their presence does not certify a stock version or establish a complete search.
Missing explicit bindings may use built-in defaults. An empty or unrecognized
mapping is a review clue, not proof of the live input behavior.

No automatic reset is included: the appropriate repair depends on the actual
launcher, firmware and config files. The next useful input is the generated
inspection report. Any later repair should preserve exact preimages and change
only the reviewed setting/config, with no ROM, SAVEDATA, memory-card or state
file replacement. A normal boot and working menu still need physical testing.

## Source references and validation

- Spruce v4.5.4 commit `d45ff8dfe5756147522b04ae5863d17a90e88b54`:
  `spruce/scripts/runtime.sh` (save_active branch),
  `spruce/scripts/runtimeHelper.sh` (auto_resume_game),
  `spruce/scripts/helperFunctions.sh` (FLAGS_DIR), and
  `spruce/scripts/emu/lib/ppsspp_functions.sh` (load/save_ppsspp_configs).
- Inherited CrossMix files at `c4550eec4e784dd67a620336fcee40599593b726`:
  `Apps/SystemTools/Menu/EMULATORS##RESUME AT BOOT (state)/Resume at boot - disable.sh`,
  `Emus/PSP/ppsspp_1.17.1_gl.sh`, and its versioned `controls.ini`.
- PPSSPP v1.20.3 commit `d357e6a32934800d3d80b49f910a603e1b069751`:
  `Core/Config.cpp` defines `AutoRun`, `AutoLoadSaveState` and `ButtonPreference`.

Nine functional fixture checks pass under Linux PowerShell 7.4.6, including
source preservation, withheld private values, empty-card reports, overlapping
output rejection, oversized/malformed files, symlinks, versioned config paths
and standalone entry-point execution. Actual Windows 5.1 and the owner's card
remain untested. The tool does not enable the custom interface or certify a
recovery result.
