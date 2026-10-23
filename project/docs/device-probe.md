# Read-only device readiness observations

`tools/device_probe.py` adds D03 engineering preparation. D03 remains open:
no original TG5040 was connected, inventoried or tested for this work. The tool
cannot activate a candidate, grant source-use permission, qualify a runtime or
replace the D02 physical restoration rehearsal.

The collector reads a small fixed metadata allowlist through the existing
anchored `InstalledTree` reader. It records:

- Original-model candidate labels and all observed installed firmware versions,
  preserving conflicts. Smart Pro S and Brick labels do not select TG5040.
- Kernel release, boot UUID and an optional existing PID/start-time identity,
  checking boot and process identity again after collection.
- Only the root/card mountpoints, filesystem types and whitelisted flags.
  Mount sources, account names and arbitrary mount options are omitted.
- Exact Python/readelf bytes and hashes. Offline tools never execute. Optional
  live `--version` calls use the same already-open file descriptor as hashing,
  then recheck both the descriptor and its current pathname identity.
- Optional isolated kernel observations from a new disposable helper: child
  subreaper adoption/wait, sealed memfd read across `exec` with rejected writes,
  and Unix peer credentials compared with the known disposable child. The
  `kernel_helper` record separates capabilities from the actual interpreter
  and source hashes used by that invocation.

The collector never reads process arguments/environment, game maps/content,
network settings, private keys or whole boot scripts. Kernel/process identities
and tool hashes remain private evidence; review any report before sharing.
Model labels and tool hashes are observations, not authenticated hardware or a
trust decision about an arbitrary executable supplied by an operator.

## Offline copied-root inspection

Prepare the complete recovery payloads separately. Inspecting copies does not
prove that those payloads restore a device, identify live libraries, or establish
target kernel support:

```sh
python3 project/tools/device_probe.py \
  --root /private/root-copy --sd-root /private/card-copy \
  --python /usr/bin/python3 --readelf /usr/bin/readelf \
  --output /private/evidence/device-readiness-static.json
```

The two tool names are absolute paths **inside the inspected root**, with normal
installed symlinks resolved inside that root. `/mnt/SDCARD` maps to the explicit
card copy. Missing files and unsupported observations stay unavailable; no host
file is substituted. An optional `--pid EXISTING_PID` inspects captured `/proc`
metadata, retaining its copied-root provenance.

`--kernel-probe` and `--tool-versions` are rejected for offline roots, including
at the low-level tool-version boundary. No copied binary or launcher executes.

## Future live observation after recovery readiness

After actual D02 recovery readiness and operator review, the same collector can
observe the already-running device with `--root /` and the actual SD root. Select
the installed trusted Python/readelf paths explicitly. `--pid` names an existing
process; the collector never starts that process or an emulator to fill a report.
`--tool-versions` opts into the two supplied trusted `--version` commands only.
`--kernel-probe` opts into the disposable helper only, on the collector's kernel.
No combination enables the experimental frontend or changes a production gate.

The helper executes the actual current Python interpreter and this collector's
source through already-open, hash-verified descriptors. Its record binds those
bytes before and after execution, including pathname replacement checks. The
helper loads no project modules from the inspected card: it uses the standard
library only. The separately inventoried `--python` path is not claimed to be
the helper's interpreter. Complete standard-library/runtime dependency closure
still requires the existing runtime inventory and review.

The helper has a five-second outer deadline and bounded output. Version commands
have a three-second deadline. A process that closes both output pipes and
then hangs remains subject to the same deadline and records an unavailable
observation, rather than escaping as an unhandled timeout. On completion or
timeout/overflow, cleanup signals only the new disposable subprocess group while
its root is still an unreaped owned child. Closing both output pipes and exiting
successfully cannot leave a child in that group running. Cleanup never signals
a reaped group. An
observed PID, game, service or foreground owner is never signalled. The helper changes only its own process state
and uses a temporary local Unix socket, without a persistent/network service.
It tests descriptor inheritance through the current trusted Python interpreter;
it does not establish the entire candidate launch chain or graphics behavior.

Reports say `live collector host` for `/`, even when that host is a development
machine. A successful host helper is not target evidence. A live report still
sets `hardware_qualified`, `runtime_verified`, `physical_restore_tested` and
`automatic_activation` to false. No display, input, audio, save, full writer
inventory, startup recovery or physical media test is performed.

## Evidence storage and checks

Output must be a new explicit filename outside the inspected offline root/card.
For live `/` inspection it must be outside the SD card and `/proc`, `/sys` and
`/etc`. The existing recovery-report writer publishes complete fsynced bytes
exclusively and fsyncs the parent; a failed publication/sync is not success and
existing receipts are never overwritten. Retain completed reports independently
and compare a fresh retrieval with their recorded hashes before reboot/export.
That operational retention is still a separate operator task.

Twenty-five focused host tests exercise copied-root provenance, missing tools/APIs,
malformed/oversize/FIFO data, path replacement and containment, PID/boot changes,
version-time mutations, output/deadline bounds, failed publication, and the fresh
host helper. Run them with:

```sh
PYTHONPATH=project python3 -m unittest discover \
  -s project/tests -p test_device_probe.py
```

These tests supply host engineering evidence. They do not complete D03 or any
physical acceptance area.
