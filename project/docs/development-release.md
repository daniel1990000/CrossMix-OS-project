# Build and run the development deliverable

This deliverable is a **host preview of the original Smart Pro presentation**. It does not install spruce, PyUI, firmware or emulators and does not qualify device activation. The packaged device profile remains unqualified. Keep the current working device/card untouched.

From the repository, using a Python environment with the documented desktop dependencies:

```sh
python3 project/packaging/dev_release.py --output /tmp/smartpro-development --release smartpro-psp-0.1.0-dev1 --include-source --smoke-python /path/to/preview-venv/bin/python
```

The output path must be new and outside `project/`. Python 3 and system libsodium are required to build/sign/verify. The `--smoke-python` environment additionally needs system SDL2, `PySDL2==0.9.17` and `Pillow==11.1.0`. No dependencies are downloaded or installed automatically by the builder.

The directory contains:

- `*-host-preview.zip`: runnable original Python modules, profiles, assets, provenance and notices. Extract on a computer; follow its `RUN.txt`.
- `*.tar`: a signed, scoped Python overlay for explicitly marked host fixtures, with full signature and hash-inventory validation.
- `development-verification.pub`: raw Ed25519 public key for that development signature.
- `*-original-source.zip` when requested: an allowlisted snapshot of original project source, host tools/tests/docs and licensed assets, prepared from files even before a Git commit. Upstream patches/source, user data, state, author-notification drafts and signing keys are excluded.
- `host-preview.png` when smoke rendering was requested.
- `build-report.json`: actual host build/verification results and explicit false device-qualification gates.
- `START-HERE.txt` and `SHA256SUMS`.

The default development signing key is generated only in a scratch directory, never copied into a payload, and deleted before the output directory is published. The public key is retained. This is a **development test identity**, not proof of upstream endorsement or production release identity. Replacing an archive and its adjacent public key defeats any publisher-identity assumption; real releases need a separately trusted key registry and cleared qualification gates.

The builder creates the signed overlay twice with the same key and compares exact bytes. It also rebuilds the standalone ZIP and optional source ZIP twice. Entries, UTC timestamps, permissions and ordering are normalized. `SOURCE_DATE_EPOCH` or `--source-date-epoch` selects the release commit timestamp; the default is the recorded active plan timestamp. Reproducibility assumes the same source bytes and Python/zlib toolchain. Rendering performance timings are observed host data and are not placed in the deterministic archives.

Each default invocation generates a fresh ephemeral signing identity, so signatures/public-key artifacts differ between invocations. The unsigned ZIP remains reproducible. To reproduce the signed archive across invocations, supply both `--private-key /external/development-private` and `--public-key /external/development-public` for a fixed development signer. These files remain outside the project and payload; the builder never deletes a caller-owned key. Production credentials should not be used for this preview.

The smoke path verifies the signature before any extraction, stages only under a temporary fixture card's `App/PSPMode`, selects a pending release, runs the **installed payload** with dummy SDL, navigates settings and checks its original classic-delegation contract, then rolls back and verifies `force-classic`. This does not launch stock PyUI, a game or real hardware. It records no physical-device readiness claim. Without `--smoke-python`, signature/rebuild/stage/activation/rollback checks still run, and the report explicitly records that rendering was not executed.

To verify the final artifacts and package:

```sh
cd /tmp/smartpro-development
sha256sum -c SHA256SUMS
python3 /path/to/repository/project/packaging/overlay.py verify smartpro-psp-0.1.0-dev1.tar --public-key development-verification.pub
```

After extracting `*-host-preview.zip`, run from its `smartpro-host-preview` folder:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=app /path/to/preview-venv/bin/python -m psp_shell --demo
```

For a headless screenshot add `--headless --frames 2 --state-dir /tmp/smartpro-preview-state --screenshot /tmp/smartpro-preview.png`. Keep state outside the extracted payload. Device boot/launch integration, source-use notification/rights, internal startup/scene restoration, sleep/USB/power and save integrity remain separate gates described in [recovery.md](recovery.md).
