# Bounded host frontend preview — 2026-10-29

At repository commit `6848e216b8d46913029d9c72b24864a990818acf`, the standalone synthetic demo rendered five independent headless previews, each two frames at 1280 × 720: home, library after `down,menu`, collections after `confirm`, controls, and search. Four captures are retained here. Inspection showed library tools, the Play later collection, native-menu controls with unavailable profile status, and the search keyboard. Demo titles are fixtures. No games were launched. The preview's scripted actions call the navigation model directly and do not exercise InputMapper or physical controls.

With PySDL2 0.9.17 installed in a temporary host directory, `PYTHONPATH=/tmp/trimui-preview-deps:project python3 -m unittest project.tests.test_ui_input project.tests.test_ui_library_workflow -v` passed 29 tests, zero failures, errors or skips: eight SDL event-fixture InputMapper tests and 21 library, delayed-action and backup-history model tests. An initial run without PySDL2 passed the other 21 and skipped those eight; the dependency-equipped rerun is the result above. SDL event fixtures are not physical input.

Example capture command (each screen used a fresh temporary state directory):

```sh
PYTHONPATH=/tmp/trimui-preview-deps:project python3 -m psp_shell --demo --headless --width 1280 --height 720 --frames 2 --screen library --actions down,menu --state-dir /tmp/trimui-simulation/state-library --screenshot /tmp/trimui-simulation/library.png --report /tmp/trimui-simulation/library.json
```

This short host smoke is not full certification, a hardware test, a performance measurement, gameplay, or authenticated Resume acceptance. No device/profile gates were enabled.
