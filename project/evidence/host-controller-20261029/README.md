# Synthetic SDL controller queue — 2026-10-29

At source commit `c8cf939f9306ac8ad062afadae05d81c2edca80e`, two bounded host runs passed using PySDL2 0.9.17 and SDL dummy video/audio. The harness pushes paired synthetic `SDL_CONTROLLERBUTTONDOWN`/`UP` events into SDL's queue. The normal standalone preview loop polls them, maps them through `InputMapper`, updates `NavigationModel`, and uses its asynchronous dispatcher. It waits for observed states before issuing each next input. Fresh temporary state and the synthetic `DemoBackend` are used for each run.

- `settings.json`: traversed Games, Continue, Tools and Settings; previewed and applied the interface confirm-button change south to east; verified the east button opens the next preview and south cancels it.
- `launch.json`: opened the synthetic All games entry and game card, observed the demo's explicit no-launch notice, dismissed it, and returned through library to home.
- PNGs capture rendered framebuffers before presentation. Fixture titles and state are synthetic.

```sh
PYTHONPATH=/tmp/trimui-preview-deps:project python3 project/evidence/host-controller-20261029/simulate.py settings /tmp/controller-evidence
PYTHONPATH=/tmp/trimui-preview-deps:project python3 project/evidence/host-controller-20261029/simulate.py launch /tmp/controller-evidence
```

Each run exits on completion, has a 15-second deadline and 1,000-frame limit, and writes its own temporary settings. Input was injected at the SDL event queue, not by a physical or virtual controller device. This checks neither polling of a real controller nor held/repeat behavior, launch handoff, return from a running application, real game launch, authenticated Resume, or device performance. The launch notice is the demo model's refusal; it is not evidence of a production bridge refusal. No profile or runtime gate was enabled, and no game or ISO was used. An independent Terra review checked the harness and its claims; its frame-bound concern was addressed by increasing the limit and exiting immediately on completion. No product source was changed.
