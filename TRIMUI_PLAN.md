# TrimUI Smart Pro project plan

Saved to the project on 22 October 2026. Documentation only: this file does not mean the design is implemented, hardware-tested or approved for release.

## How to use this plan

The full technical blueprint below is converted from **PSP_inspired_CrossMix_technical_blueprint.docx**, dated 14 October 2026. Its 26 tables and 46 source references are retained. Baseline hashes, licence observations and version claims belong to that research date; recheck moving references before implementation. The later additions in this section are planning updates, not silent changes to the original architecture.

### Exact reuse and build decision

- **Keep CrossMix as the compatibility foundation:** existing emulators, launcher scripts, firmware services, ROMs, saves and installed tools. Integrate through versioned, tested adapters. Baseline: [CrossMix commit 206d612fdef83972ed54a17de955125d0c0b3528](https://github.com/cizia64/CrossMix-OS/tree/206d612fdef83972ed54a17de955125d0c0b3528).
- **Build the system interface:** a purpose-built C++17 shell and session supervisor, using the device-compatible SDL2, GLES2, CMake/Ninja, FreeType/HarfBuzz, stb_image, nlohmann JSON, SQLite and libsodium. Use the [official original Smart Pro SDK](https://github.com/trimui/toolchain_sdk_smartpro/releases/tag/20231018), with the ABI, vendor SDL backend and dependency checks specified below. Do not upgrade global runtime libraries to make the shell build.
- **KNULLI EmulationStation is the evaluated reuse candidate, not the final default base:** [pinned source f7c5ae103815761ccd34bc55b021c6e150442c96](https://github.com/knulli-cfw/batocera-emulationstation/tree/f7c5ae103815761ccd34bc55b021c6e150442c96). Revisit only if the small native prototype reveals a blocker it demonstrably solves; compare memory, startup, latency, dependencies and complete settings coverage. It is not a drop-in CrossMix theme.
- **RetroArch XMB stays within RetroArch:** theme/configure its existing menu rather than extracting GPL engine-integrated code into the new shell. [XMB documentation](https://docs.libretro.com/guides/xmb/).
- **PPSSPP keeps its own UI:** use supported theming and narrow, maintained patches where required, not wholesale UI copying. An optional emulator-update track can investigate [spruce's original Smart Pro PowerVR build recipe](https://github.com/spruceUI/PPSSPP-spruce/blob/main/build-pvr.sh). Pin and audit the exact recipe, source and patches before use; no speed improvement is assumed.
- **Do not copy Sony firmware/assets, or assume Spruce/PyUI/NextUI/MinUI code is freely reusable.** The full licence/provenance audit below remains a release gate. Public availability alone is not permission to redistribute.

### Consolidated feature scope

1. **Switchable whole-system experience:** PSP-inspired navigation, original animated background, consistent dialogs and settings, with a return to CrossMix and shared game/save collections. Preserve the distinction between functional access and visual parity. The exact nested selector in closed-source stock MainUI is unproven; a stock App/System Tools bridge and third-party UI exceptions require explicit scope decisions.
2. **Universal controls:** one configuration experience backed by separate, versioned adapters for the shell, RetroArch, PPSSPP and supported standalone emulators. Global defaults and per-game overrides, with preview/undo and honest unsupported cases. Do not overwrite gameplay mappings merely to change menu Confirm/Back.
3. **Continue Playing:** screenshot/resume cards with Resume or Fresh Start, initially where the emulator lifecycle and state compatibility are proved. Keep in-game saves, memory cards and emulator states distinct. Later candidates include named checkpoints, Play Next, isolated guest saves and try-once presets.
4. **Optional emulator improvements:** newer PPSSPP first as a separate, reversible experiment with independent settings and backups. Compare identical games/settings for speed, audio, controls and sleep/resume. Standalone PS1 work follows only after its own compatibility checks. The initial shell prototype keeps installed emulator binaries frozen.
5. **Reliability fixes:** correct update-extraction failure reporting; validate renamed/missing emulator choices and fallbacks; back up and undo configuration resets; verify update downloads and source identity; provide a local redacted launch-failure report. Reproduce each reported defect against the selected baseline before changing it.
6. **Tuned for Smart Pro port showcase:** candidate work on GTA III, Vice City, Sonic Mania, Super Mario 64/Render96ex and Celeste, with clear owner-file import, tested controls and measured profiles. Consult the [PortMaster catalogue](https://raw.githubusercontent.com/PortsMaster/PortMaster-Info/main/ports.json), [TrimUI-specific ports](https://github.com/cobaltgit/TrimUI-Ports) and [Celeste launcher](https://github.com/PortsMaster/PortMaster-New/blob/main/ports/celeste/Celeste.sh). Recheck support and licences before packaging. San Andreas is an experiment, not a promised supported feature. Do not bundle commercial game data.

### Later checkpoint: evaluate spruce before committing to the custom distribution

The 18 October discussion raised trying spruce first. Compare it on a spare card against the existing CrossMix installation before investing in the complete custom system. If it meets the practical needs, using it can avoid unnecessary development. If important gaps remain, document those gaps and continue only the justified custom features. This checkpoint does **not** silently replace the original C++/SDL2 architecture, waive licence review, or establish measured performance gains.

### Delivery sequence and limits

1. Preserve an untouched working card, verify a spare-card clone and restoration, inventory the exact firmware/runtime, and decide the spruce comparison outcome.
2. Reproduce reliability defects and prepare small reversible fixes independently. Keep the original blueprint's device evidence and recovery work package as the prerequisite for boot changes.
3. Build the minimum native vertical slice: input/frame, one existing-emulator launch and return, safe interface switchback, and early USB/power risk checks. Freeze emulator binaries during this proof.
4. Add the settings/controls adapters, data transactions and tested system-function coverage; then build out the PSP-inspired presentation and Continue Playing.
5. Evaluate optional PPSSPP/PS1 upgrades separately from shell regressions; add the polished ports only after file-import, controls, licensing and performance checks.
6. Complete the automated, physical, recovery, save-integrity, packaging and licence gates in the original blueprint before any stable-release claim.

No code, firmware, runtime settings, ROMs or saves are changed by saving this plan. The detailed work packages below govern implementation; their estimates and acceptance counts are planning targets, not completed tests or delivery promises.

---

# Original technical blueprint (14 October 2026)

Original TrimUI Smart Pro \| Architecture and delivery plan \| 14 October 2026

Build a small native system shell above the existing CrossMix and TrimUI runtime. Give a separate session supervisor responsibility for boot selection, game and app handoff, recovery and hardware coordination. Keep the current emulators, firmware services, ROMs and saves as the compatibility foundation.

This is a proposed engineering design for your own maintained distribution. It specifies what to build, what to reuse, where the interfaces belong, how to test them and what evidence must exist before release. The product name remains open.

## Recommended decision

- Use C++17, the device-compatible SDL2 build and OpenGL ES 2.0. Build a purpose-made navigation and settings UI with original artwork, typography, animation and sounds. Keep the dependency set small.

- Preserve CrossMix through versioned adapters. Treat its launcher scripts, configuration files and firmware daemons as integration contracts that require tests, rather than as interchangeable command-line tools.

- Ship first as a reversible SD-card overlay. Do not replace the kernel, flash firmware or update emulator binaries during initial shell development.

- Prove launch and return, sleep and wake, USB transfer and recovery on a spare SD card and an original Smart Pro before investing in the complete visual layer.

## The hard limits to resolve

The new shell can provide Settings → Appearance → CrossMix / PSP-inspired interface. No verified extension point lets us add that exact nested selector to closed-source stock MainUI. A stock App or System Tools switch entry is the safe initial bridge. Also, a shared shell cannot restyle the internal screens of PPSSPP, PortMaster, file managers and other independent applications by itself. These require supported theming, specific source changes or explicit visual exceptions.

## Expected scale

Plan for roughly 21–35 person-weeks for a tested first release with full functional coverage and documented third-party visual exceptions, plus a 25–40% uncertainty allowance until the device investigation is complete. This is an engineering estimate, not a delivery promise. Exact PSP-like presentation inside every third-party application would be a separate, open-ended expansion.

Research and planning only. No implementation, firmware installation, emulator replacement, repository push or publication forms part of this deliverable. The earlier optional PSP/PS1 update work remains separate. Performance and reliability numbers in this document are acceptance targets, not measured results.

# Reading map and release contract

| **Sections**                     | **What they establish**                                    |
|----------------------------------|------------------------------------------------------------|
| Evidence and stack 3–6           | The verified baseline, dependencies and reuse decisions    |
| Runtime and interfaces 7–14      | Boot, launch, IPC, settings, library data and controls     |
| Device behavior 15–19            | Graphics, power, networking, USB and save safety           |
| Parity registers 20–21 and 32–38 | Existing functions and the proof each needs                |
| Build and delivery 22–30         | Source layout, testing, packaging, licences and milestones |
| Decisions 31 Sources 39–43       | The choices still needed and primary references            |

## First release must satisfy these outcomes

- The chosen interface starts at normal boot. Switching changes the next session and next boot without creating a separate ROM or save collection.

- Games, Continue Playing, Tools and Settings provide the everyday experience. Favorites live inside Games. Existing media players, Syncthing and other installed tools remain reachable under Tools.

- System menus, confirmations, text entry, progress, errors and common settings share one input convention and visual language. Gameplay mappings remain separate.

- The shell has no Photos category or empty placeholders. V1 adds no new store, social, camera, browser, media, cloud or account integration. Existing CrossMix integrations retain access.

- A failed shell start returns to a known-good interface. An offline recovery route works even when the new graphics code cannot start.

## Two different acceptance measures

Functional parity means each existing operation has a tested path, including advanced legacy tools. Visual parity means each screen follows the new design. Track both for every inventory row. A legacy fallback may satisfy access but does not satisfy visual parity. Never mark a row complete merely because an executable is present.

## Scope choices that need your decision

Approve or reject the stock App/System Tools switch bridge, and approve or reject named advanced-app visual exceptions for v1. If the exact stock Settings location and identical screens everywhere are non-negotiable, treat them as unresolved feasibility requirements. Do not quietly redefine either requirement to fit an easier implementation.

The dependency names, schemas, process names and proposed directory layout below are design decisions. Existing file paths and observed behaviors are identified with source references. New proposed names are not claims about APIs CrossMix already exposes.

# Verified baseline and first device evidence

The user fork and upstream main match commit 206d612fdef83972ed54a17de955125d0c0b3528, dated 20 August 2026. Pin it for the first compatibility profile. The tree includes original-Smart-Pro firmware 1.1.1/20251128; your installed firmware is still unknown. \[S01–S03\]

| **Evidence level**  | **Known or required**                                                                                                                                           |
|---------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Target              | Original TrimUI Smart Pro, TG5040/A133 family, ARM64 and PowerVR. Exclude Brick and Smart Pro S builds even when filenames look similar.                        |
| Official SDK        | Tag 20231018, commit 3eb83e4959279520c595a2e5eef45f770e8e92b0: GCC 7.5 Linaro archive, A133 sysroot and SDL2 2.26.1 GE8300 archive. \[S04\]                     |
| Firmware variation  | Vendor release notes record glibc 2.33 and PowerVR driver changes in 1.0.4, and SDL2 2.30.8 in 1.1.0. The installed ABI/backend still needs inspection. \[S05\] |
| MainUI              | Stock binary remains a legacy dependency. No verified source or nested settings-menu extension hook is available in the inspected CrossMix tree.                |
| Unverified hardware | Exact firmware, boot hook, kernel interfaces, SDL backend, OSD ownership, suspend behavior, Bluetooth capability and performance on this physical unit.         |

The 1.3.0 version string does not identify this commit. MinFwVersion.txt requests 1.1.0/20250505 but the bundled archive is 1.1.1/20251128; \_FirmwareCheck.sh derives its filename from the minimum. This verified packaging mismatch could block an upgrade; no device failure was tested. Pin commit and firmware independently. \[S34–S36\]

## Capture before the first executable prototype

Inventory firmware, kernel, mounts, boot/runtrimui scripts, processes, input capabilities, SDL backend, EGL/GLES strings, ALSA routes and power/thermal endpoints. Record ELF interpreters, libraries and versioned symbols for MainUI, SDL2 and emulators. Collect redacted logs and hashes, without credentials or ROM contents.

Clone the existing SD card, verify the clone, and test the original restoration route before changing boot behavior. Keep an untouched known-good card. Record current launch, volume, brightness, suspend, USB and shutdown behavior as comparison evidence. Confirm panel resolution from the running device before freezing rendering fixtures.

## What can proceed without the device

Architecture, desktop navigation, parsers, fake adapters, transactional settings, package validation, licence inventory and automated tests can proceed. Boot ownership, graphics handoff, input numbers, audio routing, sleep/wake and storage handoff remain hardware gates. An ARM64 binary that links successfully is not proof that it works on this firmware.

# Verified platform build traps

The official toolchain archive contains GCC 7.5.0, datestamp 20191114, Linaro 7.5-2019.12, and a compiler libc sysroot whose headers and shared library identify glibc 2.25. The separate A133 SDK usr archive is a staging overlay. Newer device firmware reports a different runtime libc. Keep compiler/sysroot identity and installed runtime identity separate. \[S04, S05\]

## The vendor SDL backend matters

The supplied SDL2 2.26.1 GE8300 source registers its framebuffer video backend as “mali” even though the hardware GPU is PowerVR. Its mali-fbdev code opens /dev/fb0, includes a PowerVR-specific native-window path and selects 1280×720 under SDL2_POWERVR_GE8300. A generic distribution SDL2 build or SDL3 compatibility layer is not a proven replacement. \[S04\]

The manufacturer specifies a 4.96-inch 720×1280 IPS panel, A133plus quad Cortex-A53 and PowerVR GE8300. Use 1280×720 as the landscape design canvas, then verify actual orientation and surface size. Manufacturer clock figures describe specifications; they do not authorize overclocking or establish available runtime governors. \[S37\]

## Hermetic build precautions

- The SDK sdl2-config embeds the original developer’s absolute staging paths and an RPATH. Replace/sanitize this build metadata instead of invoking it blindly. Reject host paths in compiler and linker output.

- The vendor GLES2 test links SDL2, EGL, GLESv2 and PowerVR support libraries. Resolve the actual installed dependency closure; do not copy those link flags without checking the target libraries.

- Keep a constrained C++17 subset and POSIX file APIs, or fall back to C++14 if a needed dependency cannot build cleanly under the exact SDK. Do not upgrade the device libc to satisfy a new library. \[S38\]

- Disable unused HarfBuzz integrations and tools; resolve its optional FreeType build cycle deliberately. Keep unused ICU, GLib, Cairo and Graphite out of the target dependency closure.

- Start with power-of-two atlases and conventional GLES2 shaders/blending. Test texture formats, NPOT behavior, context teardown and resume on the actual PowerVR stack before optimizing.

## Pin the inspected vendor source

The inspected SDL2-2.26.1.GE8300.tgz has SHA256 a37fbed6c8771f1050e6520fa9c48354e01519de813fe176ae53089f2087bb87. Record hashes for the other SDK archives and selected runtime libraries in the implementation lockfile. This identifies the research baseline, not a tested final runtime package.

# Choose a compact native stack

| **Layer**        | **Recommended choice and constraint**                                                                                                                                                                                                 |
|------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Languages        | C++17 for shell, session supervisor and adapters. Avoid std::filesystem with the older SDK; use a small POSIX path layer. Python 3 for host tooling/tests; POSIX sh only for audited boot shims and legacy-script adapters.           |
| Build            | CMake plus Ninja. Cross-compile against the pinned original-Smart-Pro SDK/sysroot; GCC 7 treats C++17 as experimental; compile-test the constrained subset. Compile dependency versions against that toolchain before admitting them. |
| Window and input | The device-compatible SDL2 build, dynamically linked in a private runtime path. Do not replace global SDL2 or set a global LD_LIBRARY_PATH.                                                                                           |
| Rendering        | A small GLES2 2D renderer: batched textured quads, glyph atlas, clipping and one inexpensive wave pass. SDL_Renderer fallback provides static/reduced-motion recovery if the verified device backend supports it.                     |
| Text and images  | FreeType plus HarfBuzz for readable Unicode and shaping; original or OFL-licensed fonts. Pinned stb_image for PNG/JPEG artwork, with dimension/decoded-memory limits and unused formats disabled.                                     |
| Structured data  | nlohmann JSON for bounded config/IPC parsing. SQLite for rebuildable library indexes. A small format-preserving INI/CFG editor for emulator files; streaming line-JSON reader for legacy favorites/recents.                           |
| Audio            | SDL2 audio and small preloaded PCM WAV effects. No music decoder or SDL_mixer dependency for shell sounds.                                                                                                                            |
| Package trust    | libsodium for detached Ed25519 manifest verification. Offline signed packages; no shell network client or background update service required in v1.                                                                                   |

Pin exact compatible revisions after the SDK build spike. Upstream latest versions are not automatically compatible with GCC 7.5, the device libc or the vendor GPU. Store every selected archive hash and licence in the build manifest. \[S04–S05, S15–S22\]

## UI implementation strategy

Use a small retained scene tree with explicit screen/view models, focus rules and animation state. Keep rendering free of file reads, process management and device writes. A worker queue handles scans, image decode and adapter jobs; the UI consumes immutable results. Do not adopt a browser engine, Electron, Qt/QML, a JavaScript runtime or a general plug-in system for v1. Their benefits do not justify their runtime and integration cost for this fixed-purpose interface.

# Compare alternatives and reuse boundaries

| **Candidate**           | **Useful strengths**                                                                                                            | **Cost and decision**                                                                                                                                                                                                    |
|-------------------------|---------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Custom SDL2 shell       | Exact navigation, low dependency count, direct ownership of settings and recovery flows.                                        | More original UI work. Recommended because the goal covers the whole system and a specific interaction model.                                                                                                            |
| KNULLI EmulationStation | Mature game browser and controller-oriented frontend; MIT source; original Smart Pro support exists in the KNULLI distribution. | README warns of Batocera environment dependencies. CMake includes SDL2_mixer, FreeImage, FreeType, curl, VLC and RapidJSON. A port still needs CrossMix system adapters. Keep as fallback, not the default base. \[S06\] |
| RetroArch XMB           | Already a horizontal menu for RetroArch, including the PS1 libretro path.                                                       | GPL-3.0-or-later engine-integrated code; not a system shell. Theme/configure the existing menu; do not extract it into the new shell. \[S07–S09\]                                                                        |
| PPSSPP UI               | Working emulator settings, on-screen keyboard and controller behavior.                                                          | GPL-2.0-or-later, tightly coupled to PPSSPP. Use theme support and narrowly maintained patches where necessary, not wholesale UI reuse. \[S10–S12\]                                                                      |
| NextUI / MinUI          | Useful product references for a restrained handheld UI.                                                                         | Current NextUI moved to PolyForm Noncommercial on 15 August 2026; its notice highlights MinUI licence ambiguity. Do not copy without a file-level permission audit. \[S13\]                                              |
| Spruce / PyUI           | Relevant device integration examples and existing emulator packaging.                                                           | Noncommercial obligations require a separate review. Avoid making them a source dependency of the new shell. Keep binaries out until provenance is complete. \[S14\]                                                     |

## Do not spend weeks porting both frontends

Start with one vertical SDL2 prototype: boot into a plain screen, read controls, launch one current PPSSPP game through the compatibility adapter, return, then switch to CrossMix. Only revisit EmulationStation if that spike uncovers a blocker that its maintained port demonstrably avoids. Compare measured startup, memory, input latency, required patches and system-settings coverage before changing direction.

A PSP ELF reader or reverse-engineering library does not solve this problem. No Sony firmware decompilation, copied XMB artwork, Sony fonts, icons, sounds or boot assets are required.

# Runtime architecture and module ownership

Firmware boot and hardware services  
\| verified SD entry hook  
v  
sessiond \<--\> ui-shell  
\| \|  
\| library / settings / navigation models  
\|  
+--\> CrossMix MainUI session  
+--\> approved game launcher --\> emulator  
+--\> approved tool or service adapter  
+--\> power / USB / recovery handoff

| **Module**             | **Owns**                                                                                            | **Must not own**                                                               |
|------------------------|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| sessiond               | Session state, foreground process tree, adapter jobs, boot health and recovery.                     | A graphics context, game controls, arbitrary command execution.                |
| ui-shell               | Navigation, focus, rendering, UI input, prompts and common settings screens.                        | Hardware writes, direct emulator config writes or background daemon ownership. |
| device adapter         | Versioned mapping from typed operations to verified firmware commands/endpoints.                    | New Wi-Fi, Bluetooth, audio or power daemons competing with firmware.          |
| CrossMix adapter       | Manifest import, preset resolution, launch context, legacy settings/tools and data synchronization. | Pretending every legacy script is standalone.                                  |
| emulator adapters      | Capabilities, config previews/transactions, state metadata and supported launch/exit behavior.      | Global remapping of gameplay or unverified live save operations.               |
| library module         | Rebuildable indexes, asset lookup, search, favorites bridge and recent-session views.               | Moving ROMs/saves or rewriting unknown source fields.                          |
| package/recovery tools | Validated staging, activation records, rollback and support bundle export.                          | Automatic firmware flashing or overwriting user data.                          |

Keep these as modules in one repository, not a fleet of services. Run only a small supervisor and one foreground UI/game at a time. A short-lived helper may perform operations that must survive UI exit. Where firmware runs everything as root, acknowledge that process separation improves reliability but does not create a strong security boundary.

# Boot selection and reliable switchback

## Integrate at the real session entry point

Inspect the installed firmware boot chain and its runtrimui/MainUI restart behavior before choosing a hook. The relevant vendor startup scripts are not all present in the CrossMix source tree. A preload script that configures services is not automatically a safe place to replace the main session. The first milestone must establish the exact entry, restart and exit contracts. \[S03, S05\]

Keep the original entry point intact and add the smallest reversible selector after required firmware initialization. It reads a validated session preference, starts either original MainUI or sessiond plus ui-shell, and falls back to the original path on error. Avoid changing firmware partitions for the first release.

## Use a transactional selector

Existing state: stable = crossmix  
User chooses new interface -\> pending = psp_shell  
Boot selector validates package + compatible profile  
Start supervisor and shell  
Shell reports ready only after input + first frame + settings read  
Commit stable = psp_shell; clear pending  
Timeout / crash / invalid config -\> stable = crossmix

The first-launch health timeout is an acceptance parameter established on hardware. A running emulator is a valid session, not a missing-shell crash. If sessiond dies, the boot/recovery layer must identify surviving children using PID plus start identity, reattach without graphics where safe, or wait for manual recovery. Supervisor state and child identity must prevent a watchdog from launching MainUI over a game. After repeated shell failures, prefer one safe fallback and a visible explanation rather than an endless restart loop.

## Switching while the device is on

Permit an interface switch only from idle home/settings after jobs finish. Flush application-owned data, stop the current UI, release input/audio/video, then hand over through the supervisor. Initial releases may use a controlled reboot if a live handoff cannot be proven safe; label that behavior honestly. Never leave two UIs reading controls or owning the display.

## Recovery must be independent of the new UI

Support an offline SD-card force-CrossMix marker and restoration of the original startup file from a verified backup. Add a physical boot gesture only after input availability and conflicts are known. Store selector records with generation numbers and checksums, keep the last known-good record, and do not rely on symlinks on a FAT/exFAT card. SD removal behavior and any on-device internal recovery route need separate firmware verification.

# Launch and return as a state machine

CrossMix has a useful launch foundation, but several paths depend on MainUI behavior. common_launcher.sh reads held A/Y, starts Activities and prepares save/override behavior. Save/load and PSP performance selection use labels taken from MainUI logs. System Tools prepares a MainUI SQLite browser rather than displaying its own complete interface. These dependencies need explicit adapter inputs. \[S03, S23–S26\]

IDLE -\> VALIDATING -\> PREPARING -\> RELEASING_UI  
-\> RUNNING -\> COLLECTING_RESULT -\> RESTORING_UI -\> IDLE  
Errors before RUNNING -\> restore UI with actionable error  
Errors during RUNNING -\> preserve saves/logs, classify exit  
USB / shutdown -\> separate exclusive handoff state

## Launch transaction

- Resolve a stable game ID, canonical ROM path, emulator preset and explicit mode. Validate mount state, allowed extensions, dependencies, BIOS requirements and available space. Reject a stale library entry without changing it.

- Read the current CrossMix default/per-game selection using the pinned adapter. Preserve the installed emulator unless the user chooses another. Translate held-button actions into an explicit menu; do not inherit the confirmation button still being held.

- Build a LaunchContext containing game path, display label, preset ID, activity policy, save/resume mode, expected working directory and a constrained environment. Resolve each legacy dependency from that context.

- Prefer a small reviewed patch to owned CrossMix wrappers that accepts explicit context and retains the old MainUI fallback. Do not fabricate MainUI log lines or screen events as a permanent API.

- Write the required cmd_to_run and resume contracts only after their firmware consumers are mapped. Transfer ownership of graphics/input/audio, spawn one approved process group and track child exit. Handle wrappers that fork or exec explicitly.

- On return, reconcile activities and emulator-written settings, restore hardware state through the verified adapter, reacquire SDL resources, debounce held inputs and restore focus to the launched item.

## Do not double count or double supervise

Keep Activities as its existing authoritative recorder if the launcher already invokes it. The new recent-session journal adds lifecycle facts rather than a second playtime total. Adapt firmware shutdown scripts that currently discover a process tree through cmd_to_run.sh; a new process name alone could otherwise leave games running or break resume. Never use a broad killall as the default game-exit mechanism.

# Typed interfaces and protocol examples

Use a private Unix socketpair between supervisor and UI, with a length-prefixed UTF-8 JSON protocol. Cap control messages at 64 KiB, cap parser nesting and query result counts, and use an explicit schema version, unique request IDs, request deadlines and stable error codes. Do not expose a TCP/HTTP listener. A separate local status socket, if needed for the stock bridge, belongs on a verified RAM-backed filesystem with restrictive permissions.

{  
"v": 1, "id": "req-104", "method": "game.launch",  
"params": {"game_id": "psp:sha256-of-relative-path",  
"preset_id": "existing-default",  
"mode": "normal", "expected_generation": 82}  
}  
{  
"v": 1, "id": "req-104", "ok": true,  
"result": {"job_id": "job-27", "state": "validating"}  
}  
{  
"v": 1, "event": "job.changed", "seq": 204,  
"job_id": "job-27", "state": "running"  
}

| **Operation family** | **Examples and safety rule**                                                                                                                |
|----------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| Read                 | system.capabilities, system.snapshot, library.query, job.get. Return unsupported rather than invented values.                               |
| Settings             | settings.preview / settings.apply / settings.undo. Apply requires an observed generation and validated diff.                                |
| Session              | game.launch, tool.launch, interface.switch. IDs resolve to a signed/installed registry; callers cannot pass a command string.               |
| Device               | audio.set_volume, display.set_brightness, network.scan, network.connect, power.request. Bounds and state preconditions live in the adapter. |
| Storage              | usb.prepare, usb.begin, package.stage, package.activate. Exclusive operations block launch, indexing and writes.                            |
| Recovery             | support.export, config.restore, session.safe_mode. Redact secrets and require confirmation for destructive restores.                        |

Errors should include a stable code such as UNSUPPORTED_PROFILE, STALE_GENERATION, BUSY_GAME, STORAGE_READ_ONLY or CHILD_EXIT_FAILED, plus a user-readable message and safe retryability. Cancellation is permitted only before a defined point of no return. Persist idempotency records for settings/update commits so a repeated request cannot apply a transaction twice. Unknown methods and unknown required fields fail closed.

# Settings authority and reversible migration

| **Data domain**            | **Authority and write policy**                                                                                                                                            |
|----------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Firmware hardware settings | Existing /mnt/UDISK/system.json and verified systemval operations. Read through the device adapter; do not maintain a competing brightness/volume authority. \[S03, S27\] |
| CrossMix settings          | Existing System/etc/crossmix.json and ex_config values remain authoritative where relevant. Track per-key mappings and reread after legacy tools.                         |
| New shell preferences      | Versioned shell-owned JSON for interface choice, motion, shell sound, text scale, layout and UI input preference.                                                         |
| Emulator settings          | Each emulator remains authoritative for its config and per-game overrides. Adapters edit a declared subset while stopped; show external changes.                          |
| Favorites and activity     | Preserve existing favorites/activity formats through a read-modify-write bridge. New session facts are separate; avoid duplicate playtime authority.                      |
| Library cache              | SQLite is disposable. Rebuild from source manifests and files. Never store the only copy of a favorite or save decision in the cache.                                     |

## Migration algorithm

Snapshot each file with its path, hash, size and schema/profile version. Parse without discarding unknown fields or comments. Compute a semantic diff and show the scope before applying changes that affect controls or existing settings. Use the authoritative backend, or quiesce noncooperating writers before file edits. Project locks do not constrain firmware daemons or legacy scripts. If exclusive access cannot be established, refuse the write. Then lock, recheck hashes and merge only unambiguous owned keys.

Write a same-filesystem temporary file, validate the result, flush it, then replace the target using the strongest operation supported by that filesystem. Keep the prior version and a transaction journal. Test power-loss recovery on the actual FAT/exFAT/ext filesystem instead of claiming POSIX rename alone guarantees durable multi-file updates. Multi-file changes need a prepare/commit record and recovery logic.

## Switching back must preserve normal user edits

Do not restore an entire old configuration tree when returning to CrossMix. That would erase changes made in games or tools. Undo only the keys this project owns, and only when their current values still match the values it wrote. Present conflicts. Maintain forward-only migration steps plus explicit restore snapshots; older releases must refuse a future schema rather than guessing.

Use a single SQLite writer and DELETE journaling with conservative synchronous settings until the device filesystem is tested. Keep transient scan databases on RAM storage where possible, checkpoint compact caches to SD, and avoid continuous database/log writes. A damaged cache should cost a rescan, not user data.

# Library model and legacy data bridge

## Import the existing library rather than reorganizing it

Read the installed Emus manifests, launch choices, ROM roots, accepted extensions, artwork conventions and existing folder structure. Support per-system and per-game launcher choices, nested directories, multidisc playlists, archives and emulator-specific special cases through a versioned resolver. Do not rename ROMs or move saves to make the new UI simpler. \[S23–S26\]

Game { id, system_id, relative_path, display_name,  
extension, artwork_ref, source_generation,  
launcher_choices\[\], selected_launcher, availability }  
Session { id, game_id, emulator_fingerprint, started_at,  
ended_at, outcome, resume_capability, state_ref? }  
Tool { id, label, entrypoint_id, required_capabilities\[\],  
ui_owner, risk_class, return_contract }

The game ID should derive from system ID and normalized relative path, with the original bytes retained. Avoid hashing every large ROM on each scan. A moved file may be matched using an optional content fingerprint after the user requests reconciliation. Detect case collisions and Unicode normalization collisions; never merge distinct files silently.

## Scanner and cache behavior

- Scan incrementally and publish batches. Limit depth, file count, filename length and image decode budgets. Do not follow symlinks out of approved roots. Exclude temporary, hidden and save directories according to tested system rules.

- Make indexing cancelable, pause it before launch/USB/update and prioritize visible items. Use sorted paginated queries rather than loading all artwork and games into memory.

- Test tiny, empty and large libraries, malformed manifests, missing artwork, non-ASCII names, stale mounts, duplicate names and special characters. A filename must never become shell syntax.

## Favorites and Continue Playing

Roms/favourite2.json and Roms/recentlist.json contain line-oriented JSON records in the inspected scripts, not a single JSON array. Bridge both with format-preserving edits, including unknown fields and sublabels. Round-trip it through stock MainUI during hardware tests. Avoid legacy utility wrappers that delete the first recent-list line after MainUI insertion unless that insertion actually occurred. Preserve the packaged Activities executable initially: available upstream source does not fully match its packaged CLI, so its database schema needs verification before native writes. Continue Playing distinguishes “resume a verified compatible state” from “launch recently played game.” No valid resume artifact means a normal launch, clearly labeled. \[S03\]

Do not run random-game selection against an unfiltered cache. Reuse or adapt the existing exclusions and launcher resolver. Favorites, recent and random must all produce the same validated LaunchContext as a normal game selection.

# Unified controls without breaking games

## Separate physical input from meaning

Define four layers: physical devices and button positions; system UI actions such as Confirm and Back; emulator actions such as Menu or Save State; and emulated gameplay controls such as PSP Cross or PS1 Circle. A change in one layer must not silently rewrite the others. Store physical positions independently of printed A/B/X/Y labels.

| **Context**          | **Policy**                                                                                                                                                                        |
|----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Shell navigation     | Left/right categories, up/down items; explicit Confirm/Back convention; predictable repeat and focus restoration. Show button glyphs that match the selected physical convention. |
| Gameplay             | Preserve current PPSSPP mappings, RetroArch core/directory/game remaps, analog dead zones and per-game overrides. Gameplay remapping is a separate opt-in action.                 |
| Emulator menus       | Map supported menu actions to the shared convention. Test whether an emulator derives UI keys from gameplay mapping before changing settings.                                     |
| Global hardware keys | Keep firmware volume, power, function-switch and OSD semantics until measured. Reserve no chord until conflicts are inventoried.                                                  |
| External controllers | Identify devices using stable capabilities/GUIDs where available. Do not rely on joystick index 0 surviving Bluetooth reconnects.                                                 |

## Input capture and ownership

Use SDL2 for foreground UI input. Read raw evdev only in a diagnostic tool or a narrowly justified hardware adapter. Avoid a global uinput remapper or exclusive device grab in v1; those can disrupt firmware hotkeys and emulator autoconfiguration. Drain held keys at transitions and require release before the first actionable input in the next screen.

## Safe profile adoption

An “Apply shared menu controls” action detects the exact emulator build, previews the affected keys, records snapshots and applies changes only while the emulator is stopped. Unknown versions remain untouched. Offer per-emulator undo and report unsupported actions. Keep a test matrix for both confirm/back conventions, built-in controls, Bluetooth controllers and existing A/B swap settings.

Menu chords can leak gameplay presses before a combined action is recognized. Test down/up ordering, held keys, fast taps, analog drift, simultaneous volume/power input and every existing OSD shortcut. Never promise a universal menu/save/exit chord until each foreground application and firmware handler has passed the collision tests.

# RetroArch and PPSSPP adapter contracts

## RetroArch covers the current PS1 route

The inspected PS1 duckstation.sh launches the libretro core through ra64.trimui. Treat DuckStation, PCSX and SwanStation as RetroArch core profiles in this integration. Do not introduce standalone DuckStation as a prerequisite. Preserve content, directory and core override precedence, and distinguish .cfg configuration, .rmp input remaps and core options. \[S28, S29\]

Use the installed XMB menu and an original compatible asset set. The supported menu_swap_ok_cancel_buttons setting can adjust menu convention without changing the emulated controller layout. Confirm the installed build supports each setting before writing it. Menu hotkey numeric values and input-driver IDs belong in version-specific fixtures, not generic assumptions. \[S07, S30\]

## PPSSPP has a meaningful controls limitation

Current upstream KeyMap code derives native Confirm/Back from PSP Cross/Circle mappings and the PSP button preference. Therefore independent menu controls cannot be assumed from editing controls.ini. Changing that preference may also affect games that read the emulated PSP system setting. Preserve gameplay and system preference unless the user chooses that consequence. \[S11\]

Recommended path: first use supported theme and input configuration where it satisfies the contract. If independent UI convention remains blocked, maintain a small version-pinned GPL-compatible PPSSPP patch that adds a separate native-menu mapping, with the old behavior as default. Proposed new keys must be documented as project extensions, not presented as existing PPSSPP settings. A full XMB-style PPSSPP UI rewrite is a much larger optional project.

## Versioned adapter manifest

EmulatorProfile {  
id, executable_sha256, upstream_source_commit,  
config_paths, supported_keys, config_precedence,  
launch_contract, clean_exit_contract,  
state_format_id, save_roots, theme_capabilities  
}

Adapters parse and preserve unknown settings, never assume a config lives at an upstream desktop default, and re-read changes after emulator exit. No live config edits while a game may overwrite the same file. Expose common settings in native screens; retain labeled advanced emulator screens until each required control has a supported implementation.

Leave the earlier optional emulator update branch and separate binaries unchanged. Its installer-only tests do not prove hardware compatibility, save-state portability or corresponding-source compliance.

# Visual system and rendering budget

## One interaction specification

Design the home screen around Games, Continue Playing, Tools and Settings. Horizontal movement changes category; vertical movement chooses items. Use original icon silhouettes and a wave-inspired background with your own motion, color and geometry. Avoid Sony logos, ripped fonts, sounds, firmware resources and a product name that implies an official Sony release.

Specify selection, submenus, dialogs, text input, loading, network errors, empty library, low storage, missing BIOS, unsupported device and recovery screens before drawing decorative assets. Transitions must preserve focus and accept interruption. Use a monotonic clock and time-based animation rather than frame-count animation.

## Graphics implementation

- Keep a small glyph and icon atlas, batch quads by texture and clip rectangle, and use a cheap GLES2 wave pass. Avoid full-screen blur, expensive postprocessing and continuous artwork uploads.

- Decode images on a worker, bound both compressed and decoded sizes, downsample to display needs and upload on the render thread. Cache only a few screens of artwork.

- Support reduced motion, a static background, sound-off, larger text and high-contrast prompts. A missing font glyph or long translated label must not crash or spill across controls. Noto Sans needs licensed fallback fonts for uncovered scripts. HarfBuzz shapes glyphs but does not implement full bidirectional layout; preserve access to unsupported stock languages and add a tested bidi module before claiming native RTL parity.

## Provisional budgets to test

| **Metric**         | **Initial acceptance target**                                                                                                                      |
|--------------------|----------------------------------------------------------------------------------------------------------------------------------------------------|
| Navigation         | 60 Hz animation when active; p95 frame time below 16.7 ms during ordinary navigation, with no sustained input backlog.                             |
| Input response     | p95 visible response within 50 ms, measured with a camera/input test setup on device, not inferred from desktop frame rate.                        |
| Memory             | Target shell RSS under 96 MiB with a representative library; supervisor under 8 MiB. Record actual GPU allocations separately where measurable.    |
| Idle and gameplay  | Stop unnecessary animation when idle or obscured. Exit/release UI resources before games; no shell rendering during gameplay.                      |
| Startup and return | Target under 2 seconds added boot time and under 1 second warm UI return after child exit, excluding emulator shutdown. Measure on named SD media. |

These budgets can change after the first device baseline, with reasons recorded. Do not claim battery savings from low desktop CPU usage. Compare power and temperature using repeatable on-device workloads, fixed brightness and the same firmware/card.

# Foreground graphics audio and process lifecycle

## Prefer full UI resource release between programs

The safest initial model is for ui-shell to save a small navigation snapshot and exit before launching a game or graphical tool. sessiond remains without SDL video/audio. On return it starts a fresh shell instance. This avoids depending on an unproven vendor compositor or simultaneous EGL context ownership. Optimize warm handoff only after repeated device tests show a need.

| **Resource**     | **Lifecycle rule**                                                                                                                                                      |
|------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| GPU and display  | Destroy textures/context/window and close the device path before starting the child. Recreate after exit. Do not SIGSTOP a UI while it still owns an EGL surface.       |
| Audio            | Drain or stop shell sounds and close its audio device. Preserve firmware volume/routing. Test headphones, mute and Bluetooth routing where supported.                   |
| Input            | Close foreground controllers, drain events and release any optional grabs. Firmware hotkeys continue under their existing owner.                                        |
| CPU and governor | Retain CrossMix per-emulator performance choices. Record/restore changes through the verified policy; do not impose a global overclock.                                 |
| Processes        | Track exact child identities and process groups. Handle wrappers that daemonize. Reap children and distinguish normal exit, crash, failed launch and user cancellation. |
| Environment      | Use an explicit working directory and allowlisted environment for each launcher. A private shell library path must not leak into emulator or stock MainUI sessions.     |

## Exit and crash policy

Use an emulator’s proven clean-exit path first. Sending a generic signal or killing a process does not prove that SRAM, memory cards or save states reached disk. For a hung child, use a verified firmware OSD/emergency control path or documented manual recovery. Do not launch another SDL UI over a game that still owns EGL/input. A forced-exit path must explain the save-loss risk through that available interface. Collect bounded logs and return to a safe UI without overwriting save data or automatically loading an uncertain state.

Store logs in a RAM-backed ring buffer and flush a small diagnostic bundle on an error or explicit request. Include component versions, exit status and redacted adapter state. Do not continuously write verbose logs to the SD card. Do not record Wi-Fi passwords, account tokens or personal content lists unless needed for a user-requested diagnostic export.

## Resource ownership is part of acceptance

A launch/return loop must show no persistent growth in process count, file descriptors, audio handles or memory across the test sequence. A blank screen after return, duplicate game process or firmware watchdog restarting MainUI counts as a release-blocking failure.

# Power sleep and hardware services

Keep the firmware’s hardware, input, Bluetooth and OSD services until their responsibilities are mapped. CrossMix preload restores settings and starts or coordinates several of them. A replacement shell must consume those services through tested operations instead of starting competing daemons. \[S03, S27\]

| **Function**            | **Adapter design and proof needed**                                                                                                                                |
|-------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Brightness and volume   | Read current value, validate bounds, apply via verified firmware interface, reread actual result. Keep hardware buttons and UI sliders consistent.                 |
| Battery and charging    | Expose measured status with stale/unknown states. Verify units and charging semantics; do not invent a time-remaining estimate.                                    |
| Sleep and wake          | Map power-button handling, kernel suspend entry, screen/audio quiesce and firmware resume ordering. Test shell, games and active background tools separately.      |
| Shutdown and reboot     | Stop new jobs, request clean child exit, flush managed data, then delegate the supported firmware action. Never replace it with an unreviewed poweroff call.       |
| Low battery             | Preserve the firmware threshold and emergency behavior. Display warning if supported; do not promise an automatic game save without a verified emulator mechanism. |
| LED and function switch | Read existing settings and per-game/performance semantics. Avoid taking over an event that another daemon owns.                                                    |
| Clock and locale        | Preserve firmware time/timezone/language authority. Handle missing RTC/network time and invalid clock values in history ordering.                                  |

## Suspend is not save and exit

Distinguish true suspend/resume, emulator save state, and relaunch-after-poweroff. CrossMix resume code can preserve a launch command, but that alone does not establish that it captured a state. Show the actual capability for each emulator and mode. A killed process cannot be described as safely suspended.

## Hardware discovery gate

Document which process receives each physical power/volume/menu input and which component draws each OSD. Test both existing A/B-swap modes. If a firmware OSD is inseparable from a hardware service, retain it as a named visual exception or replace that service through a separate validated project. Never remove a critical service just to eliminate a mismatched overlay.

# Networking Bluetooth and USB handoff

## Network settings without new network services

Provide native screens for status, scanning, connection and known-network management through the verified existing backend. Reuse its connection manager rather than spawning a second wpa_supplicant or DHCP client. Validate SSID bytes and command arguments, keep credentials out of logs and command lines where the backend permits, and serialize reconnect operations. Implement timeouts and truthful failure reasons.

Bluetooth must be capability-driven: pairing, controller reconnect and audio support may differ by firmware. Reuse the firmware service and record the exact supported operations. Do not claim Bluetooth audio or controller coverage from a daemon filename alone. Scan/pair UI, cancellation, forget and reconnect each need physical tests.

## USB is an exclusive system transition

The inspected USB storage script terminates runtrimui/MainUI and multiple services, unmounts SD and UDISK, activates mass-storage/ADB configuration and reboots after completion. Calling it while the new supervisor still uses SD-backed executables, libraries, databases or working directories is unsafe. \[S31\]

USB_REQUESTED -\> BLOCK_NEW_WORK -\> STOP_FOREGROUND  
-\> FLUSH_AND_CLOSE_ALL_STORAGE_USERS  
-\> VERIFIED_RAM_HANDOFF -\> UNMOUNT -\> USB_EXPORTED  
-\> HOST_EJECT / EXIT -\> FIRMWARE_REBOOT -\> NORMAL_BOOT

The USB handoff helper must run from verified RAM storage with no open descriptors, current directory, mapped libraries or executable dependency that prevents unmount of the exported volumes. Validate this with /proc and mount checks on the real firmware. A copy in /tmp is insufficient if its loader/libraries or child commands still reside on SD. Reuse the firmware USB application and reboot convention, not the stock wrapper unchanged: that wrapper uses broad kills, ignores unmount failures and selects mass_storage,adb. A reviewed RAM-resident replacement/patch must verify every target is unmounted before export and preserve or explicitly disclose ADB behavior.

## Service coordination and failures

Suspend existing Syncthing/file servers/indexers before unmount using their supported lifecycle, then preserve the firmware’s restart/reboot contract. Do not re-export a volume still mounted read/write on Linux. On failed unmount, remain in a safe local state and report the process holding it; never force unmount as the normal fix. Preserve the user’s existing ADB/security state and disclose any script behavior that changes it.

Test host Windows/macOS/Linux where available, host safe-eject, cable removal, rejected export while a game saves, and a failed unmount. USB mode must have a visible explanation and a documented return path even after the normal shell has exited.

# Save safety and credible Continue Playing

## Treat three kinds of data separately

In-game saves, PS1 memory cards and emulator save states have different compatibility properties. PPSSPP documents that newer save states are usually not backward compatible, while normal in-game saves remain portable between its versions. A change of PS1 core or standalone engine may also change card/state format and naming. Do not merge these into a single “save” abstraction. \[S32, S33\]

| **Operation**     | **Required protection**                                                                                                                                            |
|-------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Interface switch  | Keep emulator paths, memstick/card paths and overrides unchanged. No save conversion.                                                                              |
| Config migration  | Snapshot only affected config plus a save-location manifest. Never make a snapshot while the emulator is writing the same data.                                    |
| Resume            | Match game identity, emulator/core fingerprint, state format, slot and referenced file. If any check fails, offer normal launch.                                   |
| Emulator change   | Require a separate test and explicit choice. Keep previous engine and its states available; do not advertise cross-engine state portability.                       |
| Backup / restore  | Copy while quiescent; verify sizes/hashes; preserve the original; confirm destination and overwrite scope. Test restoring a known fixture before trusting backups. |
| Low space / power | Check room for transactional writes and state backups. Keep the previous file when a write fails. A battery warning is not a guarantee against interrupted writes. |

## Resume record example

{"schema":1,"game_id":"psp:...",  
"emulator_profile":"ppsspp-known-build",  
"state":{"relative_path":"...","sha256":"...",  
"format_id":"verified-profile","slot":0},  
"clean_shutdown":true,"record_generation":12}

This proposed record describes evidence; it must not become an arbitrary executable command. Do not execute saved command text supplied by a ROM, cache or downloaded metadata. If a legacy cmd_to_run.sh contract remains necessary, only the validated launcher adapter may generate it.

## What v1 should expose

Show recent games and “Resume available” only where a verified artifact exists. Let the emulator own live save/load and slot management until a supported local API or a small reviewed source patch exists. Do not simulate keypresses or enable an unauthenticated network command port as the standard save mechanism. Retain existing CrossMix auto-resume options with their true limitations and per-emulator tests.

# Functional parity register for games and settings

This is the release inventory template and the known major surface. Populate it from the actual installed card and firmware before claiming complete parity. Each row needs a named owner, implementation route, functional result, visual result and evidence link. “Pending device proof” is the current status for hardware-dependent rows.

| **Existing capability**                       | **Proposed route**                             | **Acceptance evidence**                                                      |
|-----------------------------------------------|------------------------------------------------|------------------------------------------------------------------------------|
| Systems, folders, ROM filters and artwork     | Native library + Emus importer                 | Compare visible/launchable files with CrossMix across each installed system. |
| System and game emulator presets              | Typed launcher resolver                        | Same preset/core/arguments and working directory as baseline.                |
| Favorites and sublabels                       | favourite2.json bridge                         | Add/remove in each interface; both retain ordering and unknown fields.       |
| History, Activities and random game           | Existing recorder + session view               | No double counting; correct exclusions and missing-file handling.            |
| Save/load entry, auto-resume and launch modes | Versioned launch context                       | Same behavior per emulator; no dependence on fabricated MainUI logs.         |
| Multidisc and CUE/M3U helpers                 | Existing parser/tool + validated adapter       | Correct disc order, card continuity and special-path handling.               |
| RetroArch common and advanced settings        | Native common settings + XMB                   | Config/remap precedence preserved; advanced UI exception recorded.           |
| PPSSPP common and advanced settings           | Native common settings + supported theme/patch | Menu preference never silently changes gameplay or PSP system preference.    |
| Volume, brightness and status                 | Device adapter + native UI                     | Hardware buttons and UI stay synchronized after game return.                 |
| Wi-Fi, Bluetooth and service status           | Firmware backend adapters                      | Connect/disconnect/reconnect failures and cancellation tested.               |
| Appearance, language, clock and sound         | Native settings + legacy authorities           | Switchback, locale/font coverage and external edits round-trip.              |
| LED, function switch and power policy         | Verified device operations                     | No hotkey conflict; suspend/shutdown/low-battery behavior retained.          |

Add every discovered stock MainUI settings row, including any undocumented firmware-only operation. A generic “Open CrossMix” button is a recovery path; it must not conceal missing common system settings in a release described as an integrated shell.

# Functional parity register for tools and services

| **Existing capability**                          | **Proposed route**                                  | **Important boundary**                                                              |
|--------------------------------------------------|-----------------------------------------------------|-------------------------------------------------------------------------------------|
| System Tools menu                                | Import action catalogue; native categorized screens | Its launcher builds a MainUI database/state, so exec alone is insufficient. \[S24\] |
| EmuCleaner and configuration utilities           | Native job/progress adapter where safe              | Preview changes, preserve backups, and disclose any removal/rewrite.                |
| Scraper and artwork tools                        | Retain installed tool; native launch/status wrapper | Keep existing service/account requirements; no new store or account flow.           |
| PortMaster and installed ports                   | Existing entrypoints under Tools or Games           | PortManager internal UI and per-port behavior remain separate.                      |
| File manager and HTTP file manager               | Existing tools with explicit service status         | Do not add an unauthenticated web server or broaden network exposure.               |
| Syncthing and existing transfer services         | Existing service controls + status                  | Preserve configuration; quiesce before USB; do not duplicate sync processes.        |
| Media players and Moonlight                      | Retain current launch entries under Tools           | No new media category or new media/cloud integration; internal UI exception.        |
| Screenshots and screen recording                 | Retain capability and storage path                  | GPU/audio/input conflicts and start/stop lifecycle require tests.                   |
| Themes, overlays and customization tools         | Map shell themes separately; retain legacy tools    | A CrossMix theme is not a shell navigation engine. Explain each theme target.       |
| Backups, restore, OTA/update and firmware wizard | Retain advanced access; wrap supported operations   | No automatic firmware update. Legacy updater can overwrite integration hooks.       |
| USB storage and network transfer                 | Exclusive session handoff adapter                   | Must close all storage users and preserve firmware return/reboot behavior.          |
| Diagnostics, logs and advanced utilities         | Tools catalogue + support bundle                    | Redact secrets; mark unsupported firmware-specific operations.                      |

## Catalogue every installed app

For each Apps entry, record label, config and launch path, required executable/library, file writes, network behavior, privileges, whether it forks, whether it needs MainUI, and how it returns. Compare the generated catalogue with the installed card, not just upstream README. Include user-added apps and give unknown entries a safe legacy route until reviewed.

# Source layout and reproducible build design

src/  
shell/ screens, scene tree, GLES2 renderer, audio  
session/ state machine, child tracking, recovery  
core/ protocol, jobs, paths, logging, transactions  
adapters/ crossmix, firmware, retroarch, ppsspp  
library/ scanner, index, favorites, history  
profiles/ firmware + CrossMix + emulator fingerprints  
schemas/ IPC, settings, manifests, migrations  
assets/ original source art + generated bundles  
tests/ unit, fixtures, integration, fault, visual  
packaging/ overlay layout, install, verify, rollback  
toolchains/ CMake profile + sysroot manifest  
docs/ decisions, device inventory, parity, runbooks  
third_party/ pinned source metadata + notices

## Build environments

Use a pinned Linux x86_64 build container with the official aarch64 GCC 7.5 toolchain and a read-only sysroot assembled from authorised SDK/firmware files. Keep toolchain archive checksums and extraction instructions. Do not install host ARM packages into the target sysroot or let host pkg-config paths leak into the build. \[S04\]

Build a native desktop target with fake device services and the same business logic. Build a device target with the selected SDL2/GPU profile. Use CMAKE_SYSROOT and target-only pkg-config search paths. Inspect the final ELF interpreter, NEEDED entries, RPATH/RUNPATH and GLIBC/GLIBCXX requirements with readelf. Prefer dynamic target libc/GPU/SDL; decide static versus private libstdc++ after testing ABI and licences.

## Pin compatible dependencies

Each dependency record includes upstream URL, immutable revision or release, archive hash, selected licence, patches, compiler flags and resulting artifact hash. A version enters the lockfile only after it compiles with the target toolchain and passes tests. Follow libsodium’s build guidance separately, including its caution against LTO/sanitizers on that library, while retaining sanitizer coverage for project code. \[S39\] Do not pretend a latest-release number is a validated device dependency. Keep host build dependencies separate from shipped runtime files.

## Repeatability checks

Set deterministic timestamps and ordering, fix locale/timezone, normalize archive owners/modes and use SOURCE_DATE_EPOCH from the release commit. Build twice in clean workspaces and compare file hashes; use diffoscope for differences. Record unavoidable nondeterminism rather than calling a release reproducible without evidence. Store symbols and build logs outside the device package.

# Automated testing and continuous integration

| **Layer**            | **Tools and required checks**                                                                                                                                                  |
|----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Core logic           | CTest with a pinned Catch2 or doctest version; deterministic navigation, state transitions, job cancellation, version negotiation and stale-generation handling.               |
| Parsers and security | Clang libFuzzer + ASan/UBSan host builds for manifests, JSON/INI/CFG, paths and image headers. Seed malformed, huge and adversarial inputs.                                    |
| Adapter fixtures     | Golden files for each supported firmware/CrossMix/emulator profile. Round-trip unknown fields/comments; assert only declared keys changed.                                     |
| Process lifecycle    | Fake launchers that exec, fork, fail, hang, signal, write late or orphan a child. Assert one foreground owner and accurate recovery.                                           |
| Data transactions    | Fault injection at each write/flush/replace/commit step; read-only/full storage; stale snapshots; interrupted multi-file updates; restore conflicts.                           |
| UI and assets        | Desktop deterministic screenshot tests for focused states, localization extremes, scaling, no artwork and error screens. Pixel tolerances account for font/render differences. |
| Package and shell    | ShellCheck, shell test harness/Bats, schema validation, path-traversal/symlink/zip-bomb tests, install/upgrade/rollback simulation and licence/manifest completeness.          |
| Target build         | Cross-compile, inspect ELF/ABI/dependency closure and generate SBOM. QEMU user-mode may test pure code, not GPU, power, USB or firmware behavior.                              |

## Pull request gates

Require host tests, parser fuzz smoke, static checks, target build, package tests and source/licence inventory for changed dependencies. Use clang-tidy with a focused rule set and compiler warnings as errors for project code. Maintain a longer scheduled fuzz/test run only when the implementation project authorizes it; no recurring service is created by this plan.

## Golden behavior tests

For each existing launcher preset, record a sanitized baseline command/environment/file-change fixture and compare the new adapter result. Test spaces, quotes, dollar signs, semicolons, newlines and non-ASCII ROM names. Shell interpolation must never turn a game title into a command. Run the same favorite and config fixture through both old and new readers where available.

A green CI result means the tested software behavior passed in that environment. It does not certify original-Smart-Pro hardware support. Label test reports as host, emulated CPU or physical device evidence.

# Physical acceptance and release qualification

Use a spare SD clone, verified backups and legally obtained test content. Record device model, firmware hash/version, card model/filesystem, adapter profile, package hash and exact test steps. Numbers below are proposed minimum release exercises; failures require diagnosis rather than another run until a lucky pass.

| **Area**            | **Physical acceptance sequence**                                                                                                                                                     |
|---------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Boot and switchback | 20 cold boots in each interface and 20 switches; corrupt/missing preference, missing asset and intentionally crashing shell all reach the safe path.                                 |
| Launch and return   | 100 mixed game/tool cycles; no lost input/audio, blank screen or leak. Test a hung game and sessiond death while a child survives; recovery must never start MainUI over that child. |
| Controls            | Both menu conventions, current OS A/B-swap modes, held buttons on transition, analog drift and hotkey collisions; built-in and at least one supported external controller.           |
| Sleep and power     | At least 50 sleep/wake cycles across idle, PPSSPP, RetroArch and tools; normal shutdown/reboot; safe low-battery observation without destructive testing on valuable saves.          |
| USB and services    | At least 20 export/return cycles, busy-volume refusal, host eject and cable removal; verify sample file hashes and restored service state.                                           |
| Save integrity      | Known in-game saves/cards/states before and after switches, launches, config changes and recovery; restore a backup; verify incompatible-state behavior.                             |
| Storage and update  | Read-only/full SD, damaged cache, interrupted package activation, rejected signature/hash, rollback, and an upstream update that touches the boot hook.                              |
| Performance         | Measure frame/input latency, cold/warm load, RSS, CPU, temperature and battery under fixed conditions; compare with stock CrossMix on the same device.                               |
| Complete catalogue  | Exercise every installed system/preset at smoke-test level and every tool/settings operation; deeper gameplay for high-risk PSP/PS1 cases.                                           |

## Release blockers

Any reproducible save corruption, unsafe USB unmount, unrecoverable boot failure, duplicate foreground ownership, severe hotkey collision or undocumented loss of an existing function blocks release. A visual exception needs explicit acceptance and a visible label. Keep recorded evidence with the release, not just a checklist marked “done.”

Limit power-interruption tests to disposable fixtures and a spare card. Do not cut power during writes to the user’s real saves or attempt hardware modifications as a shortcut to fault injection.

# Packaging updates and rollback

## Overlay package layout

System/custom-shell/  
releases/\<release-id\>/ binaries, private libs, assets, profiles  
state/ activation records, preferences  
backups/ small config/boot snapshots  
recovery/ verified minimal recovery payload  
notices/ component licences and source manifest  
Apps/InterfaceSwitch/ stock bridge, if approved

These paths are proposed. Confirm naming and startup placement against the installed CrossMix layout before implementation. Keep releases immutable and user state outside release directories. Use a validated activation record rather than a symlink so the design does not assume a Unix filesystem.

## Install and activate

- Validate model, firmware profile, CrossMix baseline, free space, package signature and file hashes. Reject path traversal, absolute paths, device nodes and unapproved links. No script may run merely because it appears in an archive.

- Stage into a new directory, verify every file, snapshot the small boot/config surface and prepare the activation journal. Keep ROMs, BIOS, saves, emulator binaries and unrelated CrossMix files untouched.

- Activate a pending release, boot it once, commit only after health checks, and retain the previous release plus recovery route. Rollback must preserve newer user saves and undo only project-owned settings.

## Protect against updates overwriting the integration

CrossMix and firmware updates may replace startup scripts, launchers and menus. Declare the exact compatible ranges/hashes; detect changed contracts at startup and fail back safely. Initially require an integration-aware compatibility check after upstream updates. Do not disable the user’s existing updater silently, and do not let it overwrite the only backup of the original boot path.

## Distribution format

Prefer a source repository plus a signed SD overlay for the first public version. A complete SD image adds redistribution obligations for firmware, GPU blobs, emulators, fonts, art and utilities. Ship only files whose provenance and redistribution permission are established. BIOS, commercial ROMs and Sony firmware/assets are outside the package.

The offline package installer is part of the trusted base. Keep signing keys off the handheld and out of source control; ship only verification keys. A locally modified root filesystem is outside the authenticity guarantee, which protects package provenance rather than an already-compromised device.

# Security and trust boundaries

## Inputs are data

Treat ROM names, scraped metadata, theme files, JSON manifests and saved launch records as untrusted. Validate types, lengths, paths, dimensions and enum values. Resolve game/tool IDs to an installed registry. Invoke fixed executables with argument arrays; never concatenate user-derived values into system(), popen() or sh -c.

Existing CrossMix scripts may still use shell. Audit each inherited path that processes variable input, then quote/fix it or constrain that adapter. An allowlisted wrapper is not safe if it later evaluates an unsanitized ROM name. Use a clean working directory and controlled environment; block path traversal and symlink escapes before file operations.

## Keep the attack surface small

- No arbitrary shell endpoint, remote command socket, theme scripting or downloaded executable plug-ins in v1.

- No new always-on network service. Expose status and controls for services the user already installed; preserve their authentication and binding behavior.

- Do not log credentials. Store Wi-Fi secrets through the established backend and protect diagnostic exports. FAT permissions are not a reliable privacy boundary.

- Use packet/schema limits and job timeouts so a damaged client or file cannot hang the supervisor. Rate-limit repeated errors and failed launches.

## Privilege model

Run the UI with reduced permissions only if the firmware supports a real separation without breaking SDL/input access. Otherwise keep hardware operations in a narrow module, document the root-runtime limitation, and avoid claiming a security sandbox. A private socket and process split prevent accidental misuse but cannot resist another root process.

## Update trust

Verify an Ed25519 signature over the exact manifest bytes and hashes before extracting/activating. Keep explicit key IDs and a documented key-rotation/revocation process. Require a user-visible confirmation before downgrading across a known security or data-schema boundary. Do not implement cryptography from scratch. \[S22\]

## Supportability

Use stable error codes with a human explanation and a suggested safe action. Export a redacted bundle containing component identities, recent state transitions and relevant hashes. The device should remain useful offline and recover without a support server, account or cloud dependency.

# Licensing provenance and release audit

| **Component**                    | **Licence posture**                                                          | **Release obligation**                                                                                               |
|----------------------------------|------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| New shell and supervisor         | Recommend MIT for original project code.                                     | Choose the licence before accepting contributions; keep authorship and dependency notices.                           |
| SDL2 / stb_image / JSON          | SDL2 zlib; stb_image dual public-domain/MIT; nlohmann JSON MIT.              | Pin source, retain notices; choose and record the stb licence path. \[S15–S17\]                                      |
| FreeType / HarfBuzz / font       | FreeType FTL or GPLv2; HarfBuzz permissive MIT-style; font licence separate. | Select FTL, retain credit/notices; use a verified OFL font and respect reserved names. \[S18–S20\]                   |
| SQLite / libsodium               | SQLite public domain; libsodium ISC. \[S46\]                                 | Retain provenance and applicable notices; include source records. \[S21–S22\]                                        |
| CrossMix files                   | Mixed distribution and third-party contents.                                 | Audit exact files/headers; do not assume one repository licence covers every bundled binary/asset.                   |
| RetroArch and assets             | XMB code GPL-3.0-or-later; assets root CC-BY-4.0 with file/set exceptions.   | If redistributed/modified, meet source and attribution obligations; inspect fonts and chosen asset set. \[S07–S09\]  |
| PPSSPP and patches               | GPL-2.0-or-later plus third-party subcomponents.                             | Provide corresponding source/build instructions for shipped binary; retain patch/source commit identity. \[S10–S12\] |
| Firmware / GPU / other emulators | Vendor blobs and per-component licences.                                     | Do not redistribute without permission/provenance. Emulator cores may impose different conditions.                   |
| NextUI / Spruce / PyUI / MinUI   | Noncommercial terms or unclear provenance need review.                       | No code/assets copied into the recommended base without a separate audit. \[S13–S14\]                                |

## Release bill of materials

For each shipped file, record supplier, source URL/revision, build recipe, licence expression, required notices, modifications, binary hash and corresponding source location. Include generated asset source files and font licences. Produce SPDX or CycloneDX SBOM data plus human-readable notices. Keep a source archive matching the exact release, including submodules and patches.

A download link to an upstream project is not proof that it matches a third-party binary. Keep the earlier optional emulator binaries outside a release until the corresponding-source and notices question is resolved. Public release needs a final legal/provenance review; this technical plan is not legal advice.

# Work packages estimates and dependency order

Estimates are person-weeks of focused engineering/design/test work. They assume one experienced embedded Linux/C++ developer, access to the original device, stable firmware and an unchanged initial emulator set. They include integration tests and documentation, but not a complete redesign of every third-party app UI.

| **Package**               | **Work and exit evidence**                                                                                   | **Effort** |
|---------------------------|--------------------------------------------------------------------------------------------------------------|------------|
| W0 Evidence and recovery  | Device inventory, SD restore proof, complete function catalogue, pinned SDK/licence baseline.                | 1–2        |
| W1 Session vertical slice | Verified boot hook; SDL input/frame; one game launch/return; safe CrossMix switchback; USB/power risk spike. | 2–3        |
| W2 Foundations            | Protocol, state machine, jobs, settings transactions, path/security layer and test fixtures.                 | 2–3        |
| W3 Core shell             | Navigation, settings framework, keyboard/dialogs, original visual system, accessibility and library views.   | 3–4        |
| W4 CrossMix integration   | Preset/launch-context adapters, favorites/history, existing tools, common native system screens.             | 3–5        |
| W5 Controls and emulators | Versioned RA/PPSSPP adapters, config diff/undo, input parity, supported theme and narrow patch if needed.    | 2–4        |
| W6 Hardware lifecycle     | Power/OSD/network/Bluetooth/USB coordination; service quiesce and repeated device tests.                     | 3–5        |
| W7 Release engineering    | Installer, signed manifests, rollback, source/SBOM/notices, compatibility profiles.                          | 2–3        |
| W8 Qualification          | Full parity pass, fault/recovery tests, performance tuning, beta fixes and user guide.                       | 3–6        |

Total: 21–35 person-weeks before contingency. Add 25–40% while the boot/USB/firmware contracts remain unknown. A solo project could span roughly 6–12 months depending on available hours and rework; parallel UI/adapter work can shorten calendar time only after the interfaces stabilize. A small proof of concept may appear much earlier but is not a release.

## Dependency sequence

W0 -\> W1 -\> architecture go / no-go  
W1 -\> W2 -\> W3 and W4 in parallel  
W2 + known launch contract -\> W5  
W1 -\> W6 early risk work; W4/W5 -\> W6 completion  
W2 -\> W7; W3/W4/W5/W6/W7 -\> W8 -\> release

# Risk register and decision gates

| **Risk**                             | **Response**                                                                                    | **Gate**                                                             |
|--------------------------------------|-------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| MainUI-only settings/menu contracts  | Inventory all stock operations; implement typed native routes; keep explicit legacy fallback.   | No complete-parity claim until every installed row is exercised.     |
| Unknown boot/watchdog ownership      | Inspect firmware; preserve original entry; test supervised game and UI states.                  | W1 device proof before default boot activation.                      |
| PowerVR/SDL ABI mismatch             | Use pinned vendor-compatible stack; inspect ELF and backend; avoid global library replacement.  | Native display + input + repeated emulator handoff.                  |
| USB unmount with SD users            | Verified RAM helper; close process/library/storage references; honor reboot path.               | Busy-volume refusal and repeated export tests.                       |
| Control coupling and OSD conflicts   | Separate mapping layers; versioned patches where needed; preserve gameplay.                     | Physical collision matrix and reversible adoption.                   |
| Data loss through migration/rollback | Single authority, hash preconditions, transaction journal and targeted undo.                    | Fault injection plus actual save/restore fixtures.                   |
| Upstream updates overwrite hooks     | Compatibility profiles and fail-safe detection; integration-aware update review.                | Upgrade/rollback test on each supported baseline.                    |
| Unclear binary/asset licences        | Prefer original/permissive code; exact source and notice records; exclude unresolved artifacts. | Release audit complete before redistribution.                        |
| Scope expands to every app UI        | Name visual exceptions; split source-level restyling into separate projects.                    | User agrees to the v1 functional/visual contract.                    |
| No physical device access            | Continue host work only; keep hardware tasks explicitly blocked.                                | No hardware claims or public stable release without device evidence. |

## Milestones the user can review

M1: boot, launch, return and recovery on a plain screen. M2: the final navigation/control prototype with fake data. M3: real library and settings parity with a tested tool catalogue. M4: PSP/PS1 controls and save safety. M5: physical qualification, signed overlay and recovery guide. Each review should include a short demonstration, test evidence, known exceptions and the next decision.

A milestone passes because its acceptance evidence exists. A large generated code diff, attractive desktop demo or successful cross-compile is not a substitute for the relevant integration proof.

# Keep AI assistance bounded and inspectable

## Use AI for well scoped units

Maintain a short architecture decision record, protocol schemas, compatibility profiles and the parity register in the repository. Give each coding task a single outcome, allowed files, current facts, explicit exclusions and an executable acceptance test. Examples: preserve unknown favorite fields; reject a stale config transaction; generate one deterministic UI screen; simulate a child that forks and hangs.

Use the strongest reasoning model at architecture boundaries, unfamiliar firmware integration, difficult failures and final reviews. Use smaller routine tasks for scaffolding and mechanical transformations where tests provide an oracle. Do not ask an agent to “build the whole OS” in one conversation and then infer correctness from its summary.

## Workflow per change

- Write or select a fixture that captures the expected behavior and failure cases.

- Implement one module or adapter change on a branch, with no unrelated refactor.

- Run focused tests, then the relevant integration suite. Review the actual diff and generated artefacts.

- Record the exact source/build/profile identities and any hardware evidence. Merge only after a human-readable checkpoint.

Keep research citations and licence checks in dependency records so future tasks do not repeat the same web investigation. Cache redacted hardware observations and fixture data. Reuse a stable interface contract; do not repeatedly redesign it inside new prompts.

## Avoid expensive wrong turns

The highest-value early work is the boot/USB/power/launch spike. Once it passes, parallelize UI, library and adapter modules behind the fixed protocol. Avoid parallel agents editing the same boot or settings code. Let CI answer deterministic questions, and reserve model review for ambiguity and design tradeoffs. No token, quota or cost counts are invented here; actual usage depends on the chosen tools, task size and rework.

## The first implementation brief after approval

Create only a read-only device inventory and a reversible session proof on a spare card. Deliver the boot contract, process/service map, verified ABI profile, original restoration procedure and measured launch/return behavior. Stop before permanent installation, emulator upgrades or publication unless separately approved. That evidence should convert the largest unknowns in this blueprint into concrete engineering tasks.

# Decisions and inputs needed before building

| **Decision or input**      | **Recommendation**                                                                                                                                  |
|----------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| First release scope        | Approve full functional access plus explicitly named advanced-app visual exceptions. Keep native everyday settings and dialogs coherent.            |
| Stock switch location      | Accept a CrossMix App/System Tools bridge unless a supported nested Settings extension is discovered. New shell gets the exact Appearance selector. |
| Menu convention            | Choose south-button or east-button Confirm, and the label/glyph style. Keep gameplay mappings unchanged by default.                                 |
| Emulator policy            | Freeze the installed PPSSPP/RetroArch/core set for initial development. Evaluate the earlier optional update independently later.                   |
| Device evidence            | Provide the original Smart Pro, firmware/version information, an SD backup and a spare card. Authorize read-only inventory first.                   |
| Graphics and identity      | Approve an original PSP-inspired direction. Choose the product name later, after checking conflicts; no Sony assets needed.                         |
| Public release intent      | Decide personal use versus public distribution early enough to plan notices, source hosting, release keys and support commitments.                  |
| Licence for new code       | MIT is the recommended default; keep GPL emulator modifications separate with their required source.                                                |
| Implementation environment | Select an available development computer/environment when implementation is authorized. This document does not start that work.                     |

## Recommended next decision

Approve the architecture and the two honest UI boundaries: the stock switch-entry location and advanced third-party screens. Then authorize W0 and W1 only. Those stages answer whether the device can safely host the integrated shell before committing to the full build schedule.

## What this blueprint adds

The project now has a chosen stack, a process model, versioned adapter boundaries, concrete data/IPC contracts, a settings authority policy, save and recovery rules, a build/release approach, parity registers and testable work packages. The remaining uncertainty is concentrated in observable firmware and hardware behavior, rather than hidden inside a general promise to make a new launcher.

Keep this technical blueprint separate from the earlier feature/research plan. Update the editable companion as device evidence and decisions arrive, while preserving the version that each implementation milestone used.

# Pinned inventory and MainUI compatibility traps

The pinned repository contains 112 direct Emus/\*/config.json descriptors, 310 top-level emulator shell scripts, 111 System Tools actions and 17 Apps descriptors. Of the emulator descriptors, three are utility pseudo-platforms and 109 cover game/port/media entries. These are source-file counts, not counts of independently tested engines or games. Include firmware-bundled and user-added apps in the on-device inventory too. \[S03\]

## Five details that change the implementation

- System Tools, Scraper and BootLogo prepare MainUI cache/list state instead of presenting a standalone complete UI. Native replacements must implement their menu model or hand over to MainUI explicitly.

- The preset loader checks per-game .games_config files before per-system launchers.cfg. Empty launch entries are separators. System visibility in show.json uses labels, so new stable IDs must preserve that legacy mapping.

- FolderOverrideFinder uses bind mounts and a re-exec marker. Keep mount cleanup and exactly-once Activities tracking correct after normal exit, forced exit and shutdown.

- VNC and the Activities shortcut explicitly depend on a process named MainUI; VNC also uses a fixed input event path. Leaving these services installed does not prove they work in the new session.

- CrossMix customization can modify firmware-resident files and credentials. Do not rerun it when switching interfaces. Resume preload returns 1 in normal non-resume paths; inspect the caller before treating that status as failure.

## Maintain a generated coverage register

Generate the file/action inventory from each supported commit and compare it in CI. A new or removed descriptor must produce a visible review item. Record each operation’s contract, native/legacy route, state writes, functional/visual status, test evidence and supported profile. The complete function-group register follows; all rows remain targets until implemented and tested.

Existing screen recording, image/ebook readers, background music and radio remain accessible as installed tools. Excluding a new Photos/media category does not authorize deleting existing players or viewers. Existing credentialed services and destructive utilities need their original confirmation/security boundaries preserved.

# Complete integration register

Pinned source contracts and proposed routes. No row represents a completed hardware test.

Native means a new shell screen with a tested adapter. Keep means the current application/backend remains in use. Bridge means an explicit legacy MainUI handoff. Gate means device or binary-version proof is still required. \[S03, S23–S31, S40–S45\]

| **Function group**                    | **Existing contract**                                               | **Proposed boundary**                                                                                         |
|---------------------------------------|---------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------|
| Boot choice, startup app, startup tab | starts/start_tab.sh, °post_starts.sh, preload.sh                    | Native selector after verified firmware seam; preserve startup app vs frontend vs resume as separate settings |
| Stock UI return and recovery          | MainUI + runtrimui lifetime, /tmp/state.json                        | Bridge and safe-mode default; single display owner                                                            |
| Game / platform browsing              | all Emus descriptors, rompath/extlist/hidebios, show.json           | Native data adapter, preserve user visibility/order, folder art and alternate labels                          |
| Search and ROM refresh                | cache7 databases, reset_list.sh, romwinidx                          | Native search/index; retain stock-compatible refresh without deleting user data                               |
| Favorites                             | Roms/favourite2.json, Favorites repair/sort                         | Native compatible reader/writer; atomic backup, unknown-field preservation                                    |
| Recent games                          | Roms/recentlist.json; utility first-line removal                    | Native compatible writer, explicit utilities exclusion                                                        |
| Best collections and shortcuts        | Best/\*/config.json and launch.sh; txt and .launch behavior         | Keep launch semantics; Native browser; validate shortcuts before execution                                    |
| All default and alternate emulators   | Emus/\*/config.json launch and launchlist                           | Keep emulator scripts/binaries; Native selection; skip separator entries                                      |
| Per-game / system launch presets      | load_launcher.sh, save_launcher.sh, .games_config and launchers.cfg | Native action + backwards-compatible storage; label ABI adapter                                               |
| ROM context actions                   | romscripts/.romscript_launcher.sh                                   | Native menu or Keep selector with explicit ROM context                                                        |

# Complete integration register continued

Pinned source contracts and proposed routes. No row represents a completed hardware test.

Native means a new shell screen with a tested adapter. Keep means the current application/backend remains in use. Bridge means an explicit legacy MainUI handoff. Gate means device or binary-version proof is still required. \[S03, S23–S31, S40–S45\]

| **Function group**                         | **Existing contract**                                           | **Proposed boundary**                                                                        |
|--------------------------------------------|-----------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| Core / directory / game overrides          | FolderOverrideFinder.sh, RetroArch configs                      | Keep existing bind mount/re-exec and cleanup contracts                                       |
| Save states, SRAM, autosave, autoload      | existing emulator/RetroArch configuration; AUTO LOAD STATE menu | Keep paths and binaries; test every emulator family rather than assume universal RA behavior |
| Resume after shutdown                      | kill_apps.sh → persistent cmd_to_run.sh → preload.sh            | Native supervisor adapter; keep cancel-on-MENU, exact selected launcher and save behavior    |
| Activities tracking / details / completion | System/bin/activities and Apps/Activities                       | Keep shipped executable; Gate native DB writes                                               |
| RetroArch menu and alternative builds      | Apps/RetroArch/launch.sh; held-Y build picker                   | Keep app; Native explicit build menu where wanted                                            |
| In-game TrimUI menu / hotkeys              | disable_tmenu, ra_hotkey, input daemon                          | Keep daemons and emulator integration; verify menu coexistence                               |
| Cheats, RetroAchievements, PSX analog      | SystemTools EMULATORS scripts                                   | Native action list or Bridge; preserve credentials privately and original config paths       |
| Overlays, scaling, widescreen variants     | SystemTools OVERLAYS; per-emulator launchlists                  | Native controls backed by existing scripts; keep effect/wide modes as distinct actions       |
| PortMaster manager / install / runtimes    | Apps/PortMaster, ex_config, trimui hooks                        | Keep app and its cwd/environment/autoinstall behavior                                        |
| Installed ports / performance profiles     | Emus/PORTS; Roms/PORTS; label-selected profile                  | Keep launch wrapper; explicit mode adapter                                                   |

# Complete integration register continued

Pinned source contracts and proposed routes. No row represents a completed hardware test.

Native means a new shell screen with a tested adapter. Keep means the current application/backend remains in use. Bridge means an explicit legacy MainUI handoff. Gate means device or binary-version proof is still required. \[S03, S23–S31, S40–S45\]

| **Function group**                          | **Existing contract**                                        | **Proposed boundary**                                                              |
|---------------------------------------------|--------------------------------------------------------------|------------------------------------------------------------------------------------|
| Random game                                 | Apps/random, MainUI cache7 inputs                            | Keep only with valid caches; or Native equivalent covering same exclusions         |
| Scraping single / all / system / background | Apps/Scraper, Emus/\_Scraper, scraper.json                   | Native menu + Keep backend; separate cancel/status; Bridge available               |
| Music players / radio / background audio    | Apps/MusicPlayer, Emus/MUSIC                                 | Keep GMU/stock/mpv/ffmpeg variants, playlist/cover utilities and remembered choice |
| Video playback                              | Emus/VIDEOS; stock media player firmware                     | Keep existing players and launch options; Native file list                         |
| Pictures, ebook / manual reading            | stock Picture; Apps/EbookReader selects stock/Pixel/KOReader | Keep apps; discover actual stock app descriptors; Gate manual player path          |
| File manager                                | Apps/FileManager                                             | Keep DinguxCommander                                                               |
| Terminal                                    | Apps/Terminal                                                | Keep SimpleTerminal; preserve sticks_disabled cleanup                              |
| Screen recording                            | Apps/ScreenRecorder + ScreencapTK; fb0/OSS and L1+R1 stop    | Keep; Gate framebuffer/renderer capture correctness and background lifecycle       |
| Screenshots                                 | scripts/screenshot.sh; SELECT+R2                             | Keep shortcut/backend; Gate capture with chosen renderer                           |
| User guide                                  | Apps/user_guide                                              | Keep with correct cwd and CrossMix style assets                                    |

# Complete integration register continued

Pinned source contracts and proposed routes. No row represents a completed hardware test.

Native means a new shell screen with a tested adapter. Keep means the current application/backend remains in use. Bridge means an explicit legacy MainUI handoff. Gate means device or binary-version proof is still required. \[S03, S23–S31, S40–S45\]

| **Function group**                                     | **Existing contract**                                             | **Proposed boundary**                                                                           |
|--------------------------------------------------------|-------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| Theme packs / backgrounds / icons / fonts / labels     | SystemTools THEME and ADVANCED SETTINGS                           | Native new-shell appearance; preserve separate stock theme settings and executable side effects |
| UI sound / BGM                                         | SystemTools SOUND; stock theme files/system values                | Native controls via adapter; do not conflate new shell audio with global game volume            |
| Volume / brightness / mute                             | systemval, shmvar, /tmp/system/set_volume and set_brightness      | Native tested IPC adapter; preserve hardwareservice and OSD                                     |
| Display color and night mode                           | system.json color settings; nightmode scripts/OSD                 | Native tested adapter or Keep configurator; retain shortcut/OSD button selection                |
| Wi-Fi scan / connect / forget / hotspot                | hardwareservice, wifi flags, wpa_supplicant storage, stock MainUI | Bridge until protocol proven; Native status/toggle where verified                               |
| Bluetooth audio / controllers                          | trimui_btmanager; /tmp/btdev_addr; RA audio switching             | Keep service; Bridge pairing UI until verified; test connect/disconnect during games            |
| SSH / SFTP                                             | ex_config + CrossMix SSH scripts + firmware enablessh             | Native script adapter synchronizing all stores; security-sensitive explicit action              |
| SFTPGo FTP / HTTP / WebDAV-related configured services | System/sftpgo config and NETWORK scripts                          | Keep configured server and management app; inventory enabled protocols from actual config       |
| SMB guest / secure                                     | NETWORK SMB scripts; System/etc/samba                             | Native action adapter; keep separate guest/secure states and verify access                      |
| Telnet                                                 | NETWORK TELNET; post_starts                                       | Native explicit action; warn about unencrypted access                                           |

# Complete integration register continued

Pinned source contracts and proposed routes. No row represents a completed hardware test.

Native means a new shell screen with a tested adapter. Keep means the current application/backend remains in use. Bridge means an explicit legacy MainUI handoff. Gate means device or binary-version proof is still required. \[S03, S23–S31, S40–S45\]

| **Function group**                         | **Existing contract**                                | **Proposed boundary**                                                                |
|--------------------------------------------|------------------------------------------------------|--------------------------------------------------------------------------------------|
| Syncthing                                  | NETWORK Syncthing; System/etc/syncthing              | Keep service; Native toggle/status                                                   |
| Tailscale                                  | NETWORK Tailscale; state directory                   | Keep service; Native toggle/reset with confirmation                                  |
| VNC                                        | NETWORK VNC; waits for MainUI and event4             | Gate adaptation required; cannot claim preserved by simply leaving service installed |
| Network identity / IP / discovery          | Display IP; hostname; Avahi; wsddn                   | Native display/status; keep boot services                                            |
| Fn switch assignments / turbo              | fn_editor/scripts.json, /usr/trimui/scene            | Keep firmware editor initially; Native UI only after protocol verification           |
| SmartLed / LED behavior                    | Apps/SmartLed, led_config.sh, led daemon state       | Keep app/service; Native status; avoid competing LED writers                         |
| Controller mappings, A / B choice, polling | inputd_switcher, swap_ab; systemval; joystick config | Gate restart behavior and event IDs; keep calibration app initially                  |
| Hardware diagnostics                       | SystemTools CONTROLS/Hardware Test.sh                | Keep hardware test app                                                               |
| CPU profile / active cores                 | scripts/cpufreq.sh, save/restore, OSD widgets        | Keep accepted device profiles; Native adapter must query supported frequencies       |
| Sleep / wake / dim / low battery           | firmware keymon/hardwareservice, dimtime, stay_awake | Gate real-device tests; don't replace with LCD-off or raw echo mem assumptions       |

# Complete integration register continued

Pinned source contracts and proposed routes. No row represents a completed hardware test.

Native means a new shell screen with a tested adapter. Keep means the current application/backend remains in use. Bridge means an explicit legacy MainUI handoff. Gate means device or binary-version proof is still required. \[S03, S23–S31, S40–S45\]

| **Function group**                    | **Existing contract**                                                | **Proposed boundary**                                                                                     |
|---------------------------------------|----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| Shutdown / reboot / force exit        | kill_apps.sh, cmd_to_run_killer.sh, System/bin/shutdown, Apps/Reboot | Preserve graceful RA QUIT, process-tree cleanup, resume save, sync and detached shutdown                  |
| USB mass storage                      | System/resources/usb_storage/launch.sh → firmware app                | Keep firmware app/reboot convention; replace unsafe wrapper with verified RAM handoff and unmount checks. |
| Firmware settings backup / restore    | FW Settings Save-Load.sh                                             | Keep with explicit review; covers Wi-Fi, MainUI and both joystick calibrations                            |
| Filesystem check, UDISK format        | SystemTools TOOLS                                                    | Keep but destructive-operation confirmation; cannot run while custom shell holds storage                  |
| ROM maintenance                       | CUE/M3U generators, dot cleanup, EmuCleaner                          | Keep scripts; Native task status; preserve paths/caches                                                   |
| Firmware wizard / OTA / update notice | \_FirmwareCheck, crossmix_update, ota_update, update_notification    | Keep maintenance capability; gate package conflicts and original TSP firmware identity                    |
| Boot logo                             | Apps/BootLogo and Emus/\_BootLogo                                    | Bridge or Native picker invoking guarded backend; flash is separate from shell selection                  |
| Third-party / future apps             | Apps and firmware app descriptors                                    | Dynamic discovery, controlled launch + honest capability status; don't hardcode only current 17           |

# Primary sources

Sources checked during research on 14 October 2026. Moving branches require repinning before implementation.

Source references support observed project behavior and licence statements. Architecture, schemas, performance targets, estimates and test counts are recommendations. The actual installed device has not been inspected or tested for this blueprint.

**S01 User fork and requested project**  
<https://github.com/daniel1990000/CrossMix-OS-project>

**S02 CrossMix pinned baseline commit**  
<https://github.com/cizia64/CrossMix-OS/commit/206d612fdef83972ed54a17de955125d0c0b3528>

**S03 CrossMix source tree at the pinned baseline**  
<https://github.com/cizia64/CrossMix-OS/tree/206d612fdef83972ed54a17de955125d0c0b3528>

**S04 Official original Smart Pro toolchain and SDK**  
<https://github.com/trimui/toolchain_sdk_smartpro/releases/tag/20231018>

**S05 Official original Smart Pro firmware releases**  
<https://github.com/trimui/firmware_smartpro/releases>

**S06 KNULLI EmulationStation source dependencies and licence**  
<https://github.com/knulli-cfw/batocera-emulationstation/tree/f7c5ae103815761ccd34bc55b021c6e150442c96>

**S07 RetroArch XMB source**  
<https://github.com/libretro/RetroArch/blob/a25f167c53f23b5ea57a3839ff508708454a32b8/menu/drivers/xmb.c>

**S08 RetroArch XMB documentation**  
<https://docs.libretro.com/guides/xmb/>

**S09 RetroArch assets licence**  
<https://github.com/libretro/retroarch-assets/blob/d9f969054dc7fbb6fa89519036d2b971e0855b51/COPYING>

**S10 PPSSPP source and licence**  
<https://github.com/hrydgard/ppsspp>

# Primary sources continued

Sources checked during research on 14 October 2026. Moving branches require repinning before implementation.

**S11 PPSSPP native menu key derivation**  
<https://github.com/hrydgard/ppsspp/blob/master/Core/KeyMap.cpp>

**S12 PPSSPP theme implementation**  
<https://github.com/hrydgard/ppsspp/blob/f6aea4c85c2979818ba498940db2d60128899518/UI/Theme.cpp>

**S13 NextUI notice and historical licence caveats**  
<https://github.com/LoveRetro/NextUI/blob/a87e3b56b8b40b89245c19d47c46254f51779b33/NOTICE>

**S14 Spruce and PyUI source licence inventory**  
<https://github.com/spruceUI/spruceOS/tree/425d7e883b1af6304d201fb19ade4c2863f6328e>

**S15 SDL2 licence**  
<https://github.com/libsdl-org/SDL/blob/SDL2/LICENSE.txt>

**S16 stb image source and licensing**  
<https://github.com/nothings/stb/blob/master/stb_image.h>

**S17 nlohmann JSON licence**  
<https://github.com/nlohmann/json/blob/develop/LICENSE.MIT>

**S18 FreeType licences**  
<https://freetype.org/license.html>

**S19 HarfBuzz licence**  
<https://github.com/harfbuzz/harfbuzz/blob/main/COPYING>

**S20 Noto fonts licence**  
<https://github.com/notofonts/latin-greek-cyrillic/blob/main/OFL.txt>

# Primary sources continued

Sources checked during research on 14 October 2026. Moving branches require repinning before implementation.

**S21 SQLite copyright and public domain statement**  
<https://www.sqlite.org/copyright.html>

**S22 libsodium signature documentation and source licence**  
<https://libsodium.gitbook.io/doc/public-key_cryptography/public-key_signatures>

**S23 CrossMix common launcher**  
<https://github.com/cizia64/CrossMix-OS/blob/206d612fdef83972ed54a17de955125d0c0b3528/System/usr/trimui/scripts/common_launcher.sh>

**S24 CrossMix System Tools launcher**  
<https://github.com/cizia64/CrossMix-OS/blob/206d612fdef83972ed54a17de955125d0c0b3528/Apps/SystemTools/launch.sh>

**S25 CrossMix launcher selection**  
<https://github.com/cizia64/CrossMix-OS/blob/206d612fdef83972ed54a17de955125d0c0b3528/System/usr/trimui/scripts/load_launcher.sh>

**S26 CrossMix PSP launchers**  
<https://github.com/cizia64/CrossMix-OS/tree/206d612fdef83972ed54a17de955125d0c0b3528/Emus/PSP>

**S27 CrossMix startup and hardware integration scripts**  
<https://github.com/cizia64/CrossMix-OS/tree/206d612fdef83972ed54a17de955125d0c0b3528/System/usr/trimui/scripts>

**S28 CrossMix PS1 DuckStation launcher**  
<https://github.com/cizia64/CrossMix-OS/blob/206d612fdef83972ed54a17de955125d0c0b3528/Emus/PS/duckstation.sh>

**S29 RetroArch configuration overrides and remaps**  
<https://docs.libretro.com/guides/overrides/>

**S30 RetroArch menu and hotkey configuration reference**  
<https://github.com/libretro/RetroArch/blob/master/retroarch.cfg>

# Primary sources continued

Sources checked during research on 14 October 2026. Moving branches require repinning before implementation.

**S31 CrossMix USB storage integration**  
<https://github.com/cizia64/CrossMix-OS/blob/206d612fdef83972ed54a17de955125d0c0b3528/System/resources/usb_storage/launch.sh>

**S32 PPSSPP save data and state locations**  
<https://www.ppsspp.org/docs/faq/>

**S33 PPSSPP update and save compatibility guidance**  
<https://www.ppsspp.org/docs/reference/how-to-update/>

**S34 Minimum firmware requested by pinned CrossMix**  
<https://github.com/cizia64/CrossMix-OS/blob/206d612fdef83972ed54a17de955125d0c0b3528/trimui/firmwares/MinFwVersion.txt>

**S35 Pinned firmware check and archive selection**  
<https://github.com/cizia64/CrossMix-OS/blob/206d612fdef83972ed54a17de955125d0c0b3528/System/starts/_FirmwareCheck.sh>

**S36 Pinned bundled firmware archives**  
<https://github.com/cizia64/CrossMix-OS/tree/206d612fdef83972ed54a17de955125d0c0b3528/trimui/firmwares>

**S37 Manufacturer original Smart Pro specifications**  
<https://trimui.com/pages/trimui-smart-pro>

**S38 GCC 7 language support and caveats**  
<https://gcc.gnu.org/gcc-7/changes.html>

**S39 libsodium installation and build guidance**  
<https://doc.libsodium.org/installation>

**S40 CrossMix folder override lifecycle**  
<https://github.com/cizia64/CrossMix-OS/blob/206d612fdef83972ed54a17de955125d0c0b3528/System/usr/trimui/scripts/FolderOverrideFinder.sh>

# Primary sources continued

Sources checked during research on 14 October 2026. Moving branches require repinning before implementation.

**S41 CrossMix System Tools dispatch and recents behavior**  
<https://github.com/cizia64/CrossMix-OS/blob/206d612fdef83972ed54a17de955125d0c0b3528/Emus/_SystemTools/launch.sh>

**S42 CrossMix resume preload**  
<https://github.com/cizia64/CrossMix-OS/blob/206d612fdef83972ed54a17de955125d0c0b3528/trimui/app/preload.sh>

**S43 CrossMix post-start services and MainUI coupling**  
<https://github.com/cizia64/CrossMix-OS/blob/206d612fdef83972ed54a17de955125d0c0b3528/System/starts/%C2%B0post_starts.sh>

**S44 CrossMix shutdown and app cleanup**  
<https://github.com/cizia64/CrossMix-OS/blob/206d612fdef83972ed54a17de955125d0c0b3528/System/usr/trimui/bin/kill_apps.sh>

**S45 CrossMix full System Tools action catalogue**  
<https://github.com/cizia64/CrossMix-OS/tree/206d612fdef83972ed54a17de955125d0c0b3528/Apps/SystemTools/Menu>

**S46 libsodium ISC licence**  
<https://github.com/jedisct1/libsodium/blob/master/LICENSE>
