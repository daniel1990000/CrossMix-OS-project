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
| Continue Playing / Resume | Existing GameSwitcher; PPSSPP SaveState APIs | Real entries have Resume only with exact validated state evidence; demo cards are fictional fixtures | Build in-emulator completion/identity evidence and prove the full state lifecycle |
| Appearance and accessibility | Existing PyUI display/input; original presentation preferences | Contrast, text size, motion, original waves, dialogs and keyboard; host SDL screenshots | Complete native/advanced screen parity and test original-device readability |
| Classic interface and crash fallback | Existing MainMenu plus project health selector | Lazy classic route; foreground uncertainty blocks another UI; `test_health.py`, `test_embedded.py` | Install a reviewed source caller and prove original-card/internal restoration |
| Launch, quit and return | `device.run_game`, `spruce/scripts/principal.sh` | Token-bound handoff, independent live evidence, partial-release recovery and typed return collection; `test_bootstrap.py`, `test_runtime.py` | Track real startup/background threads and qualify the actual principal return authority |
| Frontend menu controls | Existing Controller and device remapper | Physical Confirm/Back preference without gameplay edits; ambiguous inverse remaps refused | Built-in/external pads, disconnect, held keys and wake tests |
| PPSSPP native menu controls | PPSSPP ConfigSetting, KeyMap, SDL translator and native widgets | Three-key opt-in transaction; actual C++ remap/INI tests; complete PPSSPP/FFmpeg source cross-build passes recursive SDK inventory | Actual installed loader/driver/input/writer inventory, exact fingerprint, native widgets, saves and device qualification |
| PPSSPP appearance | PPSSPP native theme loader and background renderer; authoritative platform INI | Settings → PPSSPP appearance previews/apply/Undo using the theme manager; `test_appearance_flow.py`, `test_ppsspp_theme.py` | Verify installed memstick paths, theme support, complete writer inventory and PowerVR rendering |
| RetroArch standard menu | Existing RetroArch configuration and wrapper | Independent qualified menu-swap adapter with preview, recovery and Undo | Identify shipped engine/capability and physically validate its menu |
| spruce IGM | `ra_functions.sh`, theme `igm.json` | Separate unsupported capability, never inferred from RetroArch's standard menu swap | Implement and qualify its own controls and appearance adapter |
| Brightness, sound, Wi-Fi and hardware settings | Existing PyUI settings/device handlers | Advanced Settings route delegates existing initialized menu callback | Common settings coverage, transactional backend evidence and hardware tests |
| Sleep, power, Menu/FN hotkeys | Existing watchdogs, device functions and `save_poweroff.sh` | No competing power owner; unsafe watcher preferences block activation | Built-in controls, suspend/wake, audio, low battery and save completion tests |
| USB storage | `App/USBStorageMode/launch.sh`, staged clean-unmount/reboot route | Fourth pinned patch refuses mounted export after staging failure; actual-source mocked tests; no unqualified UI export action | Reviewed release application, storage-user shutdown, clean unmount and physical UI return |
| Apps, collections, artwork and advanced tools | Existing initialized PyUI App/Collection/Setting routes | Explicit existing-menu routes and tool callbacks; host foreground-token checks | Inventory every installed app/action and track remaining visual exceptions |
| Updates and reliability fixes | Existing spruce OTA/updater plus separate project overlay tool | Four exact-source regression patches; signed scoped development overlays and rollback | Reviewed base-patch application path, upstream-update coexistence, FAT/exFAT interruption tests |
| Ports | Existing PortMaster/wrapper conventions | Owner-data preview, staging, backups and Undo; `test_upstream_ports.py` | Exact engine/runtime/data licences and per-title original-device acceptance; San Andreas remains experimental |
| Migration and support | Existing save/config authorities | Offline copy-based migration and redacted local diagnostics; host fixtures | Verify each actual save format, restore and mounted-card procedure |

Source-use notification, distribution rights, installed inventory and physical
qualification remain open. The notification draft is unsent. Package rollback,
whole-card restore, internal startup/scene restoration and vendor firmware
recovery remain distinct procedures.
