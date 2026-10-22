# Original spruce PSP presentation overlays

For the current host deliverable, use [dev_release.py](dev_release.py) and [the development instructions](../docs/development-release.md). [current-release.json](current-release.json) is its single release selection: the builder records resolved frontend commit, actual source inventory, base/PyUI identity and explicitly unselected native references in signed metadata. Generic `overlay.py` commands below remain explicit fixture/tooling examples; their example IDs do not select the current development release.

`overlay.py` is host tooling using Python 3 and the installed libsodium Ed25519 implementation. The payload contains only original Python presentation/extensions, assets, metadata and notices. It installs under `App/PSPMode/releases/<id>`. Mutable package records live in `App/PSPMode/state`. It never replaces spruce, PyUI, emulator files, firmware, ROMs or saves; archive contents never execute during verification or installation.

The checked-in TG5040 profile identifies spruceOS v4.5.4 commit `d45ff8dfe5756147522b04ae5863d17a90e88b54` and its embedded PyUI tree. Its device/runtime/source-use gates remain **false**. Device activation refuses this profile. Matching contract hashes is not a hardware test or proof of every file in a release archive. Host fixtures are explicitly synthetic and require both a fixture profile and `--fixture`; this option cannot bypass a device profile.

Archives are uncompressed normalized USTAR: exact `manifest.json`, a raw detached `manifest.sig`, and regular `payload/*` files. The signature authenticates the exact manifest bytes; all file sizes/hashes are verified before extraction. Links, GNU/PAX headers, special files, duplicate/case-colliding names, traversal, unsafe FAT names, unexpected members and oversized archives are rejected. The same open archive descriptor is retained through staging; extracted bytes are reverified before publication. No symlinks are needed on FAT/exFAT. Directory fsync is best-effort only where unsupported; physical power-loss testing remains necessary.

Create test signing keys **outside repositories**, keep private keys off cards, and pass verification keys from a separately trusted source:

```sh
mkdir -p /tmp/psp-demo-keys
python3 project/packaging/overlay.py keygen --private-key /tmp/psp-demo-keys/private --public-key /tmp/psp-demo-keys/public
python3 project/tools/fixture_card.py --card /tmp/psp-demo-card
python3 project/packaging/overlay.py create --source /tmp/psp-demo-payload --output /tmp/psp-demo.tar --release demo-1 --private-key /tmp/psp-demo-keys/private --public-key /tmp/psp-demo-keys/public --profile /tmp/psp-demo-card/fixture-profile.json
python3 project/packaging/overlay.py verify /tmp/psp-demo.tar --public-key /tmp/psp-demo-keys/public
python3 project/packaging/overlay.py stage /tmp/psp-demo.tar --card /tmp/psp-demo-card --public-key /tmp/psp-demo-keys/public --profile /tmp/psp-demo-card/fixture-profile.json --inventory /tmp/psp-demo-card/fixture-inventory.json --fixture
python3 project/packaging/overlay.py activate --release demo-1 --card /tmp/psp-demo-card --public-key /tmp/psp-demo-keys/public --profile /tmp/psp-demo-card/fixture-profile.json --inventory /tmp/psp-demo-card/fixture-inventory.json --fixture
python3 project/packaging/overlay.py rollback --card /tmp/psp-demo-card --public-key /tmp/psp-demo-keys/public
```

Prepare `/tmp/psp-demo-payload` with `app/psp_shell/__main__.py` and its original modules, `assets/`, `metadata/` and `notices/`. For the desktop demonstration set `PYTHONDONTWRITEBYTECODE=1`, add the release's `app` directory to `PYTHONPATH`, and invoke `python3 -m psp_shell` with the documented desktop options. Staging/activation never starts the program. Runtime integration remains separately gated.

`activate` writes a checksummed pending journal before changing the current release. `confirm-health --evidence report.json` requires matching `release_id`, exact `manifest_sha256`, `profile_id`, an `evidence_reference`, and true checks `first_frame`, `input`, `settings`, `classic_fallback`, `clean_exit`. A fixture receipt is host evidence only. Previous releases remain immutable. Rollback writes `state/force-classic` before restoring the prior package selector; it does not undo newer user saves. The frontend health subsystem separately owns `frontend-health.json` and foreground handoff records. Never clear a handoff or launch another UI over a surviving game merely because a package rolled back.

Default deterministic timestamp is `1792659237`, the saved active plan commit timestamp. Set `SOURCE_DATE_EPOCH` or `--source-date-epoch` to the release commit timestamp for subsequent builds; do not use the current clock. Security/data-schema/source timestamp downgrades require `--allow-downgrade` during activation. Repeating creation with identical payload, profile, metadata and key produces identical archive bytes.

Optional `--trust-store /trusted/keys.json` enforces a separately reviewed registry, e.g. `{"schema":1,"keys":[{"id":"<SHA256 of raw public key>","public_key":"release.pub","status":"active","introduced_epoch":1792659237}]}`. Relative key paths resolve beside the registry. `retired` keys verify historical releases but cannot sign new ones; `revoked` keys cannot verify. Include old public keys during rotation so retained releases can be checked for rollback. A revoked prior release must be replaced by a separately trusted recovery payload; never bypass a revocation to make rollback succeed. The registry and raw public keys must not be trusted merely because they arrived with an archive.
