# RetroPass for TrimUI

RetroPass dashboard and source port for the original TrimUI Smart Pro **TG5040**, built around pinned spruceOS v4.5.4/PyUI and its existing native owners.

**Current development: dev19, RetroPass for TrimUI.** The complete 177-file RetroPass upstream source is imported at a pinned revision, with a working Python/SDL port of its dashboard and EmulationStation metadata reader. Fresh previews use the dark horizontal dashboard with green focus borders, smooth cover scrolling and shoulder-button category switching. Existing saved appearance is preserved. [Port details and source mapping](docs/retropass-trimui.md) distinguish the running Linux adaptation from the preserved Windows UWP source.

Run `PYTHONPATH=project python3 -m psp_shell --demo`. Left/right browse covers; up/down or L/R switch categories (desktop Q/E). Confirm opens the existing game dialog. Settings → Dashboard style switches between RetroPass and the PSP crossbar with preview/apply/Undo. `--theme retropass` or `--theme psp` overrides the preview without changing saved preferences. The earlier dev18 library, collections, accessibility and backup features remain available.

[Dev16 remains the published computer preview](https://github.com/daniel1990000/CrossMix-OS-project/releases/tag/smartpro-host-0.1.0-dev16), with its original tag, assets and matching source. Dev18 does not change that publication. This is host software: all device/profile gates remain disabled and 0/13 physical acceptance areas have run. Read [the current handover](../HANDOVER.md), [status record](handover/LATEST.json) and [master register](docs/master-plan-2026-10-22.md) for the exact development branch and remaining qualification.

## Browse and organize

Use **Start** (desktop **Tab**) for Library tools. Search stays within All games, Favorites, Continue or the selected collection. Choose any available system, clear filters, change sort order, move between pages or jump to a letter. Surprise chooses an available game from the complete current result and opens its confirmation card; it does not launch automatically. Continue keeps native recent order by default.

**Games → Collections** presents existing native collections. Membership and creation remain in the existing native Game options/Collections routes when those routes are available. Mounted-card inspection only reads existing collections. Returning from native options refreshes metadata/artwork and keeps selection by game identity, including later pages.

**Settings → Controls & help** explains the active mode and physical controls. Text size includes 175%; footer hints and status scale too. Game information puts warnings before details and keeps disc details separately reachable. Empty results offer relevant search/filter/refresh actions.

## Named offline backup history

History names existing payloads produced by the recovery tools. It never discovers active emulator save paths, creates emulator states or restores over live data. Capture time, registration time and last-check time are separate; a prior successful check is historical until another check completes.

Register a retained payload with a catalog outside the inspected card and payload:

```sh
PYTHONPATH=project python -m tools.backup_catalog --catalog /external/ui-state/backups.json --inspected-card /mounted/card register --payload /external/retained-backup --label "Before changing settings"
PYTHONPATH=project python -m psp_shell --sd-root /mounted/card --backup-catalog /external/ui-state/backups.json
```

Open **Settings → Backups & recovery → Backup history** to inspect, rename a label, check bytes again or remove an entry from history. Removal keeps the payload. Checks show progress and can be cancelled; the native input and launch owners remain unchanged. A stopped check cannot become a successful check. The catalog CLI also supports list/detail/verify, generation-checked edits and explicit interrupted-edit recovery. Its restore command delegates to the existing verifier and accepts only a new expendable directory outside protected roots.

The catalog is bounded to 1 MiB/1,000 entries. Labels and receipts live outside payloads, which remain immutable. No complete-save-coverage, independent-media or physical-restore claim follows from matching bytes. [The recovery runbook](docs/recovery.md) retains the operator procedure.

## Run the preview

Use Python 3.9 or later, system SDL2 and libsodium. On Debian/Ubuntu the runtime packages are `libsdl2-2.0-0` and `libsodium23`.

Complete host certification also requires `libsdl2-image-2.0-0` and `libsdl2-ttf-2.0-0` to exercise the embedded artwork and text paths against real host libraries. Device libraries are kept at the existing spruce versions. See [artwork formats and limits](docs/artwork-formats.md).

```sh
python3 -m venv /tmp/smartpro-venv
/tmp/smartpro-venv/bin/pip install -r project/requirements-dev.txt
PYTHONPATH=project /tmp/smartpro-venv/bin/python -m psp_shell --demo
```

Use arrow keys or a controller to navigate. RetroPass uses horizontal item navigation; the PSP crossbar retains vertical item navigation. Enter confirms, Escape returns, and the on-screen hints follow the selected physical Confirm button. The sample titles and state cards are fixtures; no games are included or launched.

The controller keyboard and essential footer help scale with text size through 175%, with physical Confirm/Cancel/Delete/Find hints. Use Games → Refresh library (or F5) after changing covers; refresh preserves page/focus and clears stale artwork. See [interface accessibility](docs/interface-accessibility.md) and the [dev18 host captures](evidence/dev18-library-backups-20261026/).

```sh
PYTHONPATH=project /tmp/smartpro-venv/bin/python -m psp_shell --demo --headless --frames 2 --screen library --screenshot /tmp/smartpro-library.png
PYTHONPATH=project /tmp/smartpro-venv/bin/python -m psp_shell --sd-root /path/to/mounted-spruce-card --state-dir /tmp/smartpro-inspection
```

Large-library, timing and port host tasks U04, D04 and P01–P03 are complete. See [measurement tools](docs/host-measurement.md) and [port preparation/save preservation](docs/ports-preparation-and-saves.md). Device qualification remains pending.

The second command inspects a card without launching its scripts or modifying its data. State, screenshot and report outputs must be outside the inspected card. Standalone rendering uses Pillow. Embedded rendering can reuse PyUI's SDL_ttf/SDL_image and existing SDL renderer without Pillow, a second input owner, or global SDL shutdown.

## Implemented source

| Area | Current behavior |
|---|---|
| Interface | Games, Continue Playing, Tools, Settings; browse/search/favorites; dialogs and original waves; text scaling, contrast, motion/sound preferences; controls and PPSSPP appearance preview/apply/Undo; credits. |
| Library | Read-only source/card inspection and injected existing PyUI models. Existing platform filtering, ROM identity and launch paths are preserved. |
| Runtime | Exact-source main UI/model/game/principal integration; foreground descendant cleanup through a Linux child subreaper; sealed staged commands, correlated returns, classic fallback and shared-renderer ownership. Fixed runtime configuration defaults to unavailable. |
| Settings | Common brightness, volume, Wi-Fi and Bluetooth controls through initialized source authorities; fixed advanced/per-game routes. One journaled PPSSPP controls/appearance transaction preserves verified per-game overrides, with conflict detection, recovery and Undo. |
| PPSSPP | Independent SDL native-menu controls, matching native themes, completed-state export and native load acknowledgement. Full PPSSPP/FFmpeg source cross-build and recursive SDK audit pass. Authenticated checkpoint transfer supports typed Resume across fresh source processes; installed profiles remain disabled. See [state integration](ppsspp/state-session.md). |
| RetroArch / IGM | Separate standard-menu, spruce IGM controls and appearance adapters; optional actual IGM C source extension and full engine build passing a 23-object SDK audit. Gameplay remaps stay with the engine. See [IGM integration](retroarch/README.md). |
| Reliability | Four pinned fixes for launcher quoting, TLS failure, extractor status and USB staging failure; optional scoped PPSSPP wrapper patch. Private source composition verifies preimages, resulting hashes, signatures and restoration backups. |
| Data and recovery | Read-only inventory and [installed loader/mapped-library evidence](docs/installed-runtime-evidence.md); offline migration; signed scoped overlays; pinned per-title port/runtime inventory and existing launch-token reuse; owner-data staging and Undo; [device acceptance recorder](docs/device-test-runbook.md). |

Continue Playing displays existing recents. Recorded checkpoints say that verification is required; open their information to check them. Resume requires authenticated engine/game/state identity, stopped writers and a qualified profile. The dialog distinguishes historical checkpoint verification from the current check, including after a later save fails. Actual save-completion time is unavailable. Existing power, sleep, USB, networking and advanced menus remain owned by spruce. Native emulator and third-party screens retain their engine layouts; the [coverage register](docs/feature-coverage.md) records those visual exceptions and pending physical tests.

## Check and package

Provide untouched source checkouts at the exact pins in [the spruce lock](../docs/spruce-source-lock.json), [PPSSPP lock](ppsspp/source-lock.json), [spruce RetroArch recipe lock](retroarch/source-lock.json), [Celeste patch lock](ports/celeste-fix.lock.json) and [PortMaster GUI text lock](profiles/ports-sources.lock.json). The certification command rejects missing or changed pinned references and any skipped test. Individual unittest invocations can still skip source-dependent cases and cannot count as a complete certification.

```sh
PYTHON=/tmp/smartpro-venv/bin/python SPRUCE_SOURCE_ROOT=/path/to/spruce-v4.5.4 PPSSPP_SOURCE_ROOT=/path/to/ppsspp-v1.20.3 SPRUCE_RA_SOURCE_ROOT=/path/to/spruce-ra-recipe PORTS_SOURCE_ROOT=/path/to/portmaster-new PORTMASTER_SOURCE_ROOT=/path/to/portmaster-gui sh project/dev/check.sh
python3 project/packaging/dev_release.py --output /tmp/smartpro-development --include-source --smoke-python /tmp/smartpro-venv/bin/python
```

The packaging command and CI use [the current release descriptor](packaging/current-release.json) for the release ID, source timestamp and selected scope. Generated signed metadata records the exact frontend commit, modified-checkout status and actual source inventory. Historical native hashes remain unselected references and do not enable device profiles.

Source checks need `git`, host C/C++ compilers with C++17 support, and `readelf` from binutils. They compile selected real patched functions with explicit fixtures. The separate [complete PPSSPP state-session build](evidence/ppsspp-complete-state-build.json) compiles the full native engine and pinned FFmpeg; it passes the 16-object SDK audit. The [complete RetroArch/IGM build](evidence/retroarch-igm-build.json) passes its 23-object SDK audit. Cross-compilation and host acceptance supply separate evidence. Actual device compatibility remains unqualified. Engine binaries and complete recipe/source archives stay private. [Development release instructions](docs/development-release.md) explain original-only signing, deterministic rebuilds, installed-payload smoke checks and outputs. GitHub Actions runs host checks and uploads the original development artifacts.

See [full-system coverage](docs/feature-coverage.md), [qualified binding](bridge/README.md), [recovery](docs/recovery.md), [packaging](packaging/README.md), and the saved [evidence](evidence/) for scope and remaining qualification. There is no measured hardware speed or battery improvement at this checkpoint.

## Licences

The RetroPass Python adaptation in `retropass/` retains GPL-2.0-only, with the complete upstream source and licence in `vendor/retropass/`. [The port notice](retropass/NOTICE.txt) records its origin and changes. Signed previews and source archives include the corresponding source and GPL notices. Existing original Python helpers retain [MIT](LICENSE). Spruce/PyUI source patches retain their upstream terms and notices. PPSSPP patches/fixtures retain [GPL-2.0-or-later](ppsspp/NOTICE.md), and RetroArch patches/fixtures retain [GPL-3.0-or-later](retroarch/NOTICE.md). The bundled Noto Sans font uses [OFL](assets/fonts/OFL.txt). The [owner-confirmed permission record](evidence/completion-20261023/owner-permission.json) covers private noncommercial source work. The [rights register](docs/release-rights.md) retains unresolved public recipe/SDK distribution questions. No Sony graphics, commercial game data, firmware or emulator binaries are included in the new payload.
