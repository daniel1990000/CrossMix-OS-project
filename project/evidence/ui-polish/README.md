# Interface polish captures

Actual SDL host renders with original synthetic text and artwork. These are
not photographs of a physical Smart Pro and contain no game data. The displayed
clock comes from the host coordinator.

- [Keyboard at normal text size](keyboard.png), with South as Confirm.
- [Keyboard at maximum text size](keyboard-large.png), with East as Confirm.
- [Decoded QOI artwork and neighboring covers](artwork.png).

Run [capture.py](capture.py) with the documented host dependencies to recreate
the screens. Exact capture digests and verification results are recorded in
[verification.json](verification.json). The [failed startup certification](failed-certification-before-fixture-sync.json)
and [fixture readiness diagnostic](fixture-readiness-diagnostic.json) are kept
separately from the passing count. The original-only development payload
excludes this evidence directory.
