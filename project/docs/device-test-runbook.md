# Original Smart Pro device acceptance

The owner confirmed that an original Smart Pro is available, but not for testing
today. These steps prepare the later TG5040 session. No hardware result has been
recorded. Use a spare/restorable card and retain the existing firmware, internal
launcher/scene and battery saves. Package rollback alone cannot restore rootfs.

Prepare [backup verification and actual-device inventory](device-recovery-preflight.md)
first. The [experimental-route design](experimental-device-route.md) records the
execution/admission gap and proposed bounded pilot. The current shipped runtime
still refuses device admission; these procedures do not activate it.

`tools/device_acceptance.py` prepares a private session, captures read-only
inventory and selected save hashes, and records operator observations. It never
starts games, restores data, sends signals, changes clocks/settings, exports
storage, flashes firmware or enables a device profile. The case list covers
recovery, boot/input, libraries, launch/return, state load, native menus,
appearance, settings, power/sleep, USB, storage/update interruption and ports.

Create the session outside the card, preferably in `/tmp` or on a separate host
disk. Copy it to durable private storage before rebooting or exporting USB;
`/tmp` may disappear. The selected save paths stay local and may identify games.
Use the existing redacted support exporter before sharing selected reports.

```sh
python3 project/tools/device_acceptance.py prepare --output /tmp/tg5040-session
python3 project/tools/device_acceptance.py capture --session /tmp/tg5040-session --phase before --save Saves/saves/EXACT_OWNER_SAVE_FILE
python3 project/tools/device_acceptance.py report --session /tmp/tg5040-session
```

Supply each exact battery-save file with a separate `--save`. There is no
recursive save scan, and no content is copied into a report. Files must be
regular, under `Saves/`, and at most 64 MiB each. Emulator state identity belongs
to the engine's completed-state protocol; a battery-save hash is not a state.
Save paths cannot contain symlinks, including aliases to another file on the
same card. Session access retains a directory descriptor under a private regular
file lock, so a directory replacement cannot redirect an evidence write.

For an already-running PPSSPP, `capture --pid EXISTING_PID` also runs the exact
ELF/interpreter/mapped-library probe. That option requires a trusted `readelf`;
the probe does not start an engine or establish rendering compatibility. A
mounted filesystem copy can use `--root` and `--sd-root`, with snapshot evidence
kept separate from a live process observation.

Perform each case through the existing device interface and reviewed candidate
procedure. Record the actual result, exact candidate/profile identity, observed
behavior and retained external evidence references in the note:

```sh
python3 project/tools/device_acceptance.py record --session /tmp/tg5040-session --case input --status blocked --note 'External-controller test not run; no controller attached.'
```

Each retest appends an attempt linked to the previous attempt's hash. It never
rewrites a failure as a pass. Captures are exclusive; use a new session for a
new baseline. Before/after captures must select the same save files and retain
the observed root/card filesystem identities. A replacement filesystem or copied
card needs its own session; these host filesystem identities are not device
serial numbers or proof that two mounts contain the same physical card.

```sh
python3 project/tools/device_acceptance.py capture --session /tmp/tg5040-session --phase after --save Saves/saves/EXACT_OWNER_SAVE_FILE
python3 project/tools/device_acceptance.py report --session /tmp/tg5040-session
```

Changed hashes are reported without overwriting newer saves. Expected gameplay
changes and unexpected corruption require separate interpretation. A selected
save must exist at the baseline. If it or its parent directory disappears before
the after capture, the snapshot and report retain `missing=true` and
`unchanged=false` for that exact path. They do not recreate the file or restore
the older save. Record the observed failure and investigate it before continuing.
Symlinks, special files, permission failures and files changing while being
hashed still fail collection; they are not treated as absent saves. These
observations do not establish whether storage loss was caused by the candidate.
A missing, stale, cross-session or edited evidence reference is rejected. Content checksums
cover snapshots and every attempt, and historical snapshot references are
checked along with the latest observation. These checks detect inconsistent or
accidentally edited files. They are not authenticated attestations: an operator
who rewrites all checksums and references can rewrite an observation. Operator pass
notes are observations for review; even an all-pass report keeps
`hardware_qualified=false`, `automatic_activation=false` and
`review_required=true`. A trusted installed profile needs review of the actual
firmware, source/runtime hashes, writer ownership, restore, state and foreground
lifecycle evidence. These files cannot turn arbitrary card JSON into authority.

Source-use notification and redistribution review remain separate from this
device session. The independent host preview can be checked before those steps;
they are not replaced by synthetic test results.
