# Spruce Midnight for PPSSPP

This original palette matches the offshoot's dark blue and mint `#64ffdf` interface. The same INI contains a high contrast variant with a black background and yellow focus. It uses PPSSPP's existing fonts, glyph atlas, icons, controls, dialogs and renderer. No fonts, Sony artwork, firmware, shaders or executable assets are included.

The data format was checked against upstream PPSSPP **v1.20.3**, commit `d357e6a32934800d3d80b49f910a603e1b069751`. `UI/Theme.cpp` accepts `Name` and 24 color properties. Quoted colors use `#RRGGBBAA`; packed integer colors instead use ABGR. The supplied INI uses the quoted form throughout.

The adoption helper sets only:

| Config section | Key | Value |
|---|---|---|
| `Theme` | `ThemeName` | `Spruce Midnight` or `Spruce Midnight High Contrast` |
| `General` | `BackgroundAnimation` | `3` for PPSSPP's native wave, `0` for reduced motion |

`ThemeName` is a supported PPSSPP preference, not a project extension. The wave is PPSSPP's own implementation running inside its own process. Gameplay mappings, PSP button preference, emulation, audio, graphics backend and save paths are untouched.

For a qualified original Smart Pro profile, installation adds `Saves/.config/ppsspp/PSP/themes/spruce-midnight.ini` and edits `Saves/.config/ppsspp/PSP/SYSTEM/ppsspp-SmartPro.ini`. Spruce copies the platform INI into the active `ppsspp.ini` on launch and copies it back on exit. The helper therefore requires PPSSPP and every inventoried writer to be stopped. It does not edit an active running instance or replace the `Emu/PSP/assets` tree.

The custom directory follows upstream `GetSysDirectory(DIRECTORY_CUSTOM_THEMES)`: `<memstick>/PSP/themes`. The verified spruceOS v4.5.4 release archive contains `Emu/PSP/PPSSPPSDL_TrimUI` (19,885,376 bytes, SHA256 `d0635cdb73e046cf8c62a92a4c59194cf9a80dfabbe08a0c9a0cb4628a1c96d7`) with an embedded `v1.20.3` string. This identifies the archive artifact; it does not prove corresponding source or theme support. The shipped example profile remains **unqualified** because the installed device binary, memstick root, theme behavior and complete writer inventory have not been verified. Source format validation alone does not qualify that binary. Editing the example's flags is not a substitute for recording that evidence.

The original Python helper is `psp_shell.ppsspp.PPSSPPThemeManager`. Its public methods are `status`, `preview`, `apply`, `undo` and `recover`. Preview reports the affected keys and any overwrite. Apply requires the expected generation, matching source/config/profile hashes, a qualified exact executable version/hash and a quiescent write window. It journals snapshots before replacing files. The existing settings transaction engine performs host-tested interrupted-write recovery.

Undo restores the owned preference keys when they still match the applied values, preserving unrelated settings edited afterward. A preexisting palette is restored from its snapshot. A newly added palette remains installed but unselected; the result explicitly reports `theme_file_retained_unselected`. This avoids deleting a file another theme or user may now reference. A conflicting external theme edit is presented as a conflict.

Host tests:

```sh
PYTHONPATH=project python3 -m unittest discover -s project/tests -p 'test_ppsspp_theme*.py' -v
```

The SVG is a palette illustration, not a screenshot or evidence of device rendering. Color contrast checks cover opaque palette endpoints. PPSSPP rendering, font coverage, PowerVR behavior and FAT/exFAT recovery still require the relevant physical tests.

The palette and original illustration are MIT-licensed under `LICENSE` in this directory. Existing PPSSPP code/assets retain their own licenses and are not redistributed by this theme data.
