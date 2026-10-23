# Dev14 to release continuation

This work extends the existing PSP experience on `build/spruce-psp-experience`,
PR #1. Dev14's published computer preview and 1,011 passing checks remain the
baseline. Its exact build and artifact identities remain in the historical
receipts. The changed original-only development package is dev15; it does not
replace a native emulator build or enable device activation.

## Added behavior

- Per-game PPSSPP rendering resolution, manual frameskip and automatic frameskip
  use the existing profile, writer locks and journaled settings authority.
  Preview, Apply and Undo preserve unselected settings and user overrides. Native
  interactions are checked before writes. Trusted native game-to-INI identity is
  required; the UI never guesses a filename from a ROM basename. Candidate
  presets remain untested. PS1 retains its current emulator options.
- Gameplay reporting records named PSP/PS1 games and scenes, exact emulator and
  settings identities, observation methods and retained evidence. It rejects
  incomplete or incompatible comparisons. Existing process and menu timing stay
  separate; unavailable FPS, latency, battery and other observations remain null.
- Game information includes artwork, system, selected emulator/preset,
  availability, Resume status, existing launch actions and native game options.
  PS1 disc information reads existing M3U/CUE references and warns about missing
  or malformed entries. PBP internal disc counts remain with the native emulator.
- Search stays combined with the selected system. Favorites and Continue Playing
  can filter PSP or PS1, retain history order and paginate without changing IDs.
  Start opens the filter dialog; desktop Tab has the same action.
- Continue Playing distinguishes authenticated Resume available from Recently
  played and explains unavailable Resume. Checkpoint timestamps remain original
  verification times. Backup status performs fresh readback with existing
  recovery tools and shows each selected scope. Physical restore and independent
  storage remain separate evidence. Supported screen actions recheck bytes,
  display recovery instructions or export existing redacted diagnostics.

No playlist generator runs, no game file moves, and neither memory-card locations
nor the selected PS1 emulator changes. Missing artwork uses the existing
placeholder. Existing controller ownership, launch/return, classic fallback and
production qualification gates remain in force.

## Validation and release boundary

[The continuation evidence](../evidence/release-continuation-20261023/verification.json)
records all 1,092 strict passing checks (1,031 host/source plus 61 PPSSPP), zero
skips/errors/failures, packaging, installed smoke/rollback and byte-identical
preview/source ZIPs rebuilt from the no-Git source export. Clean build commit
`65fdc58` contains 66 payload files and 222 inventoried original-source files.
The [desktop native receipt](../evidence/release-continuation-20261023/desktop-ppsspp/receipt.json)
records stock PPSSPP v1.20.3 serialization/deserialization completion using
existing GPL2 BlockOut II PSP software. It establishes no rendered/audio,
custom integration, gameplay-performance or device result. The unchanged starting head was
independently certified first: 1,011 checks passed against all five pinned source
references, with zero failures, errors or skips. Source integration tests and
native desktop PPSSPP observations are distinct from Smart Pro qualification.

Use the existing recovery preparation and 13-area device casebook. Compare
spruce and this frontend with the same emulator/settings before changing an
individual setting or engine. Each scene needs five matched runs; demanding
release profiles also need a 30-minute sustained run. Record intended speed,
frame pacing, audio, resolution and frameskip. Choose recommended presets only
from those results and identify the game, scene, settings and baseline in any
marketing figure. No gameplay improvement percentage has been measured here.

PR #1 remains draft, all device gates remain disabled and no native binary or
upstream patch is selected. Public native distribution, production key custody
and maintenance ownership retain their existing open criteria. State-gallery
expansion, named save history and Resume after power-off follow later.

CI run 39923557908 independently passes all 1,092 checks on clean PR merge
`aa1106734f392cc3506ede13fa642cdadb0a54b2`. The downloaded artifact passes
[full checksum, signature, payload and source readback](../evidence/release-continuation-20261023/ci-readback.json).
The branch build and CI merge have separate frontend identities and the same
222-file source inventory. Later evidence/handover edits retain their own source
identity; the exact implementation build remains 65fdc58.
