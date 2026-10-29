# RetroPass dev19 host evidence

Implementation and artifact source: `2858f3155c03d2efca3fd1cf364151e4d516fd5e`. Later evidence commits preserve their own identity.

- `verification.json` and `certification.json` describe the exact final host run.
- `build-report.json`, `release-source.json`, `no-git-rebuild.json` and `SHA256SUMS` bind the installed preview and full corresponding source to captured bytes. Both ZIPs rebuilt identically from the exported source without Git.
- `review.json` records independent lane review and reproduced fixes.
- `library.png`, `library-large.png` and `help-large.png` are actual SDL host captures with synthetic sample titles, at100%/175% text. They do not show a running game or establish physical-device performance.

The published dev16 release remains unchanged. The new host preview and source ZIP are retained outside the repository; no game, save, firmware, emulator binary or private key is included.
