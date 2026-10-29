# RetroPass in PSP UI — dev20 host evidence

Checked implementation and artifact source: `25d594c5ca26b9d1b927d32d44f04cef0697c420`. Later evidence commits retain their separate identity.

`verification.json` and `certification.json` describe the final strict run against all five pinned source trees. `build-report.json`, `release-source.json`, `no-git-rebuild.json` and `SHA256SUMS` bind the installed preview and corresponding source to captured bytes. `review.json` records the bounded independent review and fixes.

`psp-home.png`, `psp-library.png`, `psp-library-large.png` and `psp-help-large.png` are actual SDL captures using the default PSP presentation and synthetic sample titles, at 100%/175% text. They show no running game and establish no device performance result.

The new preview retains complete upstream RetroPass source, adapted GPL Python source and notices. It includes no game, save, firmware, emulator binary or private key. Published dev16 assets remain unchanged.
