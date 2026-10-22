# PPSSPP source integration

This directory extends real PPSSPP v1.20.3 source at
`d357e6a32934800d3d80b49f910a603e1b069751`. It reuses PPSSPP's ConfigSetting
serialization, SDL input translation, native menu bindings, widgets, and event
dispatch. The spruce PowerVR build recipe at
`9f770cb984fd8ffcc8f91d24fcbca859439c2e9b` defaults to that release. The verified
spruce v4.5.4 `Emu/PSP/PPSSPPSDL_TrimUI` contains the version string `v1.20.3`;
that does not establish its exact compiled source or contain this extension.
Pins, file hashes, and qualification limits are in [source-lock.json](source-lock.json).

The patch adds an opt-in **Independent native menu controls** checkbox and
**Native menu Confirm button** choice in PPSSPP's Controls settings on SDL
builds. Selecting physical south or east automatically gives Back the opposite
button. SDL south/east translate to PPSSPP `NKCODE_BUTTON_2`/`NKCODE_BUTTON_3`
in this pinned release. Android/XInput-style `BUTTON_A`/`BUTTON_B` would be wrong
for this SDL path.

The project-specific INI contract is:

```ini
[ProjectNativeMenu]
IndependentMenuControls = False
NativeMenuConfirm = south
NativeMenuBack = east
```

Disabled, malformed, equal, or non-SDL choices preserve the upstream menu
policy. The new setting is saved with global `CfgFlag::DEFAULT` metadata,
instead of being emitted as a per-game setting. Upstream manually authored
appended/per-game INI overlays can still contain arbitrary global section keys;
this patch does not change PPSSPP's general overlay semantics.

The patch reserves the selected physical pair for native Confirm/Back. It does not modify
`g_controllerMap`, `controls.ini`, PSP `ButtonPreference`, or emulated system
parameters. Keyboard Enter/Space, Escape, mouse Back, other native navigation,
and analog inversion retain upstream behavior. When the extension is enabled,
south/east are removed from other native information, tab and directional
bindings so an unusual gameplay remap cannot trigger two menu actions. The
desktop `PauseExitsEmulator` shortcut also yields to this pair in native menu and
pause-menu states. Its gameplay behavior remains unchanged. Invalid, disabled
and non-SDL configurations retain the upstream policy.

No emulator binary is shipped or replaced. Existing installed profiles remain
unqualified. The Python adapter cannot activate this patch in the stock binary;
a future qualified profile must identify the rebuilt executable hash, verify
the opt-in state and exact active/platform INI copy-back writers, and pass
physical input tests. Do not set a supported flag merely because the embedded
version string matches.

To apply in a separate PPSSPP v1.20.3 build tree:

```sh
git apply --check /path/to/project/ppsspp/patches/0001-independent-native-menu-controls.patch
git apply /path/to/project/ppsspp/patches/0001-independent-native-menu-controls.patch
```

Run the host acceptance with git, g++, and Python:

```sh
PPSSPP_SOURCE_ROOT=/path/to/pinned-ppsspp python -m unittest discover -s project/ppsspp/tests -v
```

Tests verify exact source preimages, apply the patch only in a temporary tree,
and compile and execute the actual patched `UpdateNativeMenuKeys` and `NativeKey`, actual SDL
translator, actual ConfigSetting constructors/read/write methods, and the native
widget fragment using its actual upstream constructor signature. Explicit narrow
stubs supply unrelated controller storage, platform callbacks, in-memory Section,
and widgets. A separate fixture executes the real INI value and boolean parsers
for quoted values, comments and literal escapes. These tests do not establish a full engine build, target ABI,
rendered widget behavior, physical input correctness, or device performance.
CI must provide `PPSSPP_SOURCE_ROOT`; absent source skips source-dependent tests.

The isolated [PowerVR candidate builder](build-candidate.md) verifies full source,
submodules, recipe and SDK inputs before copying them into a new work directory.
Its output stays separate from the project overlay and installed engine. Build
results, SDK dependency inventory and distribution clearance are separate claims.

The PPSSPP patch and C++ acceptance fixtures are GPL-2.0-or-later. The exact
upstream license and PSPSDK notice are retained in
[LICENSE.PPSSPP.txt](LICENSE.PPSSPP.txt). See [NOTICE.md](NOTICE.md) for boundaries
between the PPSSPP work, original Python helpers, and the separate PyUI frontend.
