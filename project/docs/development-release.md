# Build and run the development deliverable

This deliverable is a **host preview of the original Smart Pro presentation**. It does not install spruce, PyUI, firmware or emulators and does not qualify device activation. The packaged device profile remains unqualified. Keep the current working device/card untouched.

From the repository, using a Python environment with the documented desktop dependencies:

```sh
python3 project/packaging/dev_release.py --output /tmp/smartpro-development --include-source --smoke-python /path/to/preview-venv/bin/python
```

The output path must be new and outside `project/`. Python 3 and system libsodium are required to build/sign/verify. The `--smoke-python` environment additionally needs system SDL2, `PySDL2==0.9.17` and `Pillow==11.1.0`. No dependencies are downloaded or installed automatically by the builder.

The full host certification additionally requires system SDL_image (`libsdl2-image-2.0-0` on Debian/Ubuntu) for actual embedded-path artwork decoding tests. The standalone preview continues to use Pillow; the device keeps its existing SDL libraries.

Historical dev9 previews now have [private retained-storage readback receipts](../evidence/artifact-custody/host-retention.json).
Both the original verified artifact and later handover CI archive were retrieved
from Drive and matched against their distinct GitHub digests, all eight inner
checksums, signed payload and original-source inventory. These copies do not
recover private native outputs or establish production signing trust.

[The current release descriptor](../packaging/current-release.json) selects the release ID, normalized timestamp, pinned spruce/PyUI baseline and exact original payload scope. The CLI and CI use it by default; an explicit `--release` must match it. The native candidate hashes, extension sets and historical evidence in that file are references only: no upstream patch or native binary is selected for this preview. The historical host pass does not certify this release.

Each build resolves repository HEAD to an exact frontend commit and records whether `project/` has uncommitted changes. A SHA-256 inventory binds the actual allowlisted source bytes, including the descriptor and copied source lock. This identity appears in signed payload metadata and `build-report.json`. A modified checkout is explicitly labelled and must not be presented as an exact-commit certification.

The directory contains:

- `*-host-preview.zip`: runnable original Python modules, profiles, assets, provenance and notices. Extract on a computer; follow its `RUN.txt`.
- `*.tar`: a signed, scoped Python overlay for explicitly marked host fixtures, with full signature and hash-inventory validation.
- `development-verification.pub`: raw Ed25519 public key for that development signature.
- `*-original-source.zip` when requested: an allowlisted snapshot of original project source, host tools/tests/docs and licensed assets, prepared from files even before a Git commit. Upstream patches/source, user data, state, author-notification drafts and signing keys are excluded.
- `host-preview.png` when smoke rendering was requested.
- `build-report.json`: actual host build/verification results, resolved release selection and explicit false device-qualification gates.
- `release-source.json`: exact original-source inventory and resolved frontend identity; also retained inside the optional source ZIP for rebuilding without Git.
- `START-HERE.txt` and `SHA256SUMS`.

The default development signing key is generated only in a scratch directory, never copied into a payload, and deleted before the output directory is published. The public key is retained. This is a **development test identity**, not proof of upstream endorsement or production release identity. Replacing an archive and its adjacent public key defeats any publisher-identity assumption; real releases need a separately trusted key registry and cleared qualification gates.

The builder creates the signed overlay twice with the same key and compares exact bytes. It also rebuilds the standalone ZIP and optional source ZIP twice. Entries, UTC timestamps, permissions and ordering are normalized. The timestamp defaults to the release descriptor; `SOURCE_DATE_EPOCH` or `--source-date-epoch` can explicitly select another normalized timestamp, which the report records. Reproducibility assumes the same source bytes, timestamp and Python/zlib toolchain. Rendering performance timings are observed host data and are not placed in the deterministic archives.

Each default invocation generates a fresh ephemeral signing identity, so signatures/public-key artifacts differ between invocations. The unsigned ZIP remains reproducible. To reproduce the signed archive across invocations, supply both `--private-key /external/development-private` and `--public-key /external/development-public` for a fixed development signer. These files remain outside the project and payload; the builder never deletes a caller-owned key. Production credentials should not be used for this preview.

The smoke path verifies the signature before any extraction, stages only under a temporary fixture card's `App/PSPMode`, selects a pending release, runs the **installed payload** with dummy SDL, navigates settings and checks its original classic-delegation contract, then rolls back and verifies `force-classic`. This does not launch stock PyUI, a game or real hardware. It records no physical-device readiness claim. Without `--smoke-python`, signature/rebuild/stage/activation/rollback checks still run, and the report explicitly records that rendering was not executed.

To verify the final artifacts and package:

```sh
cd /tmp/smartpro-development
sha256sum -c SHA256SUMS
python3 /path/to/repository/project/packaging/overlay.py verify *.tar --public-key development-verification.pub
```

After extracting `*-host-preview.zip`, run from its `smartpro-host-preview` folder:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=app /path/to/preview-venv/bin/python -m psp_shell --demo
```

For a headless screenshot add `--headless --frames 2 --state-dir /tmp/smartpro-preview-state --screenshot /tmp/smartpro-preview.png`. Keep state outside the extracted payload. Device boot/launch integration, source-use notification/rights, internal startup/scene restoration, sleep/USB/power and save integrity remain separate gates described in [recovery.md](recovery.md).

The extracted `smartpro-original-source` directory can rebuild the same deliverable using `python3 packaging/dev_release.py --output /tmp/smartpro-rebuild --include-source` and the same optional signing/smoke arguments. Its `metadata/release-source.json` preserves the original Git identity and verifies all selected source bytes before building. Changed exported source is rejected instead of being attributed to the original commit. Use a repository checkout and a new descriptor for subsequent development. Full pinned-source certification additionally needs the separately scoped upstream patches/native fixtures and the five pinned source references (spruce, PPSSPP, spruce RA, PortMaster-New and PortMaster-GUI); the original-only ZIP does not contain those upstream/native source scopes.

Dev14 adds manually dispatched GitHub build provenance and stable original-only
host delivery. See [verification instructions](nondevice-completion-2026-10-23.md).
Attestation identifies the workflow/source that produced host bytes; device
qualification and the existing operational signing requirements remain separate.
