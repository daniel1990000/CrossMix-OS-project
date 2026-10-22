# Saved development evidence

All results in this directory are **host evidence**, captured 22 October 2026. No original TrimUI Smart Pro was attached.

- `host-tests.json`: 277 Python/SDL/integration checks plus 24 PPSSPP source/build-tool checks; all 301 passed, with zero skips, failures or errors. Both untouched pinned source checkouts were available. The continuation's checks cover live binding/return contracts, partial lifecycle failures, opt-in controls, common appearance transactions, USB staging failure, real INI semantics, native-menu input collisions and checked build-source assembly.
- `source-contract-audit.json`: all 34 selected spruce source contracts match. This is not a complete release inventory or a device test.
- `release-source-audit.json`: complete downloaded archive SHA-256, ten selected integration/licence comparisons and bundled PPSSPP fingerprint/version hint. Reproduce with `project/dev/audit_release.py` and host-only `py7zr==0.22.0`.
- `development-build.json`: actual deterministic same-key overlay/ZIP rebuilds, signature and payload inventory verification, fixture staging/activation/rollback, installed-payload dummy-SDL rendering and original settings/navigation/classic-delegation checks. The generated private key was deleted. Device qualification remains false.
- `ppsspp-candidate-build.json`: complete AArch64 engine cross-build after checked project/recipe assembly, executable fingerprint, recursive SDK dependency inventory and private corresponding-source retention. Compilation succeeds, but required GLIBC versions exceed the recipe's sysroot. The candidate is unqualified and neither it nor its full recipe/source archive is published.
- `preview-library.png`, `preview-controls.png`: actual dummy-SDL screenshots of the development UI and fictional sample collection. No games or working-device state are shown.
- `preview-appearance.png`: actual dummy-SDL rendering of the common PPSSPP appearance review using copied host configuration and an explicitly synthetic profile. This is the outer frontend, not PPSSPP running on a device.

Build artifacts are reproducible from the committed source using the development builder; GitHub Actions uploads fresh artifacts after a successful run. Adjacent development verification keys do not establish production publisher trust. New ephemeral signer invocations intentionally produce different signatures; unsigned ZIPs and same-key archive rebuilds are deterministic under the same inputs/toolchain.

Still unqualified: the candidate's SDK ABI mismatch, actual installed-device loader/driver compatibility, physical controls/rendering/performance, launch/save/return behavior, suspend/power/USB, installed-path/writer inventory, FAT/exFAT interruption and internal boot/scene restoration. These results must not be represented as a device release pass.
