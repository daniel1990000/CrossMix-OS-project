# Full host PPSSPP build and native state protocol

The pinned full SDL engine built and executed the private GTA: Vice City Stories ISO on x86_64 Linux. Actual native save/load callbacks produced correlated private session records. This evidence covers desktop native behavior. It grants no TrimUI qualification, production source-use admission, foreground authority, writer capability, promoted SaveRef or authenticated frontend Resume.

`build-report.json` records executable SHA-256 `6924b0392831517fb54108b98b9faa743492fe7d2709690098f91226fcdf56de`, upstream commit `d357e6a32934800d3d80b49f910a603e1b069751`, and exact patches 0001, 0002, 0003 and optional diagnostic correction 0005. Patch 0005 fixes the independently reproduced upstream GPU-statistics float-copy overflow; it is explicitly additional to the three locked state/menu patches. No PowerVR recipe patch or device profile was selected. `assembly.json` includes modified source hashes. The pristine upstream checkout stayed clean.

The host used pinned FFmpeg prebuilt x86_64 static archives. Their hashes and submodule identity are retained; this run does not establish their complete source correspondence. `configure-host.sh` records the actual configuration. Build command was `cmake --build /workspace/trimui-audit/native/patched-build --target PPSSPPSDL -j3`, with the private build-venv tools on PATH. CMake 4.4.4, Ninja 1.13.2 and Debian GCC 14.2.0 were used. The extracted dependency package inventory and actual dynamic dependency resolution are included. The separately downloaded official stock AppImage is identified in `stock-binary.json`.

`protocol-report.json` checks 14 retained experiments: 13 met their expected native observations, and one earlier harness setup failure is preserved because default native keyboard mappings did not bind F2. It is not a product failure. Explicit private mappings were then added to the native-generated controls and per-game configuration: F2 save, F4 load, F3 next slot. Other native-generated mappings were preserved.

| Native case | Observed outcome |
| --- | --- |
| Save then unwritable state directory | Actual completed SaveSlot sequence 1 retained; sequence 2 reports failure with empty positive evidence fields. |
| Fresh-process load then save | Actual load sequence 1 and new SaveSlot sequence 2 succeed. |
| Controllable Soldier/bike state | Actual load of parent-observed gameplay state, new native save, and fresh-process reloads succeed. |
| Wrong engine digest, malformed trailing packet, insecure request permissions | Startup exits 2 without native result/completion records. |
| Wrong game digest, state modified or truncated after request preparation | Native failure reports input identity mismatch; no positive completion. |
| Corrupt state with its exact digest in request | Genuine native loader failure; no positive completion. |
| Final-result publication obstructed by a directory | Native load succeeds and independent load completion exists, but no regular final result is published. A temporary record remains. This is a publication-failure injection, not a physical power-cut test or proof of production promotion. |

The gameplay input hash was `2d7b3d34a4b31c02e855444b1359c85630bf8bb6c34fb012fa4a4c33bb91e7b8`; the newly saved and subsequently reloaded state was `1292772964f0333fba549e8d2f3b23231d977bf04c03ccab4db00a658fe2ca99`. New save bytes replace the previous slot, so the previous load record still names the old bytes. The report retains both identities without pretending both describe the current file.

The `playable-resume3` run also passed through the existing `run_owned_tree` kernel boundary: native exit 0, one child reaped, subreaper restored, no external descendant cleanup. The frontend lane owns that separate receipt. An earlier owned run was held open by SDL-autolaunched host dbus descendants and required explicit service cleanup; the clean retry set `DBUS_SESSION_BUS_ADDRESS=unix:path=/nonexistent`. These facts do not establish composed frontend Resume.

The included Python and shell files are exact retained experiment scripts, not product runtime code. They reference this session's private workspace paths. Running them requires the private input, built engine, extracted host libraries, Xvfb `:100`, native configuration and fresh session paths. They hash and decode native records without constructing a `QualifiedStateProfile` or granting device authority. Preserve an input copy before tests that overwrite a slot. `prepare_negative_cases.py` and the aggregate script depend on the named earlier experiment folders. Scripts are supplied for review and deliberate reconstruction, not blind execution in another checkout.

No ISO, game data, states, screenshots, audio, native executable, full source tree or downloaded base distribution is included. The report contains only hashes, native record fields, command metadata and references to retained private artifacts. Raw logs and game imagery stay private. Device input/suspend/storage/renderer behavior and authenticated frontend authority remain separate acceptance work.

## Additional native boundary probes

`additional-protocol-report.json` retains the later wrong-slot, matching-hash truncation and replay observations. Native loading accepts the caller's slot 1 metadata for a state filename ending in slot 0. Reusing an unchanged raw request in another native process produces another successful sequence-1 load and a byte-identical result packet. These are observations of the native trusted-caller boundary, not successful slot/replay rejection tests. The independent `slot-replay-boundary-review.json` separates actual envelope-helper rejection under changed session/minimum-sequence context from the full qualified consumer, which was not exercised. A 256-byte truncated real state with its exact digest supplied in the request reaches the native loader and fails without a positive completion.

The three initial follow-up launches overlapped one controlled performance pair. Their approximate reconstructed intervals are recorded; the parent performance lane owns exclusion/repetition of impacted measurements. The second replay happened only after the soak started. No timing result here is presented as an isolated performance measurement. G04 remains partial against complete authenticated roadmap acceptance.

## Bounded ordinary gameplay

`ordinary-gameplay-report.json` records one normal native process from 19:09:33.685580 to 19:34:21.371726 UTC, exit 0: 24 minutes 47.686 seconds, 203 logged input/screenshot actions and 71 private screenshots. It exercised bike mounting/driving/collisions and recovery, on-foot movement, a Barracks interior, map controls, the Fort Baxter exit gate, the airport coastal road/underpass, traffic, pedestrians and swimming/recovery. The initial state came from the parent-observed playable scene; an explicit F4 reset and a later F2 convenience checkpoint remain separately identified native state operations.

The bounded keyboard attempt did not complete Soldier or create ordinary game savedata. The savedata directory was empty before and after. Fresh launch → Continue was therefore not validated. This is partial operator-limited gameplay coverage, not a save acceptance pass or an established emulator defect. The run overlapped the stationary host soak; it does not measure isolated FPS. Only command metadata, hashes and the two experiment scripts are published. Game images, game/state contents and logs stay private.
