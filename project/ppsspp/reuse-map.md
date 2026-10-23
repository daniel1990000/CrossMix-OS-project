# PPSSPP reuse in the Smart Pro spruce offshoot

Use upstream PPSSPP as a complete native emulator and UI. The inspected source is **v1.20.3**, commit `d357e6a32934800d3d80b49f910a603e1b069751`; the separate Spruce PowerVR recipe/patch identity belongs in `source-lock.json`. The original Smart Pro's installed stable binary has not yet been matched to this source. It stays unchanged while the optional source build is developed and qualified separately.

The verified spruceOS v4.5.4 release archive contains `Emu/PSP/PPSSPPSDL_TrimUI`, 19,885,376 bytes, SHA256 `d0635cdb73e046cf8c62a92a4c59194cf9a80dfabbe08a0c9a0cb4628a1c96d7`, with an embedded `v1.20.3` string. This release-artifact observation is recorded separately in the theme example profile. It does not prove source correspondence, identify the installed device executable, or qualify the theme extension.

The shell delegates launch through Spruce's existing wrapper and principal loop, releases its display/input ownership first, and returns through that same lifecycle. PPSSPP owns its window, graphics context, UI events, emulated machine and saves. Its screens receive the original matching palette through supported configuration. This reuses the working native screens rather than constructing a second emulator settings or save-state interface in Python.

| Existing component | Reuse boundary and resulting behavior |
|---|---|
| [`UI/Theme.cpp`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/UI/Theme.cpp) | Load the original `spruce-midnight.ini` using the supported theme scanner. Reuse native widget/font/icon selection. Palette data cannot change fonts, icons, layouts or animation code. |
| [`UI/Background.cpp`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/UI/Background.cpp) and [`Core/ConfigValues.h`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/Core/ConfigValues.h) | Use the native `WAVE=3` animation and `OFF=0` for reduced motion. The Python frontend does not copy the PPSSPP wave/shader implementation. |
| [`Common/UI/View.cpp`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/Common/UI/View.cpp), `ViewGroup.cpp`, `PopupScreens.cpp` | Retain native selection, focus, scrolling, widgets and confirmation dialogs inside PPSSPP. The independent native-menu mapping patch is isolated under this GPL subtree. |
| [`UI/GameSettingsScreen.cpp`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/UI/GameSettingsScreen.cpp), `ControlMappingScreen.cpp`, `DisplayLayoutScreen.cpp` | Keep graphics, audio, emulation, per-game settings and controller editors as native screens. The shell exposes common choices only through reviewed configuration adapters and retains advanced access. |
| [`Core/Dialog/PSPOskDialog.cpp`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/Core/Dialog/PSPOskDialog.cpp) | Keep the emulated PSP on-screen keyboard in PPSSPP, where it has game and PSP utility context. Do not extract it into the system keyboard or copy PSP assets. |
| [`UI/PauseScreen.cpp`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/UI/PauseScreen.cpp) | Reuse existing save-slot cards, screenshot viewer, save/load/undo controls and engine callbacks. These already call PPSSPP's state subsystem and distinguish slot contents. |
| [`UI/SavedataScreen.cpp`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/UI/SavedataScreen.cpp) | Keep the native savedata/state manager. In-game savedata and emulator states remain different collections. |
| [`Core/SaveState.h`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/Core/SaveState.h) | Use `Rescan`, `HasSaveInSlot`, `HasScreenshotInSlot`, `GetSlotDateAsString`, `GenerateSaveSlotPath`, `SaveSlot` and `LoadSlot` from a reviewed in-emulator integration, where the game prefix and active engine are known. These are C++ engine APIs, not an existing external shell protocol. |
| [`Core/Util/PathUtil.cpp`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/Core/Util/PathUtil.cpp) | Resolve savedata, states, screenshots, configuration and custom themes through the engine's memstick authority. Do not guess slot filenames by appending `.ppst` to a ROM name. |
| [`Core/Config.cpp`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/Core/Config.cpp) | Retain global/per-game precedence, engine validation and supported `ThemeName`/`BackgroundAnimation` keys. Spruce platform copy-in/copy-back remains part of the adapter contract. |
| [`Common/Render`](https://github.com/hrydgard/ppsspp/tree/d357e6a32934800d3d80b49f910a603e1b069751/Common/Render), [`Common/GPU`](https://github.com/hrydgard/ppsspp/tree/d357e6a32934800d3d80b49f910a603e1b069751/Common/GPU), [`GPU/GLES`](https://github.com/hrydgard/ppsspp/tree/d357e6a32934800d3d80b49f910a603e1b069751/GPU/GLES) | Reuse the native renderer, atlas/text code and GPU backend inside the emulator build. Keep the device-qualified PowerVR/SDL environment and separate process ownership. No global graphics-library replacement or speed claim follows from this source reuse. |

## What is implemented here

`theme/spruce-midnight.ini` provides the original normal/high-contrast palettes. `psp_shell.ppsspp` validates the actual source-supported schema and provides preview, exact-profile gates, a journaled theme/config installation and targeted undo. Tests cover source parser keys, original colors, preserving unrelated settings, source/profile/config staleness, running writers, overwrite confirmation, external edit conflicts and interrupted multi-file recovery. The supplied compatibility example refuses writes until qualified.

The independent native-menu patch is maintained separately from this original adapter and theme data. It retains the existing PSP/gameplay mappings and the old behavior by default. Enabled Confirm/Back keys are reserved against colliding native information, tab, directional and menu-exit actions. Each candidate binary needs its corresponding source, source/patch identities, build recipe and notices before redistribution. The [isolated candidate builder](build-candidate.md) records these inputs without changing the installed emulator.

The corrected source candidate compiled on 22 October 2026 with the proved
spruce patches, explicit GCC9/SDK searches and rebuilt pinned FFmpeg. It passes
the recursive SDK basename/version inventory, with device qualification and
distribution clearance still outstanding. Its [build evidence](../evidence/ppsspp-sdk-search-build.json)
is separate from the [original attempt](../evidence/ppsspp-candidate-build.json),
whose compiled ELF failed that inventory.

## Continue Playing evidence

The separate [optional state-evidence patch](state-evidence.md) adds an in-process
qualification API around the real Save/SaveSlot/Process lifecycle. It checks the
final slot rename, reports rejected operations, invalidates changed sessions,
and fingerprints the exact active ROM, running executable and completed state.
Compiled source acceptance includes the real upstream SHA-256 implementation.
The optional API and its separately locked [session extension](state-session.md)
are now included in the [complete private PowerVR build](../evidence/ppsspp-complete-state-build.json).
The extension adds a new opt-in private request/result protocol; it is not an
existing stable-spruce API. Actual save/Process completion and native state-load
acknowledgements bind request, game, engine, format and state fingerprints.
`PrincipalStateSessionAuthority` supplies the fixed launcher environment,
checks stopped writers after the real process boundary, and stores boot-bound
authenticated capabilities for the next source process. Typed Resume retains
the original `device.run_game` route. Signed checkpoint times survive a later
failed save; an arbitrary card JSON record cannot authorize Resume.

The checked spruce save-and-quit override exits only after successful completion.
The real cross-process host fixture covers save, failed later save, fresh-process
Resume and load acknowledgement. Its serializer/platform are fixtures. Full ROM
hashing can pause emulation; no device timing is claimed. Callback completion
does not establish durable storage or clean shutdown. Shipped profiles therefore
keep ordinary launch until independent installed-profile and TG5040 tests pass.

## Source and asset separation

PPSSPP's engine/UI source is GPL-2.0-or-later with per-file third-party exceptions. Keep copied or patched source and its original headers/licenses in this separate PPSSPP tree and the matching source bundle. Do not paste engine-integrated code into the original MIT Python frontend or imply that the frontend license covers PPSSPP.

The new palette/adapter/illustration are original. They refer to supported configuration names and existing native resources without copying fonts, atlases, UI images or Sony assets. If any existing asset is later redistributed, audit that exact file's license and notices first. The theme package currently contains none of those assets.
