# Smart Pro PSP experience

Development source for an original TrimUI Smart Pro **TG5040** offshoot of spruceOS v4.5.4 and its shipped PyUI. The interface now follows the classic PSP crossbar: anchored horizontal categories, a vertical selection column, white pictograms, broad blue waves and translucent options. It uses original graphics and PPSSPP's supported native UI features. Read [the handover](../HANDOVER.md) and [complete plan](../TRIMUI_PLAN.md) before continuing.

See the [new screenshots](evidence/psp-design/gallery.png), [actual PSP comparison](evidence/psp-design/comparison.png), and [visual design/source notes](docs/psp-visual-design.md). All new captures are actual SDL host renders. PlayFieldPortal informed category positioning and bounded row motion; EmuCoreA informed cover presentation. The matching PPSSPP palette uses its pinned official theme parser.

This checkpoint runs on a computer and has injected-runtime tests. It is not a device-ready SD image. Device activation remains blocked by the shipped profiles.

The [software validation fixes](docs/software-hardening-2026-10-23.md)
address source certification, disposable probe cleanup, device evidence chronology,
revocation receipts and trust report readback. The current descriptor selects
**smartpro-psp-0.1.0-dev13**, an original-only host preview.

The earlier [remaining-plan software completion](docs/completion-2026-10-23.md)
implements the conditional private viewing route, real backup/restore payloads,
structured casebook review, exact native notice review and original-only release
handoff. Its dev12 build and retention receipts retain their historical identities.
The owner confirms author permission for private noncommercial source work;
the attestation is retained privately. No message was sent by this work.

The master register has 14 completed scoped rows: 13 host engineering rows
including D01, plus owner-confirmed R05 private source use. Zero of 13 physical
acceptance areas have run. Actual device recovery/inventory, qualification,
precise public native distribution rights and operational release custody remain
open. The fixed selectors and production/profile gates remain unavailable.
Exact certification, packaging, source identities and retained readbacks are in
[the completion evidence](evidence/completion-20261023/verification.json).

## Run the preview

Use Python 3.9 or later, system SDL2 and libsodium. On Debian/Ubuntu the runtime packages are `libsdl2-2.0-0` and `libsodium23`.

Complete host certification also requires `libsdl2-image-2.0-0` to exercise the embedded artwork path against a real host SDL_image. Device libraries are kept at the existing spruce versions. See [artwork formats and limits](docs/artwork-formats.md).

```sh
python3 -m venv /tmp/smartpro-venv
/tmp/smartpro-venv/bin/pip install -r project/requirements-dev.txt
PYTHONPATH=project /tmp/smartpro-venv/bin/python -m psp_shell --demo
```

Use arrow keys or a controller to navigate. Enter confirms, Escape returns, and the on-screen hints follow the selected physical Confirm button. The sample titles and state cards are fixtures; no games are included or launched.

The controller keyboard scales with text size, provides title punctuation and shows physical Confirm/Cancel/Delete/Find hints. Use Games → Refresh library (or F5) after changing covers; refresh preserves page/focus and clears stale artwork. See [interface accessibility](docs/interface-accessibility.md) and the [new host captures](evidence/ui-polish/).

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

Continue Playing displays existing recents. Resume requires authenticated engine/game/state identity, stopped writers and a qualified profile. The dialog shows the original checkpoint verification time, including after a later save fails. Actual save-completion time is unavailable. Existing power, sleep, USB, networking and advanced menus remain owned by spruce. Native emulator and third-party screens retain their engine layouts; the [coverage register](docs/feature-coverage.md) records those visual exceptions and pending physical tests.

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

New original Python helpers use [MIT](LICENSE). Spruce/PyUI source patches retain their upstream terms and notices. PPSSPP patches/fixtures retain [GPL-2.0-or-later](ppsspp/NOTICE.md), and RetroArch patches/fixtures retain [GPL-3.0-or-later](retroarch/NOTICE.md). The bundled Noto Sans font uses [OFL](assets/fonts/OFL.txt). The [owner-confirmed permission record](evidence/completion-20261023/owner-permission.json) covers private noncommercial source work. The [rights register](docs/release-rights.md) retains unresolved public recipe/SDK distribution questions. No Sony graphics, commercial game data, firmware or emulator binaries are included in the new payload.
