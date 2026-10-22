# Spruce Midnight for PPSSPP

This original palette matches the offshoot's classic PSP azure interface: a blue background, white text and a translucent white focus with navy labels. The same INI retains the high contrast variant with a black background and yellow focus. PPSSPP supplies its existing fonts, glyph atlas, icons, controls, dialogs and renderer.

The data format was checked against the official [PPSSPP v1.20.3 theme parser](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/UI/Theme.cpp) and [default theme data](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/assets/themes/defaultthemes.ini), commit `d357e6a32934800d3d80b49f910a603e1b069751`. `UI/Theme.cpp` accepts `Name` and 24 color properties. Quoted colors use `#RRGGBBAA`; packed integer colors instead use ABGR. The supplied INI uses the quoted form throughout. The 22 October palette revision uses those supported fields for focused, pressed, disabled, popup, tooltip, slider and scrollbar colors. Theme names remain unchanged so existing selection and Undo records still refer to the same variants.

The adoption helper sets only:

| Config section | Key | Value |
|---|---|---|
| `Theme` | `ThemeName` | `Spruce Midnight` or `Spruce Midnight High Contrast` |
| `General` | `BackgroundAnimation` | `3` for PPSSPP's native wave, `0` for reduced motion |

`ThemeName` is a supported PPSSPP preference, not a project extension. The wave is PPSSPP's own implementation running inside its own process. Gameplay mappings, PSP button preference, emulation, audio, graphics backend and save paths are untouched.

For a qualified original Smart Pro profile, installation adds `Saves/.config/ppsspp/PSP/themes/spruce-midnight.ini` and edits `Saves/.config/ppsspp/PSP/SYSTEM/ppsspp-SmartPro.ini`. Spruce copies the platform INI into the active `ppsspp.ini` on launch and copies it back on exit. The helper therefore requires PPSSPP and every inventoried writer to be stopped. It does not edit an active running instance or replace the `Emu/PSP/assets` tree.

The custom directory follows upstream `GetSysDirectory(DIRECTORY_CUSTOM_THEMES)`: `<memstick>/PSP/themes`. The verified spruceOS v4.5.4 release archive contains `Emu/PSP/PPSSPPSDL_TrimUI` (19,885,376 bytes, SHA256 `d0635cdb73e046cf8c62a92a4c59194cf9a80dfabbe08a0c9a0cb4628a1c96d7`) with an embedded `v1.20.3` string. This identifies the archive artifact; it does not prove corresponding source or theme support. The shipped example profile remains **unqualified** because the installed device binary, memstick root, theme behavior and complete writer inventory have not been verified. Source format validation alone does not qualify that binary. Editing the example's flags is not a substitute for recording that evidence.

The original Python helper is `psp_shell.ppsspp.PPSSPPThemeManager`. Its public methods are `status`, `preview`, `apply`, `undo` and `recover`. Preview reports the affected keys and any overwrite. Apply requires the expected generation, matching source/config/profile hashes, a qualified exact executable version/hash and a quiescent write window. It journals snapshots before replacing files. The existing settings transaction engine performs host-tested interrupted-write recovery.

The common interface exposes a combined review through `PPSSPPExperienceManager`: the current physical Confirm button, theme and motion preference share one stopped-writer transaction. It writes the shared INI once, journals the palette and all three generations together, and rolls the complete change back if a replacement fails. Its `experience.ppsspp.status`, `.preview`, `.apply` and `.undo` Dispatcher methods require an injected `experience_manager`; standalone mode has no emulator write authority. Replacing a customized palette defaults to Cancel. The independent `PPSSPPThemeManager` and `appearance.ppsspp.*` operations remain available for trusted callers; changing frontend preferences alone does not edit PPSSPP.

Owned PPSSPP configuration names follow the pinned engine's case-insensitive INI rules. Hash comments are retained. Semicolons inside a value are data, and quoted values are not decoded as JSON. Duplicate owned sections or keys are refused. The combined manager takes both component locks and an optional trusted maintenance lease for the entire read/preview/apply/undo/recovery window. A separate component transaction invalidates a stale joint preview.

Upstream `Core/Config.cpp` at the pinned version implements `Config::LoadGameConfig` by reading every setting present in a game INI, including manually stored keys marked global when saving. Existing `<game-id>_ppsspp.ini` files can therefore override the selected theme, motion and native-menu extension. The combined manager requires both qualified profiles to declare the same complete `per_game_configs` inventory and `per_game_inventory_verified=true`. It hashes those files, reports the owned override values and preserves every byte; a changed overlay invalidates preview. The example inventories remain unverified and empty. The manager reports global scope and does not claim uniform per-game appearance. Independent adapters report persisted/global configuration with `runtime_observed=false` and do not evaluate per-game overrides.

Undo restores the owned preference keys when they still match the applied values, preserving unrelated settings edited afterward. A preexisting palette is restored from its snapshot. A newly added palette remains installed but unselected; the result explicitly reports `theme_file_retained_unselected`. This avoids deleting a file another theme or user may now reference. A conflicting external theme edit is presented as a conflict.

Host tests:

```sh
PYTHONPATH=project python3 -m unittest discover -s project/tests -p 'test_ppsspp_theme*.py' -v
```

The SVG illustrates the palette; it is not a PPSSPP screenshot or device evidence. Host contrast checks composite focus and popup fills over the configured background. The native emulator keeps its own menu layout. This theme contains no Sony assets or fonts. PPSSPP rendering, font coverage, PowerVR behavior and FAT/exFAT recovery still require the relevant physical tests.

The palette and original illustration are MIT-licensed under `LICENSE` in this directory. Existing PPSSPP code/assets retain their own licenses and are not redistributed by this theme data.
