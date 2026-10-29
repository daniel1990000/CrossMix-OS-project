# Dev20 next-round evidence

This round starts at dev19 handover commit
`1ef6aa1e7856a93ed2328b60cbf04eff88dc914a` on a separate development branch.
Prior package and CI receipts retain their original identities.

`startup.json` records remote inspection and input recovery. The recovered private
ISO passed the complete SHA-256 check; no game bytes are stored here.

`native-interruption.json` records deterministic SIGSTOP/SIGKILL probes in a host
harness compiling the exact patched native functions. Its serializer and platform
services are explicit fixtures. This is neither a whole-emulator kill nor a power
failure test. Raw disposable fixture trees and the compiled harness remain private;
the reproducible capture entrypoint is
`project/ppsspp/tests/capture_state_interruption.py`.

The interruption result is a diagnostic finding, **not preservation acceptance**.
Incomplete future receipts are rejected. However, replacing `save-completed`
before the final result can lose the prior receipt, and replacing the same slot
can invalidate its former path/hash. Native Undo bytes at another path do not
constitute an authenticated preserved checkpoint. Generation-bound immutable
payloads and coherent publication/recovery remain unmet; production gates stay
disabled.

The original register remains 14/25 and physical acceptance remains 0/13.
