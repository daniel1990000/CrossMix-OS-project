# Optional PPSSPP completed-state evidence

This separate GPL-2.0-or-later patch adds an **in-process, qualification-only**
`SaveState::SaveSlotWithEvidence` API to upstream v1.20.3. It has no installed
caller, external command, socket, manifest exporter or automatic save-and-quit
behavior. Resume remains unavailable on the shipped profiles.

[state-evidence.lock.json](state-evidence.lock.json) pins the untouched source,
patch and resulting files. This patch composes with the native-menu patch but
is deliberately excluded from the default candidate's `source-lock.json`.
The existing complete PowerVR build and its executable hash do **not** contain
this API. Neither a complete engine build nor a device test of this optional
patch has been performed.

## Completed operation and identity

The API uses the running emulator's `PSP_CoreParameter().fileToStart`, positive
SFO `DISC_ID` and `DISC_VERSION`, `GetGamePrefix` and `GenerateSaveSlotPath`.
It never derives a slot from a ROM basename in Python. The caller supplies
only a bounded request identifier and a slot; it must invoke the API on the
existing emulation owner thread, never from a signal handler.

The real `SaveSlot` / `Save` / `Enqueue` / `Process` lifecycle performs the save.
No evidence is emitted when an operation is merely enqueued or a screenshot is
requested. After the serializer reports success, final slot rename must also
succeed. The patch fixes upstream `SaveSlot`'s ignored rename result and reports
networking/hardcore policy rejection through the existing callback instead of
silently accepting it. Warnings cannot produce successful evidence.

Successful evidence includes the exact request, native slot path, slot number,
SFO identity and engine-generated prefix; the pinned upstream commit, extension
and source-format identifiers; the generated engine version and architecture;
and SHA-256 plus size for the current ROM, actual Linux `/proc/self/exe`, and
completed state. ROM and executable fingerprints must match before and after
the asynchronous operation. A session generation invalidates pending evidence
after engine shutdown or reinitialization. A replaced ROM, changed active game,
failed write, failed rename, missing or empty state produces no evidence.

The format label records the locked chunk-header revision 5 and SaveStart
section version 3. It is a conservative source identity, not a declaration that
every state loads successfully in every configuration or engine build.

## Resource and callback contract

Hashing streams through a 64 KiB buffer and checks regular-file identity, size,
mtime and ctime on the open descriptor and named path. Nonblocking opens reject
FIFOs and directories without waiting for a writer. ROM input is limited to
8 GiB; executable and state inputs to 512 MiB. Empty/unreadable inputs,
unsupported paths, directory-based homebrew and missing positive SFO identity
are refused. The API supplies evidence only on Linux SDL builds.

Complete ROM hashing before and after a save can pause emulation for large ISOs.
This deliberate opt-in API is for qualification work. There is no enabled UI
or hotkey caller. Production use needs a measured scheduling plan on TG5040 and
must preserve the emulator's state and thread ownership.

Copy `SlotEvidence` inside the callback: its pointer is valid only during that
call. Every delivered failure has a null evidence pointer; successful evidence
is delivered at most once. Synchronous rejection and asynchronous completion
can use different existing threads. A missing callback does not queue a save.
An operation never processed before core termination may have **no callback**;
loss of completion remains unavailable evidence and must never be converted to
success by a timeout, screenshot or process exit.

The request ID is correlation, not authentication. A later trusted integration
must bind it to the independently retained launch request and ROM fingerprint,
the qualified installed engine hash and state format, the approved state root,
and the existing foreground lifecycle. This API neither sets nor proves
`clean_shutdown`. A C++ callback also does not establish physical-card durability,
save/load compatibility, absence of another writer, successful poweroff or
successful foreground return. The saved record must be rechecked before a
qualified state-load action is offered. Do not load arbitrary card JSON as an
authority or mark a recent entry resumable from this API alone.

## Host acceptance

```sh
PPSSPP_SOURCE_ROOT=/path/to/pristine-v1.20.3 \
PYTHONPATH=project python3 -m unittest discover \
  -s project/ppsspp/tests -p test_state_evidence_patch.py -v
```

The harness compiles the actual patched queue, save, slot-finalization,
processing, evidence and session functions, together with the real locked
PPSSPP SHA-256 implementation. It exercises asynchronous completion, failed
write/rename, policy rejection, content replacement, changed game/session,
nonregular/empty/oversize inputs, duplicate completion and unsupported builds.
An independent Python SHA-256 calculation verifies the exact fixture engine,
ROM and state hashes. A composition check applies both optional and existing
native-menu patches to a copied, verified source tree.

Emulator, serializer, screenshot and platform services are narrow, explicit
fixtures. Fixture bytes are not real PSP states. The source-format constants
are checked against locked `Serializer.h` and `SaveStart::DoState`. These checks
do not claim a complete emulator build, real game save/load, hardware rendering,
state durability or a qualified Resume route.

The patch's upstream context and C++ acceptance fixture retain GPL-2.0-or-later;
the Python test driver is original MIT code. The [PPSSPP notices](NOTICE.md)
and exact corresponding-source obligations still apply. No engine code is
copied into the Python frontend.
