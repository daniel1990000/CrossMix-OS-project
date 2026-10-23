# Per-game performance options

The existing Game information panel exposes three native PPSSPP settings:
rendering resolution, manual frameskip and automatic frameskip. Lower resolution
reduces image detail. Frameskip drops drawn frames and changes visible motion.
These settings do not raise the emulated PSP's intended game speed, change its
clock, or replace PPSSPP. The two named candidate selections are **untested**;
neither is a recommended release preset before game-and-scene measurements.

PS1 uses its existing per-game emulator-options route. The selected emulator,
playlists, game files and memory-card locations stay with the existing authority.

## Configuration and preservation

`psp_shell.performance.PPSSPPPerformanceManager` takes the existing
`PPSSPPExperienceManager` and a trusted `game_configs` mapping from stable shell
game IDs to **existing** relative native per-game INI paths. Each path must belong
to both independently verified component inventories. The installed source/config
authority must supply the association; PPSSPP uses its own game/disc ID for
`<game-id>_ppsspp.ini`, whereas shell IDs identify system/path records. A required
trusted live `game_identity(game_id)` callback observes the current ROM SHA-256,
native game ID, selected preset, selected engine, executable path/hash and actual
per-game `config_path`. The native ID must match that INI's filename, and the
selected executable must match the existing qualified authority. The exact live
identity is rechecked before each write, Undo and recovery; replacing content at
the same ROM path or changing the preset invalidates earlier transactions. A
static map without that live observer is unavailable. The callback must read the
current installed authorities; a cached association is insufficient.

The manager never infers the native ID from a filename, creates an override, or
silently switches an emulator. Several library records can share a native configuration;
status and preview explicitly report this before editing it.

The existing stopped-writer lease, component locks, exact binary/profile gates
and complete per-game inventory checks protect each operation. The manager uses
the existing `_Transactions` rollback machinery with a separate generation and
journal. Construct/recover it before accepting settings commands, through the
trusted runtime's injected manager slot. Shipped unqualified profiles remain
unavailable, with an explanation and the existing native-settings route.

`status(game_id)` describes current local values and inherited global values.
An unread or unqualified value is **unavailable**, not an assumed default.
`preview({game_id, changes, expected_generation})` records the exact selected
edits, profile identities, global INI and complete override inventory.
`apply({preview_id, request_id, expected_generation})` rejects changed settings
or stale evidence. `undo({transaction_id, request_id, expected_generation})`
reverses only its supported edits and preserves independent later owner edits.
An external change to an owned option produces a conflict instead of overwriting
the owner's value. Request IDs support idempotent retries.

Each option also offers **Use global setting**, which removes only that selected
override. Other per-game options, mappings, comments, global settings and
unselected INIs are preserved. Undo of a removed option restores its original
token and inline comment; if unrelated edits happened meanwhile, the restored
line can move within the same section. With no intervening changes, Undo restores
the exact original file bytes.

Native interactions are checked rather than silently changing more settings:

- Manual frameskip is inactive while automatic frameskip is enabled. Turn auto
  off first, or explicitly include both choices in a reviewed transaction.
- PPSSPP can turn off Skip Buffer Effects when enabling auto frameskip. The
  shell rejects this combination and directs the user to native game settings.
- Resolution is inactive with Software Rendering or Skip Buffer Effects. The
  shell explains that conflict without changing either existing option.

The source contracts are pinned in
[`performance-source-lock.json`](../ppsspp/performance-source-lock.json).
These are source observations, not Smart Pro gameplay measurements.

## Verification boundary

`test_performance_controls.py` exercises the actual existing journal, locks and
profile gates with disposable synthetic installed-card fixtures. It covers
override/global preservation, inherited options, independent edits, stale global
and per-game previews, interrupted writes, process-death recovery, Undo conflicts,
running writers, native interlocks and shared native configurations. A source
test verifies the exact pinned native settings and interlock definitions.

These tests do not execute native PPSSPP, qualify an installed Smart Pro profile,
or measure gameplay. Device qualification must compare fixed game scenes against
existing spruce with unchanged emulator/settings first, then test each setting
separately. Record resolution, frameskip, intended game speed, pacing and audio;
use five matched runs and 30-minute sustained demanding profiles before choosing
release recommendations. Unavailable observations remain unavailable.
