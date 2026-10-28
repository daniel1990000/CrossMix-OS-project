# Optional debugger GPU timing copy correction

The pinned PPSSPP v1.20.3 debugger collector stores timing samples in
`std::vector<float>`, but its two `memcpy` calls use `sizeof(double) * valid`.
For nonempty timing history, the requested destination write exceeds the vector
size; a full 600-sample history also reads beyond the source float array.

The optional `0005-gpu-stats-float-copy.patch` uses the source element type for
each byte count and `vector.data()` for the destinations. It changes neither
the timing values nor the debugger JSON protocol. `gpu-stats.lock.json` pins
the source, patch and resulting file. It is separate from the existing native
menu/state/session patches and does not enable a shipped profile or select a
device binary.

`tests/test_gpu_stats_patch.py` compiles the exact original and patched
`FlipListener` function and `CollectedStats` type with explicit display-service
stubs under AddressSanitizer and UndefinedBehaviorSanitizer. The original
nonempty case must reproduce a heap overflow; the fixed empty, one-sample,
partial and full histories must preserve all float values and request behavior.
This is source-level host acceptance, not a complete emulator or device run.
Any complete build and live endpoint result needs its own exact binary evidence.

Do not use `gpu.stats.get` or `gpu.stats.feed` on the uncorrected build for
measurement. The native FPS/speed HUD is a separate observation route. The
debugger endpoint can control execution and memory, so any private test use
must identify the actual server scope; `RemoteDebuggerLocal` controls the
debugger UI location and is not a loopback-listener guarantee.
