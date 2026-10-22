# Host library and presentation measurements

U04 and D04 provide repeatable host workloads and device measurement tools.
They do not establish TG5040 speed, physical input latency or battery life.

## Library workload

```sh
PYTHONPATH=project python project/tools/library_benchmark.py --count 10000 --repeats 5 --output /tmp/library.json
```

The tool creates a new temporary card containing synthetic, non-playable files.
It measures the first query, five pages and five searches separately through
the read-only snapshot and injected live-manager adapters. Fixture construction
is excluded from query timing. The first query is not cold UI startup.
The corpus includes Latin, Japanese, Arabic, Korean and long titles. Tests add
duplicate basenames, empty/malformed entries, complete pagination, refresh/focus
restoration and finite source/cache budgets. Game contents are not validated.

The retained baseline rebuilt all 10,000 live records for every query: page
median 5,927 ms and search median 6,126 ms on the recorded x86_64 host.
The bounded live cache now normalizes each existing manager list once per
explicit refresh. It preserves upstream manager objects and basename preset
semantics. Empty ROM files remain visible for review with launch unavailable;
invalid individual models do not hide valid entries. Search normalizes Unicode
to NFC before case folding. No second ROM scanner or launch authority is added.

The preliminary corrected run measured live page median 21 ms and search
median 15 ms. These are one synthetic workload, not whole-application/device
improvements. Original baseline and exploratory samples are retained in
`project/evidence/host-batch3/`. The final comparison uses the recorded policy:
first query and snapshot query p95 must stay within 25% of baseline, allowing
250 ms startup and 5 ms query noise; live page/search p95 targets are 100 ms.
This policy was chosen after exploratory measurements, before the final check.
It is not a preregistered device budget. CI checks semantics and sample shape;
it does not assert machine-dependent wall-clock limits.

## Presentation and resource sampling

```sh
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy PYTHONPATH=project python project/tools/ui_benchmark.py --frames 120 --warmup 20 --output /tmp/frames.json
PYTHONPATH=project python project/tools/benchmark.py --profiles-file project/profiles/measurement-scenes.json --list-scenes
PYTHONPATH=project python project/tools/benchmark.py --profiles-file project/profiles/measurement-scenes.json --profile frontend-classic --scene settings-navigation --pid 1234 --seconds 30 --metadata /tmp/conditions.json --output /tmp/classic-resources.json
```

Replace the PID and metadata with an already running, identified process and
actual conditions. The resource sampler attaches read-only; it never launches,
signals or changes clocks. It records root/tree RSS, PSS where `smaps_rollup`
is readable, and CPU increments for each PID/start-time pair. Departed observed
CPU work is retained; first-seen work and children missed between samples are
unavailable. Tree enumeration is bounded and exposes truncation. RSS can count
shared pages repeatedly. PSS availability and sampling cost vary by device.

The SDL workload records monotonic timestamps immediately after real standalone
`SDL_RenderPresent` returns, with separate render/present durations and median,
nearest-rank p95 and worst intervals. Twenty warmup frames are excluded. The
scene uses four Down/four Up actions, motion off, with no deliberate pacing.
An embedded observer must call `FrameTimings.record` after the owning PyUI
`Display.present`, never after the embedded renderer's no-op `present` method.
The reusable recorder bounds storage and reports dropped samples. No embedded
production measurement hook is enabled by this work.

## Physical comparison procedure

1. Record exact source/binary/config/content hashes, firmware, filesystem,
   brightness, radios, clocks, battery/charging state and ambient conditions.
2. Measure classic spruce first with unchanged engines and fixed scenes; retain
   raw observations. Set numerical budgets before the candidate comparison.
3. Repeat the same actions/content with the PSP frontend, including idle and
   navigation scenes. Keep startup, steady state and refresh separate.
4. For input-to-photon latency, film the physical button and screen together at
   a documented frame rate, count repeated trials and report frame uncertainty.
   Presentation timestamps alone do not measure this latency or panel scanout.
5. Check audio with a recorded repeatable scene; retain actual glitches as
   observations. Use calibrated energy instrumentation and matched conditions
   for battery claims. USB charging draw and percentage snapshots are insufficient.

Unmeasured panel FPS, audio faults, latency, temperature and energy remain null.
The existing device acceptance programme and qualification gates still apply.
