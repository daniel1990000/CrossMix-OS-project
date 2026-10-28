# Private host gameplay audit collector

`tools.host_gameplay_audit` consolidates the dev19 native counter collector,
PID/listener checks, frozen input copies and existing gameplay importer/comparator.
It is development tooling, excluded from the installed payload. Linux `/proc`,
X11, `xdotool` and a development installation of `websockets` 15 or later are required. Keep
all outputs outside the repository: they contain private content paths, native
logs, state bytes and configuration. No device profile or frontend API is added.

The collector requires an explicit emulator, ISO, starting state, frozen XDG
configuration tree, scene definition and output directory. It hashes full inputs
before and after collection; inode/size/mtime/ctime and config membership checks
run during acquisition. SHA-256 is streamed, so a large ISO is not read into RAM.
Copies of the frozen configuration are retained separately from the native
process's writable run configuration. No template is regenerated from live INIs.

## Freeze before collecting

Prepare two complete XDG configuration trees with
`ppsspp/PSP/SYSTEM/ppsspp.ini` and `<native-id>_ppsspp.ini`. Explicitly set
`Graphics.FrameSkip=0` and `Graphics.AutoFrameSkip=False`; the only semantic
change between arms is `Graphics.InternalResolution=1` versus `2`. Configure
`General.RemoteDebuggerOnStartup=True`, `General.RemoteDebuggerLocal=True` and
`General.RemoteISOPort` for the explicit collector port. Normal native exit uses
`--escape-exit`. Prepare the game through ordinary gameplay; a convenience state
is a starting fixture, never proof of ordinary savedata restoration.

The frozen scene JSON has `id`, `starting_state_sha256`, `camera` (a concrete
camera description), `warmup_seconds`, `duration_seconds` and
`input_sequence_sha256` (null for a stationary scene). Its exact file digest is
`identity.scene_definition_sha256`. Changes to camera, input sequence, warmup,
duration or state require a new frozen definition before collection. For a scene
that will have demanding-profile comparisons, the **same file must also freeze**
`sustained_duration_seconds` (at least 1800) and
`sustained_input_sequence_sha256` before the first candidate. A sustained run
selects those fields through its explicit `sustained=true` manifest; its
`input_sequence_sha256` binds the selected long sequence. The shared scene file
keeps the state, camera and scene identity identical across repeats and soaks.
A later scene redefinition cannot qualify earlier runs.

The manifest contains the existing gameplay importer fields `identity`, `run_id`,
`pair_id`, `duration_seconds`, `sustained`, `demanding_profile`, and these bindings:

- `emulator_sha256`, `iso_sha256`, `starting_state_sha256`.
- `configuration`: every relative frozen configuration file and its SHA-256.
- `warmup_seconds`, `interval_seconds` (0.25–10 seconds).
- `native_slot` from the legitimate fixture record (never inferred from its
  filename), `native_disc_version` and `native_architecture`. The scene also
  freezes the slot and disc version. `identity.emulator.version` is the exact
  native reported build version, rather than a nearby release tag.
- `input_sequence_sha256`: null, or the exact replay file digest.
- For replay, `controller_shim_sha256` and `input_tolerance_seconds` (0–1 seconds,
  positive, frozen before collecting).

Use `inventory(config_root)` and `configuration_identity(config_root, game_id)`
from this module to construct the manifest's configuration and
`identity.settings`. The latter reads complete effective global/per-game native
values and incorporates other config-file hashes. The declared settings must
match those bytes; changing resolution labels alone fails. The remaining exact
identity fields follow `tools.gameplay_benchmark.validate_identity`. The collector
accepts `evidence_class=host` only.

```sh
PYTHONPATH=project python -m tools.host_gameplay_audit collect \
  --emulator /private/native/PPSSPPSDL --iso /private/game.iso \
  --starting-state /private/frozen/scene.ppst \
  --frozen-config /private/frozen/config-1x \
  --statistics-source /private/patched/Core/Debugger/WebSocket/GPUStatsSubscriber.cpp \
  --manifest /private/frozen/pair1-1x.json \
  --scene-definition /private/frozen/scene.json \
  --port 19362 --xdotool /usr/bin/xdotool --output /private/results/pair1-1x
```

## Corrected statistics and executable provenance

The historical executable `6924b039…56de` is bound to the retained dev19 build,
assembly and patch evidence. The supplied statistics source must match the exact
corrected source digest in `ppsspp/gpu-stats.lock.json`; patch hashes and retained
assembly/build identities are checked too. An arbitrary binary plus a corrected
source file cannot pass this historical binding.

A rebuilt binary has a new identity. Supply `--build-receipt`, its externally
reviewed digest with `--build-receipt-sha256`, and `--review-evidence`. The build
receipt must declare `kind=reviewed-host-statistics-build`, exact
`executable_sha256`, `statistics_source_sha256`, `upstream_commit`,
`statistics_patch_sha256`, and `review_evidence_sha256`. Retained review JSON must
match that digest and declare `decision=accepted_for_host_counter_collection`,
`reviewer`, and the same executable/corrected-source hashes. Review the complete
build/source correspondence before pinning this receipt. These are reviewable
provenance declarations, not cryptographic proof that a compiler produced the
executable from those sources; the collector cannot independently establish that
correspondence or qualify a device. No editable `statistics_corrected` boolean
is accepted.

## Timed analogue input

The optional frozen replay is a JSON list of nonoverlapping events. Each has
`at_seconds` from the status-start acknowledgement, `seconds` (0.01–60), `axes`
(`[LX, LY, RX, RY]`, each -1 through 1), and SDL `buttons` bitmask. Events must end
within the observation window. Build `dev/host_virtual_controller.c` privately
and pass `--input-sequence /private/frozen/inputs.json --controller-shim
/private/frozen/controller.so`. Its exact hash belongs in the manifest. Existing
`LD_PRELOAD` is refused during replay. The fixed development Python helper sends
PID/start/executable-bound commands; the native shim records observed application
timing and neutralizes expired input. Missing/failed/late native applications, observed hold-end timing outside the
frozen tolerance, or late publication fail collection. Requested, published and observed timings and
all failed attempts remain private raw evidence. This records host synthetic
input, not physical latency. Actual moving scene/game acceptance still requires
review of real retained gameplay evidence.

## Process and evidence boundaries

An occupied observer port or any competing PPSSPP process fails preflight. A
fresh helper calls the existing `run_owned_tree` boundary. PID, start ticks,
running executable digest and listening socket inode are bound before and during
observation. Competition during observation fails the run. The only exit input
targets the unique visible X11 window owned by that same PID/start/executable;
no title matching, unrelated window closure, service termination or forced kill
is used. A native window that cannot close normally leaves an explicit failure
and its supervising helper for operator handling; it cannot publish completion.

Raw JSONL is flushed/fsynced for every received response. The nominal analysis
window is `[0,duration)` from status-start, with final unpaused matching-game
acknowledgement required after the window. Late samples are retained and listed
as excluded. Interrupted raw data cannot form an accepted run. Attempts require
new output directories; failure receipts and publication `.partial` files are
preserved. A valid run additionally requires normal owned-tree completion and
unchanged original inputs.

Use five independent 30-second matched pairs for each frozen scene, with arm
order fixed in advance. Keep isolated 30-minute runs for each setting separate
from scene repeats. Compare with five explicit run paths per arm:

```sh
PYTHONPATH=project python -m tools.host_gameplay_audit compare \
  --baseline /private/results/pair{1,2,3,4,5}-1x/run.json \
  --candidate /private/results/pair{1,2,3,4,5}-2x/run.json \
  --output /private/results/comparison.json
```

The tool verifies complete collector receipts, retained frozen config/scene/input
identities and raw digests, recomputes accepted-window means, then delegates to
the existing five-pair comparator. It permits only 1x versus 2x with frameskip
disabled. Native FPS is approximate; tiny differences cannot establish an
improvement. Audio quality, panel frame pacing, latency and energy stay
unavailable. Host observations do not qualify TrimUI presets or production gates.

For demanding scenes, add `--sustained-baseline /private/results/soak-1x/run.json`
and `--sustained-candidate /private/results/soak-2x/run.json` to compare. Both
complete collector reports undergo the same raw/config/input revalidation before
the existing comparator checks identities against the repeat arms. The raw
window and late-sample classification always use each run's actual frozen
duration, rather than assuming the 30-second repeat duration.

### Explicit warmup input

A native SDL axis can cache its first event before forwarding later changes.
If the observed game/input path needs priming, freeze a separate warmup sequence
and supply `--warmup-input-sequence /private/frozen/warmup-inputs.json`. Its
`warmup_input_sequence_sha256` must occur in both the scene and run manifest.
The same event schema applies, with timing relative to warmup start and events
ending within the frozen warmup duration. Nonzero-to-neutral pulses must be
explicitly declared; the collector never inserts hidden priming or changes
native SDL code. Requested/applied/hold-end timing for warmup and measured input
is validated separately against their respective clocks. Both phases share the
same PID-bound controller and retained final native observation log; request
journals are separate. Measured input's clock is additionally bound to the raw
status-start acknowledgement's monotonic timestamp. Final log hashes are recorded
after owned-tree closure, including SDL_Quit neutralization.

### Actual starting-state load acknowledgement

Before native launch the development collector creates a fresh 0700 raw-session
directory and canonical 0600 `request`, using the existing packet codec. Its
random session/request/context IDs bind the copied state, exact game/engine
hashes, explicit fixture slot and format. Both `--state` and the existing
`--project-state-session` extension are passed. Before any warmup input, the
collector requires actual native `result` and `load-completed` packets with
matching fresh context, operation load, sequence1, success, native game ID, disc
version/prefix, exact paths/hashes/sizes, slot, upstream, extension, build version,
architecture and format. Missing, failed, stale or incompletely published records
fail collection. The same packets and copied state must remain unchanged after
normal owned-tree exit and when a report is revalidated. All raw packets and
context hashes are retained privately.

This uses the native trusted-caller diagnostic boundary. No
`QualifiedStateProfile`, production capability, authenticated frontend consumer
or Resume authority is constructed. Slot declarations still require legitimate
fixture review. After the load acknowledgement, each input phase additionally
waits for a retained matching unpaused `game.status` acknowledgement; listener
readiness alone never authorizes warmup controls. The native load callback proves
that the exact state loaded; private visual review must still verify the desired
progress and camera before accepting the frozen scene.
