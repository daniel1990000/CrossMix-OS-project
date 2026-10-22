# Full-system coverage checkpoint

Target: original TrimUI Smart Pro TG5040, pinned spruceOS v4.5.4. All completed
checks below are host checks. No row is physically qualified. The active plan
remains [TRIMUI_PLAN.md](../../TRIMUI_PLAN.md); [HANDOVER.md](../../HANDOVER.md)
records the next implementation work.

Paths in the authority column refer to the pinned spruce tree unless marked
PPSSPP. A working callback in a fixture proves the adapter contract, not that
the installed device has supplied or qualified that callback.

| Surface or action | Existing authority retained | Current project behavior and evidence | Remaining work |
|---|---|---|---|
| Home, systems and game lists | PyUI `menus/main_menu.py`, initialized system/ROM models | Four categories, search, artwork and focus restoration; `test_ui_model.py`, `test_ui_rendering.py`, `test_spruce_backend.py` | Qualify live source caller, physical input, rendering and timings |
| Favorites and recents | PyUI history managers; existing JSON arrays | Snapshot inspection and injected initialized-manager writes; recents use normal launch | Verify actual persistence and save integrity on a spare card |
| Continue Playing / Resume | Existing GameSwitcher, `device.run_game`, PPSSPP SaveState APIs | Completed-state export/load ack, boot-bound authenticated capability store and typed Resume through the original source route; real patched API/principal/fresh-process host roundtrip and authenticated checkpoint verification time | Qualify installed engine/state/writer profiles, durable saves and full physical save/load/return lifecycle |
| Appearance and accessibility | Existing PyUI display/input; original presentation preferences | Contrast, text size, motion, original waves, dialogs and text-scaled controller keyboard; 50 keys, physical hints, title punctuation and bounded Unicode input; [host captures](../evidence/ui-polish/) | Complete native/advanced screen parity and test original-device readability |
| Classic interface and crash fallback | Existing MainMenu plus project health selector | Lazy classic route; foreground uncertainty blocks another UI; `test_health.py`, `test_embedded.py` | Install a reviewed source caller and prove original-card/internal restoration |
| Launch, quit and return | `device.run_game`, `spruce/scripts/principal.sh` | Exact-source model/menu/game/principal staging; child-subreaper descendant ownership, sealed command capture and correlated completion; composed subprocess acceptance | Qualify the exact installed source/payload, graphics/input release and physical return/recovery |
| Frontend menu controls | Existing Controller and device remapper | Physical Confirm/Back preference without gameplay edits; ambiguous inverse remaps refused | Built-in/external pads, disconnect, held keys and wake tests |
| PPSSPP native menu controls | PPSSPP ConfigSetting, KeyMap, SDL translator and native widgets | Three-key opt-in and native collision tests; complete state-session engine/FFmpeg build passes the 16-object SDK audit; read-only installed runtime probe | Collect actual device loader/driver/input/writer evidence, exact fingerprint, native widgets and saves |
| PPSSPP appearance | PPSSPP native theme loader/background and authoritative platform INI | Separate theme preview plus one common controls/appearance write window and five-file journal; verified per-game overlay inventory; protected recovery/Undo | Verify actual memstick paths, copy-back writers, overlays and PowerVR rendering; native engine layout remains an explicit visual exception |
| RetroArch standard menu | Existing RetroArch configuration and wrapper | Independent qualified menu-swap adapter with preview, recovery and Undo | Identify shipped engine/capability and physically validate its menu |
| spruce IGM | `ra_functions.sh`, native IGM/theme loader | Actual pinned C controls extension, raw input/parser/action acceptance, separate controls/palette adapters and exact active-theme precedence; complete full-engine build passing the 23-object SDK audit | Qualify rebuilt installed engine, raw joypads, JSON reload/paths, palette rendering and writers |
| Brightness, sound, Wi-Fi and hardware settings | Existing initialized PyUI settings/device handlers | Common preview/apply, stale-reading rejection, shared write window, asynchronous configuration readback and fixed advanced routes; no synthetic device readings | Prove physical brightness/audio/radios and original service ownership/return on the target |
| Sleep, power, Menu/FN hotkeys | Existing watchdogs, device functions and `save_poweroff.sh` | No competing power owner; unsafe watcher preferences block activation | Built-in controls, suspend/wake, audio, low battery and save completion tests |
| USB storage | `App/USBStorageMode/launch.sh`, staged clean-unmount/reboot route | Fourth pinned patch refuses mounted export after staging failure; actual-source mocked tests; no unqualified UI export action | Reviewed release application, storage-user shutdown, clean unmount and physical UI return |
| Apps, collections, artwork and advanced tools | Existing initialized App/Collection/Setting and per-game routes | Fixed existing-menu callbacks with embedded renderer/input lifecycle; preserved per-game options and source task handlers | Inventory owner-installed apps; advanced/third-party screens retain their native layouts and need device acceptance |
| Updates and reliability fixes | Existing spruce OTA/updater plus scoped overlay verifier | Four exact-source fixes, optional state wrapper, all-or-none private source composition, signed expanded module binding and exact-preimage restoration | Source-use review, upstream-update coexistence and physical FAT/exFAT interruption tests |
| Ports | Existing PortMaster and source PORTS/app tokens | Pinned launch-script/metadata source contracts; read-only engine/Mono/support inventory; owner-data staging/Undo and existing launch contexts | Per-title installed source/engine/data rights, graphics/input/saves and measured acceptance; San Andreas remains disabled/experimental |
| Migration and support | Existing save/config authorities | Offline copy-based migration and redacted local diagnostics; host fixtures | Verify each actual save format, restore and mounted-card procedure |

The device acceptance recorder retains before/after named save hashes and
append-only operator attempts without minting qualification. The owner has the
original device but cannot test today. Source-use notification, distribution
rights, installed inventory and physical qualification remain open. The
notification draft is unsent. Package rollback,
whole-card restore, internal startup/scene restoration and vendor firmware
recovery remain distinct procedures.
