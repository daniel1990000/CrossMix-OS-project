# Private host virtual controller

This development helper reconstructs the private dev19 SDL input probe and adds
analogue sticks plus recorded command timing. It is not part of the frontend,
installed payload or device activation path. It does not create game progress,
load states or change game/configuration files.

Build the shim with the host C compiler (SDL2 runtime 2.0.14 or later is required):

```sh
cc -Wall -Wextra -Werror -shared -fPIC project/dev/host_virtual_controller.c -ldl -o /private/audit/controller.so
```

Use an owned directory with mode 0700 for command and log files. Launch the exact
emulator through the existing process supervisor with these environment entries:

- `LD_PRELOAD`: absolute shim path (preserve any intentionally selected existing preload).
- `TRIMUI_CONTROLLER_EXECUTABLE`: resolved absolute emulator executable.
- `TRIMUI_CONTROLLER_COMMAND`: absolute command file in the private directory.
- `TRIMUI_CONTROLLER_LOG`: absolute observation JSONL file in that directory.

The normal launcher still owns launch and exit. The helper attaches one SDL virtual
controller inside that process once its existing SDL game-controller subsystem is
initialized. It does not initialize SDL, intercept unrelated windows, send global
keyboard events, or stop another process. Executable-path mismatch prevents attachment.

Send an explicitly timed command using the PID, start ticks retained by the launcher, and exact executable digest:

```sh
python3 project/dev/host_virtual_controller.py --pid PID --start-ticks LAUNCH_START_TICKS --executable /private/build/PPSSPPSDL --sha256 DIGEST --command /private/audit/input/command --record /private/audit/input/requests.jsonl --axes 0 -1 0 0 --seconds 1
```

Axes are left X/Y then right X/Y in [-1, 1]; negative Y is up. `--buttons` is an SDL
standard button bit mask: south 1, east 2, west 4, north 8, back 16, start 64,
left/right shoulders 512/1024, D-pad up/down/left/right 2048/4096/8192/16384.
The emulator's existing mapping determines in-game actions. No remap is written.
Zero axes/buttons release input. All controls return to neutral when the command
expires (10 ms to 60 seconds) and before normal SDL shutdown; deadline delivery
requires the native event loop to poll. A stalled event loop cannot provide precise
input timing. Process termination removes this process-local virtual device.

Commands bind PID, `/proc` start ticks, sequence and monotonic issue/deadline times.
The Python publisher verifies retained launch start ticks and executable path/hash twice. The shim rejects foreign
process, future-issued and expired commands; rejected/late commands neutralize input.
Private regular files are required; symlinks and group/world access are refused.
Use a single command publisher. Atomic replacement keeps partial commands invisible.

The request log records requested/published monotonic nanoseconds. The native log
records actual observation nanoseconds, PID, sequence, values, deadlines and SDL
results. Retain both, including rejected/late commands and unsuccessful attempts.
These are input-acquisition receipts, not proof of a game accepting the action or
measurement of physical latency. Keep game captures, savedata and convenience states
private and separately labelled. Freeze a replay sequence before collecting candidate
measurements; do not select inputs from mutable live configuration.

`python3 -m unittest discover -s project/tests -p test_host_virtual_controller.py -v`
compiles the real shim, verifies actual SDL axis/button readback, automatic neutral,
late/foreign-process rejection and wrong executable/hash preservation. This synthetic
SDL probe does not count as gameplay, physical-controller or save/Continue acceptance.
