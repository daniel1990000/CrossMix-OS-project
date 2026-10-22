# Smart Pro PSP experience

Development source for an original TrimUI Smart Pro **TG5040** offshoot of spruceOS v4.5.4 and its shipped PyUI. The interface uses original graphics, a four-category layout, and PPSSPP's native UI features where appropriate. Read [the handover](../HANDOVER.md) and [complete plan](../TRIMUI_PLAN.md) before continuing.

This checkpoint runs on a computer and has injected-runtime tests. It is not a device-ready SD image. Device activation remains blocked by the shipped profiles.

## Run the preview

Use Python 3.9 or later, system SDL2 and libsodium. On Debian/Ubuntu the runtime packages are `libsdl2-2.0-0` and `libsodium23`.

```sh
python3 -m venv /tmp/smartpro-venv
/tmp/smartpro-venv/bin/pip install -r project/requirements-dev.txt
PYTHONPATH=project /tmp/smartpro-venv/bin/python -m psp_shell --demo
```

Use arrow keys or a controller to navigate. Enter confirms, Escape returns, and the on-screen hints follow the selected physical Confirm button. The sample titles and state cards are fixtures; no games are included or launched.

```sh
PYTHONPATH=project /tmp/smartpro-venv/bin/python -m psp_shell --demo --headless --frames 2 --screen library --screenshot /tmp/smartpro-library.png
PYTHONPATH=project /tmp/smartpro-venv/bin/python -m psp_shell --sd-root /path/to/mounted-spruce-card --state-dir /tmp/smartpro-inspection
```

The second command inspects a card without launching its scripts or modifying its data. State, screenshot and report outputs must be outside the inspected card. Standalone rendering uses Pillow. Embedded rendering can reuse PyUI's SDL_ttf/SDL_image and existing SDL renderer without Pillow, a second input owner, or global SDL shutdown.

## Implemented source

| Area | Current behavior |
|---|---|
| Interface | Games, Continue Playing, Tools, Settings; browse/search/favorites; dialogs and original waves; text scaling, contrast, motion/sound preferences; controls and PPSSPP appearance preview/apply/Undo; credits. |
| Library | Read-only source/card inspection and injected existing PyUI models. Existing platform filtering, ROM identity and launch paths are preserved. |
| Runtime | Fixed action registry, once-only handoffs, foreground uncertainty records, classic fallback and shared-renderer ownership. A trusted initialized-owner binding refreshes live evidence and correlates return receipts; the actual qualified source caller/thread lifecycle and principal return authority remain outstanding. |
| Settings | Preview, journaled apply, conflict detection, crash recovery and targeted undo. Emulator changes require a qualified executable/profile and stopped writers. |
| PPSSPP | Actual v1.20.3 source patch for independent SDL native-menu Confirm/Back, executable source acceptance harness, matching original themes and transactional adoption helper. The [separate candidate builder](ppsspp/build-candidate.md) checks pinned source/SDK inputs and every selected spruce patch before cross-compiling. See [PPSSPP integration](ppsspp/README.md) and [reuse map](ppsspp/reuse-map.md). |
| Reliability | Four exact-source spruce patches: launcher path quoting, verified TLS download failure handling, extractor exit status, and refusal of mounted-card USB export after staging failure. They remain separate reviewable patches. |
| Data and recovery | Read-only inventory and redacted support bundles; offline CrossMix favorites/recents and approved battery-save migration; signed scoped overlays with rollback; port owner-data staging and undo; read-only process benchmarks. |

Continue Playing displays existing recents. Real Resume requires verified game/engine/state identity and a successful state lifecycle; a recent entry alone does not qualify. Existing power, sleep, USB, networking and advanced menus remain owned by spruce. Native emulator screens retain their engine behavior; full visual/control parity still needs work.

## Check and package

Provide untouched source checkouts at the exact pins in [the source lock](../docs/spruce-source-lock.json) and [PPSSPP lock](ppsspp/source-lock.json). Source-dependent checks otherwise skip and cannot count as a complete pass.

```sh
PYTHON=/tmp/smartpro-venv/bin/python SPRUCE_SOURCE_ROOT=/path/to/spruce-v4.5.4 PPSSPP_SOURCE_ROOT=/path/to/ppsspp-v1.20.3 sh project/dev/check.sh
python3 project/packaging/dev_release.py --output /tmp/smartpro-development --include-source --smoke-python /tmp/smartpro-venv/bin/python
```

The PPSSPP checks also need `git` and `g++` with C++17 support. They compile selected real patched functions with narrow fixtures. The separate complete PPSSPP/FFmpeg PowerVR source build passes the read-only SDK dependency inventory; actual device compatibility remains unqualified. Its executable and full recipe/source archive stay outside the development overlay and public artifacts while distribution rights remain unresolved. [Development release instructions](docs/development-release.md) explain signing, deterministic rebuilds, installed-payload smoke checks and outputs. GitHub Actions runs checks and uploads the development artifacts.

See [full-system coverage](docs/feature-coverage.md), [qualified binding](bridge/README.md), [recovery](docs/recovery.md), [packaging](packaging/README.md), and the saved [evidence](evidence/) for scope and remaining qualification. There is no measured hardware speed or battery improvement at this checkpoint.

## Licences

New original Python helpers use [MIT](LICENSE). Spruce/PyUI source patches retain their upstream terms and notices; the nested PyUI source-use notification requirement is recorded in the handover. PPSSPP patches and C++ acceptance fixtures retain [GPL-2.0-or-later](ppsspp/NOTICE.md). The bundled Noto Sans font uses [OFL](assets/fonts/OFL.txt). No Sony graphics, commercial game data, firmware or emulator binaries are included in the new payload.
