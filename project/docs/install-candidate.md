# Offline install preparation

`install/build_candidate.py` now produces the actual private integration payload
and exact original source preimages. It can also compose a full, separately
extracted spruce base tree. This is workstation preparation for the original
Smart Pro TG5040, not an installed or hardware-qualified custom OS.

The owner has already authorized private noncommercial source work. The builder
uses the exact retained permission decision from 23 October, verifies its digest,
and constructs the existing typed `SourceUseReview`. It does not ask for another
notification, accept arbitrary permission JSON, or infer public distribution
rights. The project remains on pinned spruce v4.5.4 and the current signed dev20
payload; replacement emulator binaries are not selected.

## Build on the Linux workstation

Use the existing host dependencies and pinned source checkout. The tool invokes
the established source composition, signed-overlay verification and new-output
restoration APIs. Windows has a separate base preparation helper; these Linux
APIs are not presented as a Windows executable.

```sh
python3 project/install/build_candidate.py \
  --source-root /path/to/pinned-spruce-source \
  --overlay /path/to/smartpro-retropass-0.1.0-dev20.tar \
  --public-key /trusted/development-verification.pub \
  --output /private/new-install-preparation
```

The public key must be the expected workstation build key. A package and a new
key supplied together do not independently establish publisher identity.

To compose the full private base tree, additionally supply:

```sh
  --base-archive /private/cache/spruceV4.5.4.7z \
  --extractor /trusted/tools/7zz
```

The fixed base is 1,652,634,074 bytes with SHA256
`4623f1cd824ac1d01e7663d11ca40a8d3ad874c5f071e692f4392957d2159cfd`.
It is verified before extraction and again after full composition. No archive
script or native engine executes. The caller selects a trusted Linux 7-Zip
binary; its digest is recorded. The output path must be new and separate from
the source. `/mnt/SDCARD` is refused. Existing output is never overwritten.

## What is produced

| Output | Meaning |
|---|---|
| `candidate/tree/` | SD-relative source patches and verified frontend modules. This is a scoped delta, not a whole OS. |
| `candidate/backup/` | Exact source preimages retained by the integration composer. |
| `rollback/tree/` | Separately reconstructed original source preimages, verified against their hashes. It is not an internal-flash or complete-card restore. |
| `deploy-plan.json` | Exact old/new hashes, intended source modes, original overlay identity, base identity and remaining physical requirements. It grants no activation. |
| `prepared-card/` | Optional full base plus scoped integration, prepared only in the new workstation directory. Its runtime remains unavailable. |
| `base-files-before.json`, `prepared-card-files.json` | Optional complete private file inventories for extraction/composition readback. |
| `verification.pub` | Retained development public key; private signing material is never copied. |

Before patching a full extracted base, every affected source file must match its
independent pinned preimage. A new integration path must be absent. Any mismatch
stops the build before source modification. Afterwards every original file
outside the selected integration must retain its original bytes and mode, and
every selected file must match its candidate digest. This includes preserving
the existing native engines. The builder rejects symlinks/special files and
excessive entry/byte counts rather than silently flattening them.

The extracted full tree may contain upstream default configuration and data;
it contains no imported owner games or saves. Preserve the original card backup
separately. The Windows staging lane plans ROM copies but does not guess save
compatibility or merge the old emulator configuration into the new system.

## Device activation is still a separate step

Both fixed runtime selectors must still contain an undecorated
`configuration()` returning `None`. The builder checks syntax without importing
or executing their code. A signed package, copied plan, successful host build
or restored source tree cannot change this state.

Do not copy the prepared source candidate onto the owner's only card. Their
current handheld boots into PPSSPP with unusable button bindings; USB Storage
access is not established. A microSD reader, verified card backup and reviewed
current startup/settings are the first actual-device inputs. The separate
internal recovery archive and exact observed firmware/runtime are also needed
before selecting a private view-only configuration. Boot, input, classic return,
games, saves and recovery must then be observed on hardware.

The production profile, enhanced Resume and native replacement candidates remain
unselected. The full private base-plus-source tree is useful preparation, but
is not a claim that the custom UI is ready to boot or that games have migrated.
Keep the complete base and private derivative outside the public repository.
