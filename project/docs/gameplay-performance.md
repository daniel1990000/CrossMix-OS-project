# Gameplay observations and fair comparisons

The existing process sampler now accepts exact PSP or PS1 game-and-scene
identities. `tools/gameplay_benchmark.py` records available native observations
and compares matched gameplay runs. These tools do not launch a game, change an
emulator, generate PS1 playlists or select a recommended preset.

Keep frontend library/menu timing, process resources and gameplay observations
in separate reports. A returned SDL presentation call or a CPU/RSS sample cannot
supply native game speed, gameplay FPS, physical frame pacing or input latency.
FPS and native speed are different observations: a game can deliberately render
at 30 FPS while running at its intended speed.

## Record one run

Create a private run manifest with these fields. The values below describe the
format; replace every placeholder with an observed identity before recording.
The `settings.sha256` hashes the exact selected configuration bytes, including
effective per-game overrides. `settings.values` records all selected native
gameplay keys so that a comparison can identify individual changes. Record
frameskip explicitly, including automatic frameskip. If the settings span
several files, retain a canonical path-and-SHA-256 inventory and hash that file.

```json
{
  "identity": {
    "system_id": "PSP",
    "game_id": "existing-library-game-id",
    "game_title": "Owned game or redistributable test software",
    "content_sha256": "<64 lowercase hex characters>",
    "scene_id": "repeatable-scene",
    "scene_definition_sha256": "<hash of exact route, start and end conditions>",
    "device_id": "operator-recorded-device",
    "environment_sha256": "<hash of complete fixed-condition record>",
    "evidence_class": "operator-declared-physical-device",
    "emulator": {
      "id": "ppsspp",
      "version": "exact observed version",
      "binary_sha256": "<observed executable hash>"
    },
    "settings": {
      "sha256": "<exact configuration inventory hash>",
      "resolution": "1x",
      "frameskip": "0",
      "values": {"Graphics.InternalResolution": 1, "Graphics.FrameSkip": 0}
    },
    "frontend_id": "spruce-classic",
    "intended_speed_percent": 100
  },
  "run_id": "baseline-scene-run-1",
  "pair_id": "scene-pair-1",
  "duration_seconds": 30,
  "sustained": false,
  "demanding_profile": false
}
```

For PS1 use `system_id: "PS1"` and record the existing emulator/core and its
exact identity. For a playlist, the content inventory covers the playlist and
every selected disc; the scene definition identifies the active disc. An engine
version string alone is insufficient. `environment_sha256` binds the actual
device, firmware, filesystem, display mode, brightness, radio and charging state,
CPU policy/clocks, initial battery/thermal conditions and other fixed conditions.
Retain that underlying record with the report; a hash alone does not describe it.

An observations JSON file maps each measured metric to its value, measurement
method and retained raw evidence. Omit an unavailable metric or use `null`.
At least one actual observation is needed to record a gameplay report. This
format is an evidence import, not an automatic parser of an emulator HUD.

```json
{
  "native_speed_percent": {
    "value": 100,
    "unit": "percent",
    "method": "native-counter",
    "evidence_file": "/private/run-1/native-speed-observations.txt",
    "evidence_sha256": "<hash of retained observation file>",
    "start_seconds": 0,
    "end_seconds": 30
  },
  "native_fps": null,
  "input_latency_ms": null,
  "battery_energy_wh": null
}
```

The example's 100 is a format illustration, not a project measurement. Record
how values were sampled and aggregated in the raw observation file. Native FPS
and speed require an identified native counter. Frame-time p95 requires a native
frame log or documented video analysis. Audio faults require a reviewed audio
recording; latency requires physical video; energy requires a calibrated
instrument. A zero fault count is measured evidence, whereas `null` means that
audio was not measured. Evidence imports check nonempty regular files, their
hashes, units, finite values and observation windows before writing a report.

```sh
PYTHONPATH=project python project/tools/benchmark.py --gameplay-identity /private/identity.json --profile existing-library-game-id --scene repeatable-scene --pid 1234 --seconds 30 --output /private/resources.json
PYTHONPATH=project python project/tools/gameplay_benchmark.py record --manifest /private/run-1.json --observations /private/run-1-observations.json --resources /private/resources.json --output /private/run-1-report.json
```

The optional resource report remains a separate attachment. The existing
sampler attaches to an already running PID and never terminates the game.

## Compare selected scenes

1. Measure existing spruce with its current engine and settings.
2. Measure our interface with the **same engine and settings**. Supply five
   distinct matched pair IDs and five independent run IDs in each arm. Use the
   same game, scene definition, duration and fixed-condition record.
3. Test one native setting change at a time on the same frontend and engine.
   Use `--comparison setting`. Candidate preset bundles stay untested until
   their constituent tradeoffs and complete profile have been measured.
4. Test an emulator change separately with `--comparison emulator`. Retain
   configuration equivalence and compatibility evidence rather than attributing
   combined engine/settings changes to the interface.
5. For demanding release profiles retain a separate matched **30-minute**
   sustained run per arm. Mark those manifests `sustained: true` and record
   observations over the complete sustained interval, including audio behavior.

```sh
PYTHONPATH=project python project/tools/gameplay_benchmark.py compare --baseline /private/b1.json /private/b2.json /private/b3.json /private/b4.json /private/b5.json --candidate /private/c1.json /private/c2.json /private/c3.json /private/c4.json /private/c5.json --metric native_speed_percent --output /private/comparison.json
```

Add `--metric native_fps`, `--metric frame_time_p95_ms` or other actually measured
metrics as appropriate. A selected metric missing from any run rejects the
comparison. Mismatched content, scene, device, conditions, settings, method,
observation windows or run identities also reject it. All five repeats use one
duration and the same method/window for each selected metric, including across
different matched pairs. Demanding profiles require
`--sustained-baseline` and `--sustained-candidate`. Full retained evidence still
needs independent review: metadata and hashes do not authenticate a device.
The comparison rechecks each raw file's digest and rejects identical raw evidence
reused under different run IDs or copied filenames. Retain a separate run-specific
raw observation file, including its time/run identity, for each run; split a shared
capture into distinct retained run slices before importing it. Settings use flat
scalar `Section.NativeKey` entries so that nested preset bundles cannot masquerade
as one changed setting.

Record and compare reject an output path that resolves to an input document or
raw observation, including sustained-run and unselected metric evidence. Use a
separate output filename to preserve the retained evidence. Existing path aliases
are checked before publication.

Report the individual paired differences and spread, intended speed, frame
pacing, audio and image-quality tradeoffs. A higher FPS number alone is not a
recommendation. Publish marketing figures only after actual Smart Pro runs,
with named game, scene, settings, baseline and uncertainty. Neither this tool
nor a host result approves a marketing claim, enables a profile or completes
the existing 13-area device casebook.

## Actual desktop native save/load check

The [desktop receipt](../evidence/release-continuation-20261023/desktop-ppsspp/receipt.json)
records a real stock PPSSPP v1.20.3 x86_64 run with the existing GPL-2.0 BlockOut II
PSP v1.0 public release. A test-only SDL key harness exercised native Save State,
Load State and normal quit. The retained native log explicitly records completed
state writing and completed deserialization of that same state. Emulator,
package, EBOOT, state and post-run configuration hashes are retained; downloaded
emulator/game/state binaries are outside the repository.

This is a headless CPU/native serialization check. Vulkan initialization was
unavailable; the run selected software rendering and printed an OpenGL diagnostic.
No rendered gameplay correctness, display behavior, audio quality or performance
metric was established. The stock desktop binary does not contain our Smart Pro
save-completion/load-acknowledgement patches. Their project integration harnesses
and actual-device qualification remain separate evidence paths. Earlier attempts
that did not retain input interposition are described in the receipt rather than
counted as successful native save/load checks.
