Computer preview of the completed Smart Pro PSP host software through dev16. PR #1 is merged into main. This prerelease runs on a computer; all device/profile activation gates remain disabled and Smart Pro qualification is pending.

Included work:

- PSP-style interface, library/search/favorites/recents, accessibility, game information and read-only PS1 disc warnings.
- Original spruce launch/return and PPSSPP integration helpers, controls/themes and save/Resume plumbing; current PS1 route retained. Native engine patches and binaries are excluded from the attached downloads.
- Per-game performance preview/apply/Undo, evidence-backed gameplay reports, combined system filters and fresh scoped backup status.
- Dev16 fixes evidence/input overwrites, inconsistent protocols across five matched repeats and disc-reference path swaps.

The exact attached preview and matching original-source ZIP are built from `99336f6525efbd1b790a15c7de54acca3eacd1ec`. Full host certification passes 1,099 checks with zero skips, errors or failures against five pinned upstream sources. Packaging verifies the development signature/payload, deterministic rebuilding, installed smoke tests and fixture rollback. The download includes checksums, certification, exact source/build metadata and GitHub workflow provenance. The bundled public key demonstrates development package integrity; production device key custody remains open.

Download `smartpro-psp-0.1.0-dev16-host-preview.zip`, extract it into a new computer folder and follow its RUN.txt. Python >=3.9, SDL2, PySDL2==0.9.17 and Pillow==11.1.0 are required. Use the attached `smartpro-psp-0.1.0-dev16-original-source.zip` for its matching source. GitHub's automatic repository archives include inherited mixed source/runtime and historical engines; they are outside this verified attached-asset scope. MIT/OFL/dependency notices remain included. No emulator, firmware, SDK, commercial game, save or private key is included in these attached artifacts.

Zero of 13 physical acceptance areas have run. Actual device recovery/inventory, physical acceptance, native rendering/audio, custom Resume behavior and gameplay performance remain unqualified. Candidate presets are untested; no speed, latency, battery or improvement percentage is claimed. Hardware comparisons require five matched runs per named scene and 30-minute sustained runs for demanding profiles. Precise public native distribution decisions, production signing/custody and accepted maintenance ownership remain open. State galleries, named save history and power-off Resume remain later enhancements.

The published dev14 preview and all historical dev15/dev16 evidence retain their exact identities. No game files, playlists, memory-card locations or emulator selections are changed by this release.
