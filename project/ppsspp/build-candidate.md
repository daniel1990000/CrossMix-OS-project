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
python3 project/ppsspp/build_candidate.py --source-root /tmp/ppsspp-full --recipe-root /tmp/ppsspp-recipe --sdk-dir /tmp/ppsspp-sdk --work-dir /tmp/ppsspp-power-vr --jobs 4
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
`build-configuration/` retains CMake configuration, the generated
`git-version.cpp`, and actual flags for `Core/KeyMap.cpp`, `UI/NativeApp.cpp` and
`UI/GameSettingsScreen.cpp`; the builder requires `SDL` in all three units.
The recorded local run also extracted `/tmp/pvr-toolchain.cmake` from its active
build container into that directory before creating the source archive. The
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
