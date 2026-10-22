# Separate PowerVR source candidate

`build_candidate.py` builds a complete PPSSPP SDL candidate in a new directory.
It leaves the supplied source checkout and installed spruce engine unchanged.
The candidate uses upstream v1.20.3, the pinned spruce PowerVR recipe and its
selected patches, and the project native-menu patch. The project development
overlay contains no emulator executable or SDK libraries.

## Inputs and invocation

Use a complete, pristine checkout of PPSSPP at
`d357e6a32934800d3d80b49f910a603e1b069751`, with all recursive submodules at their
gitlink revisions. The sparse source checkout used by host tests is insufficient.
Use a pristine checkout of `spruceUI/PPSSPP-spruce` at
`9f770cb984fd8ffcc8f91d24fcbca859439c2e9b`.

The two required SDK archives are listed with URLs, byte sizes and SHA-256 in
`build-inputs.lock.json`. Their complete downloaded contents were independently
hashed on 22 October 2026. The builder checks them again before preparing any
output. SDK extraction happens only inside the build image.

```sh
git clone --depth 1 --branch v1.20.3 --recurse-submodules --shallow-submodules https://github.com/hrydgard/ppsspp.git /tmp/ppsspp-full
git clone https://github.com/spruceUI/PPSSPP-spruce.git /tmp/ppsspp-recipe
git -C /tmp/ppsspp-recipe checkout --detach 9f770cb984fd8ffcc8f91d24fcbca859439c2e9b
python3 project/ppsspp/build_candidate.py --source-root /tmp/ppsspp-full --recipe-root /tmp/ppsspp-recipe --sdk-dir /tmp/ppsspp-sdk --work-dir /tmp/ppsspp-power-vr --jobs 4 --strict-sdk-search --rebuild-ffmpeg
```

Place the downloaded archives in `/tmp/ppsspp-sdk` before running the builder.
Host requirements are Python 3.9+, Git and a working local Docker daemon with
BuildKit. The script explicitly selects `/var/run/docker.sock` and preserves
Docker registry credentials. In a managed cloud environment, retain its Docker
proxy defaults and use `--ca-bundle` if the provided combined trust bundle lives
elsewhere. TLS verification stays enabled. No login or outbound messaging occurs.

The work directory must be new and outside the project and input directories.
The builder refuses changed tracked, untracked or ignored input files, sparse
PPSSPP source, missing/mismatched submodules, SDK hash mismatches and existing
output. `--prepare-only` copies and patches the isolated source without starting
Docker. An interrupted build can be inspected in place; start a new work
directory for another complete run.

`--strict-sdk-search` corrects the GCC 9 driver's default include/library search
order while retaining the same compiler, sysroot, source and target options.
It disables automatic C include search, lists GCC 9's C++ and intrinsic headers
before the SDK C headers, and lists GCC 9's runtime directory before the SDK
library directories. The recipe's final `-isystem` to `-I` rewrite is accounted
for by using the proved explicit `-I` form. Keeping GCC 9's runtime directory
first also prevents selection of the SDK's older GCC 7 static C++ archive.

Before compiling the engine, this mode requires an actual cross-compile/link
preflight: C and C++ must select glibc 2.25 headers, the large-file `fcntl`
declaration must avoid the newer `fcntl64` import, and a C++17
filesystem/future/math probe must link the GCC 9 static archive and pass the
recursive SDK ABI inventory. The probe is inspected without executing target
code. Its exact flags, header paths, archive hash and link trace are retained in
`sdk-search-preflight.json`. Omitting the option reproduces the original recipe
search behavior, whose completed candidate failed that SDK inventory.

`--rebuild-ffmpeg` also rebuilds the exact pinned FFmpeg submodule
`1e3b4965632f60b1d85360261d1b9dd45444bc71`. Its original `linux_arm64.sh`
configuration supplies the unchanged codec/module selection. The helper expands
that command as arguments without executing its in-tree build function, then
adds the proved sysroot/header/library policy and an absolute new install
prefix. Configure and make run outside the read-only source tree. PPSSPP's
FFmpeg include/library/API cache entries are invalidated, and all five selected
libraries and header roots must resolve to the rebuilt prefix.

The old bundled `libavutil.a(file_open.o)` imports `fcntl64`, which prevents a
strict old-SDK link even after PPSSPP's own headers are corrected. Its prebuilt
version header says `a5baf97`, while the locked source is `1e3b496...`; exact
prebuilt/source correspondence is unverified. The first archive is therefore a
verified pinned-source/input snapshot, without proof of corresponding source
for those old FFmpeg objects. Artifact hashes and the first build outcome are
preserved. Rebuilding FFmpeg from the pinned source establishes a new source
chain, subject to the final engine and SDK checks.

## Recipe adaptations

The locked upstream recipe uses Ubuntu 20.04's GCC 9 cross compiler, a Linaro
glibc 2.25 sysroot and the original TG5040 PowerVR/SDL SDK. Its common and PVR
patch-selection rules are preserved. The builder applies the project extension
first. `apply_recipe.py` then verifies the pinned source HEAD and selected
script hashes, applies each selected common/PVR script explicitly, and requires
both a zero exit status and changed source content. The ten applied scripts,
five prescribed skips, per-script before/after hashes and final combined source
hashes are recorded in `recipe-assembly.json`. A changed HEAD, changed input,
failed script or stale assembly is rejected before compilation. The
`combined-tracked-source.patch` supplements the full source snapshot; the new
project header is retained by that snapshot and the project patch.

Assembly and compilation use the recipe image's root user, with bind mounts
limited to the prepared source, output, build helpers and cache. The disposable
containers trust only `/build/ppsspp` for Git operations, including CMake's
version-source generation. Host Git settings are unchanged. This avoids the
upstream shell loops silently skipping unreadable patch directories under an
unprivileged user. Such an earlier partial compile was stopped and rejected;
the explicit assembly gate precedes the corrected compile.

The generated Dockerfile pins the Ubuntu image digest, accepts a temporary CA
secret for HTTPS package traffic and retries package downloads. It installs the
compiler and merges the SDK in one filesystem layer using read-only SDK archive
mounts. Unused Linaro compiler and SDK staging directories are removed before
that layer is committed. This avoids cumulative SDK copies with Docker's `vfs`
storage driver; the merged sysroot, GCC 9 compiler and build flags are preserved.
The generated
build script replaces unrestricted `nproc` concurrency with the chosen job count.
The upstream configure flags, selected patch scripts, merged sysroot and target
remain recorded. Exact generated script hashes and installed Ubuntu package
versions accompany each result. Ubuntu package repositories are mutable, so
these records do not claim a bit-identical binary rebuild.

The original multi-layer image exhausted this workspace during its first
container creation. Its exact image/hash/log record is retained separately from
the compact rebuild. Recovery removed only this task's image and captured cache
IDs, then reused the already-prepared candidate source. No Docker storage driver
or proxy setting was changed.

## Outputs and evidence

`candidate-report.json` records whether the full engine compiled, the exact
executable SHA-256, builder image ID and generated recipe hashes. A successful
compiler exit is followed by AArch64 ELF inspection. `candidate-elf.txt` records
the interpreter, dynamic dependencies and symbol-version requirements.
`candidate-abi.json` compares recursive dependency basenames and symbol versions
with the merged SDK inventory using `readelf`; it never executes the candidate.
It retains ambiguous names and selected SDK paths. This is an SDK inventory,
with actual device loader paths and driver behavior still untested.

`candidate-corresponding-source.tar.gz` retains the complete modified PPSSPP
source and initialized submodule sources with their notices. It also retains
project patches and source locks, the exact recipe scripts and patches, generated
Dockerfile, compiler package inventory, assembly evidence and build helpers.
The documented build procedure, strict-search helper and preflight evidence are
retained alongside those inputs. New archives use gzip level 6; the first
preserved candidate used the original default level 9.
When FFmpeg has been rebuilt, the archive also retains its exact source,
configure arguments, generated config/headers, version source and new archive
hashes. Unused old FFmpeg `*.a` inputs are omitted only from that new archive,
with an explicit file/hash manifest; working source/prebuilt files stay intact.
FFmpeg's raw `config.log` includes an environment dump and stays private outside
the retained source metadata. It is excluded along with session CA and secrets.
`build-configuration/` retains CMake configuration, the generated
`git-version.cpp`, and actual flags for `Core/KeyMap.cpp`, `UI/NativeApp.cpp` and
`UI/GameSettingsScreen.cpp`; the builder requires `SDL` in all three units.
The first local run also extracted `/tmp/pvr-toolchain.cmake` from its active
build container into that directory before creating the source archive. The
builder now retains that exact file during compiler package inventory. The
generated Dockerfile reconstructs this file with the original recipe's exact
`printf` instruction.
The upstream version generator uses `git describe --always` without `--dirty`,
so its `v1.20.3` string does not identify the applied patches. The source
manifests provide that evidence separately. Git metadata, compiled build output,
SDK archives, session CA and credentials are excluded. The
`rebuild-source.sh` helper skips patch application because that source snapshot
already includes the modifications. SDK URLs/hashes remain in the input lock.
The archive stays in scratch until distribution rights are resolved.

When rebuilding from the archive without Git metadata, create `ppsspp/build/`
and copy `build/build-configuration/git-version.cpp` there before invoking
`build/rebuild-source.sh` in the recorded toolchain image. Set only its
`PPSSPP_GIT_VERSION_NO_UPDATE` macro to `1`, keeping the recorded version string,
so CMake preserves that generated source. Retain this explicit build-control
change with the new result. Use the same source/output/cache mounts and working
directory as the recorded compile command. The archive is a source-retention
record, and the SDK inputs and generated image must be obtained separately.

For an archive produced with `--rebuild-ffmpeg`, recreate its separate FFmpeg
prefix before running the engine helper. The original Python helper requires
Git metadata to validate fresh checkouts. A manual archive rebuild uses the
retained source identity and exact configure arguments instead. Inside the
recorded compiler image, mount `ppsspp/` at `/build/ppsspp` read-only, retained
`build/` at `/retained` read-only, and new writable directories at
`/ffmpeg-build` and `/ffmpeg-sdk`, then run:

```python
import json, os, subprocess
with open('/retained/ffmpeg-build-inputs/manifest.json') as stream:
    manifest = json.load(stream)
environment = dict(os.environ, revision=manifest['source_git_description'])
subprocess.run(['/build/ppsspp/ffmpeg/configure', *manifest['configure_args']],
               cwd='/ffmpeg-build', env=environment, check=True)
subprocess.run(['make', '-j' + str(manifest['jobs']), 'install'],
               cwd='/ffmpeg-build', env=environment, check=True)
```

The exported lowercase `revision` preserves the recorded `1e3b496` version
source without Git metadata; preserve the original generated
`libavutil/ffversion.h` separately and retain this explicit build-control choice.
Mount the completed prefix at `/ffmpeg-sdk` for the PPSSPP build. Its generated
engine script clears the old FFmpeg include/library/API cache selections.

Keep `image-build.log`, `engine-build.log`, source archive and ABI evidence with
the local candidate. No save-state, hardware input, PowerVR rendering,
suspend/return or performance result follows from cross compilation. The
installed engine fingerprint and all physical qualification fields stay unset.

The recorded 22 October 2026 candidate completed the full engine build and
produced a 19,881,280-byte AArch64 ELF. Its SDK inventory failed: libc lacks the
required `GLIBC_2.28`, and libm lacks `GLIBC_2.27` and `GLIBC_2.29`. GCC 9's
default cross include/library directories take precedence over the old sysroot;
the independent header/link probes establish that mismatch. This first candidate
and its source archive remain preserved separately from any corrected search
policy. [The sanitized evidence](../evidence/ppsspp-candidate-build.json) records
their exact hashes, assembly, compiler flags and failed ABI gate.

The corrected build completed with the explicit search policy and rebuilt
pinned FFmpeg. Its 19,909,952-byte AArch64 ELF requires only `GLIBC_2.17` and
passes the recursive inventory across sixteen objects, with no missing
basenames or symbol versions. [Corrected build evidence](../evidence/ppsspp-sdk-search-build.json)
records the separate executable/source identities and failed strict attempt
that exposed the old FFmpeg object. This passes the SDK inventory only; actual
device loader paths, PowerVR/SDL behavior and physical qualification remain
untested.

## Distribution status

The pinned recipe repository contains no root `LICENSE` file. Its
`build-pvr.sh`, `Dockerfile.pvr`, `patches/common/*.py` and `patches/pvr/*.py` lack
an explicit licence grant in their headers. Their exact code is retained locally
to reproduce this private source candidate; redistribution terms remain
unresolved. The SDK archives include vendor runtime libraries whose redistribution
rights have not been audited. Do not publish the candidate executable, complete
source archive or SDK/runtime blobs as a cleared release from this checkpoint.

PPSSPP's GPL-2.0-or-later terms and third-party notices still apply. Local
compilation, complete corresponding-source retention, distribution clearance and
physical qualification must each have their own evidence. No author notification
or other outreach has been sent.
