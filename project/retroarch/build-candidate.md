# Private RetroArch/IGM candidate

This builds the complete RetroArch v1.22.2 engine with all four pinned spruce
common patches, the three shared IGM sources, and the separately locked opt-in
`project_menu_controls` extension. It never executes a target program or changes
an installed emulator. The extension starts disabled and affects only the spruce
IGM; standard RetroArch menus and gameplay controls remain separate.

The exact upstream commit, spruce recipe, selected files, optional patch, proved
compiler-image identity and original TG5040 SDK assets are recorded in
[build-inputs.lock.json](build-inputs.lock.json). This is a new private candidate;
it does not establish the source correspondence of spruce's bundled executable.

Use a full pristine checkout, rather than the narrow source-acceptance staging
helper. Git, Python 3.10+, and the local Docker daemon are required. Restore the
immutable compiler image using the pinned PPSSPP old-SDK build procedure when
it is absent; an image tag with a different identity is refused. The source
checkout and private work path must be separate and new.

```sh
git clone --depth 1 --branch v1.22.2 https://github.com/libretro/RetroArch.git /private/ra-upstream
git clone https://github.com/spruceUI/RA.git /private/ra-recipe
git -C /private/ra-recipe checkout --detach 71d84da4dc88945177a3eb34268013355c705dbd
python3 project/retroarch/build_candidate.py prepare --upstream /private/ra-upstream --recipe /private/ra-recipe --work /private/ra-build
python3 project/retroarch/build_candidate.py configure --work /private/ra-build
python3 project/retroarch/build_candidate.py build --work /private/ra-build --jobs 4
```

Preparation verifies clean Git identities and every selected patch/shared-source
hash, applies patches in recipe order, then verifies the extension's resulting
source hashes. It retains complete original and modified engine sources, the
complete recipe, notices, the optional patch, build helpers and an inventory in
`source-inputs.tar.gz`. It excludes Git internals, SDK blobs and session data.
Configuration and build recheck the full prepared source inventory. A changed
input requires a new preparation directory.

The original TG5040 configuration differs explicitly from the recipe's universal
Ubuntu build: `--enable-vulkan` becomes `--disable-vulkan`, because the original
SDK has no Vulkan loader. SDL2/EGL/GLES/GLES3 remain enabled. GCC 9 intrinsic and
C++ headers/runtimes precede the original SDK C headers/libraries; pkg-config
reads only the SDK. A compiled C/C++17/header/link preflight checks this policy
without executing target code. SDK C headers use explicit `-isystem` with
`-nostdinc`, so engine `-I` compatibility headers keep their intended precedence.
A compiled actual bundled-zlib source/header trace checks that behavior and
rejects Ubuntu C header leakage. No newer host driver or C library is substituted.
The recipe also appends `-lstdc++` explicitly, bypassing its unused static-runtime
variable. A retained build-only Make overlay selects the proved GCC 9 static
C++ archive and enables a full link trace; no engine source is changed for this
correction and no replacement C++ shared library is installed.
The fixed recipe flags, static audio/video filters, compiler package inventory,
generated configuration and actual ELF audit are retained. The local container
has no network and uses at most four CPUs and 8 GiB RAM. Docker connection
selectors are cleared only for that subprocess; registry/proxy configuration is
left intact. No compiler image or sysroot is mutated.

The stripped executable is `output/retroarch-igm-tg5040`. Inspect
`build-manifest.json`, `sdk-preflight.json`, `sdk-abi-inventory.json`,
`elf-inventory.txt` and `build-records.tar.gz`. A failed SDK audit retains the
candidate and records the failure. The audit compares recursive ELF names and
symbol versions against SDK basenames; it does not reproduce an installed
loader's resolution order, runtime driver loading, input, rendering, save/state
compatibility or physical behavior. No physical compatibility gate is enabled.

Retain both source and build-record archives alongside the candidate. Raw
configure/build logs remain in the private work directory, not public evidence.
The engine's original licences and notices are preserved in full source. This
builder is MIT; the optional engine modifications use GPL-3.0-or-later. An
explicit grant for the external spruce recipe/shared code has not been located,
and SDK/runtime redistribution is not cleared. Keep the executable and complete
source/input archives private while those rights remain unresolved. Development
overlay packages must not include these candidates or vendor SDK libraries.
