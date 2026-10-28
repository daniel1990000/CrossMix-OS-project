# Dev19: supplied-image host audit

The owner executed the [ISO continuation](iso-enabled-roadmap-2026-10-26.md). This is the game-testing batch authorized in that chat. It began on merged dev18 main `30aa59ffa35195bcad2b2553f91c43fc32301556`, rather than the older dev17 planning baseline. Main's later dev18 merge record at `05d1088f35ff76231144ef44c393deb95900bc28` was incorporated.

Work is saved in [PR #3](https://github.com/daniel1990000/CrossMix-OS-project/pull/3). Clean implementation and local package identity: **`a962d6c9d213f9d76b6a104ba78a282029cc453a`**. Later evidence and handover commits have separate identities. Dev19 is an original-only host preview; no emulator, game, state, native patch or device profile is selected for distribution. Published dev16 is unchanged.

## Input and environment

The supplied image is Grand Theft Auto: Vice City Stories, native ID `ULUS10160`, disc version `1.03`, 1,696,006,144 bytes, SHA-256 `e7d26d0efb2fb7a37bb73c51bddae9baffa39feab7d76e30299b4c9e5d6fc80a`. The original is retained separately from disposable test copies.

Tests use x86_64 Debian, Xvfb, software OpenGL and SDL dummy audio. This is neither the TrimUI nor its firmware/PowerVR path. Native audio recordings contain pre-volume mixed PCM; they do not establish speaker output, latency or fault-free playback.

The official PPSSPP 1.20.3 AppImage booted the image and opening scene. A full SDL host build of pinned upstream `d357e6a32934800d3d80b49f910a603e1b069751` also ran the game. It contains locked patches 0001–0003 plus separately reviewed diagnostic correction 0005. Binary digest: `6924b0392831517fb54108b98b9faa743492fe7d2709690098f91226fcdf56de`. Compiler, dependencies, source/submodule identities and limits are in [native evidence](../evidence/iso-continuation-20261026/native/README.md). Pinned FFmpeg static inputs were not rebuilt from their corresponding sources; no complete distribution-source claim follows.

## Findings and changes

The real-image read-only frontend offered Start/Resume despite its explicit unavailable-launch capability. It now explains that launch is unavailable and removes those actions. Independently permitted Game options remains accessible. Direct dispatcher refusal remains covered. The first broad check caught the Game options regression and an outdated UI expectation; those failures and corrections remain recorded.

The native GPU statistics source copied `sizeof(double) * count` bytes into a `vector<float>`. An exact-function sanitizer reproduction failed on old source and passed with `sizeof(float)` for empty, small and full histories. The optional patch is under `project/ppsspp/`; the desktop candidate used it for subsequent observations. This is a reproduced source defect, not a whole-game AddressSanitizer run.

Keyboard gameplay reached the Soldier objective, moved the player, entered the motorcycle and drove it. Native SaveSlot/Load callbacks produced success records tied to exact engine, game and state hashes. Fresh processes loaded saved bytes, including a load followed by a new save. A later failed save retained the earlier successful completion and state. See the [protocol report](../evidence/iso-continuation-20261026/native/protocol-report.json) and [independent review](../evidence/iso-continuation-20261026/native/independent-review.json).

A run through existing `run_owned_tree` exited normally, reaped its child and restored the prior subreaper state without external cleanup. A first attempt correctly stayed pending while SDL-autolaunched dbus descendants survived; its assisted cleanup and the clean retry are distinct. The retry explicitly prevented host dbus autolaunch. This proves that kernel boundary for that host run, not composed frontend Resume.

## Acceptance register

| Package | Status | Evidence and unmet criterion |
|---|---|---|
| G01: real-image frontend | Pass within read-only scope | Actual image identity, space-containing argv, search/filter/paging, information rendering and immutable card checks pass. Favorites, recents and collection records are explicit fixtures. [Receipt](../evidence/iso-continuation-20261026/frontend/g01-readonly-frontend.json). |
| G02: desktop baseline | Partial | Stock boot, controllable gameplay, native states and normal exits observed. A further 24m47.686s run exercised vehicles, interiors, airport roads and swimming, but did not complete Soldier; savedata stayed empty. Ordinary game save/relaunch/Continue remains untested. [Parent baseline](../evidence/iso-continuation-20261026/desktop/g02-baseline.json), [extended gameplay](../evidence/iso-continuation-20261026/native/ordinary-gameplay-report.json). |
| G03: config/menu/Undo | Partial | Eleven helper edits and generic rollback pass against native-created INI. Actual native readback confirms 2x then restored 1x; default/swapped Confirm/Back work through SDL virtual input, and Spruce Midnight renders. Manual/automatic frameskip and explicit global fallback also read back correctly. Native exit materializes the fallback as a local override; future global changes then do not follow. Qualified manager Apply/Undo and physical buttons remain unverified. [INI receipt](../evidence/iso-continuation-20261026/frontend/g03-native-config.json), [native UI follow-up](../evidence/iso-continuation-20261026/frontend/g03-native-ui-followup.json), [frameskip/fallback](../evidence/iso-continuation-20261026/frontend/g03-native-frameskip-followup.json). |
| G04: native state protocol | Partial | Actual native packets and fresh reloads observed, including matching-hash truncated data reaching the real loader and failing. [Additional cases](../evidence/iso-continuation-20261026/native/additional-protocol-report.json). Authenticated checkpoint promotion and death/power-loss acceptance unproven. Native accepts caller-supplied slot metadata and a replayed trusted request; actual envelope helpers reject changed nonce/stale sequence. Later qualified slot/path/hash adoption remains blocked. [Boundary review](../evidence/iso-continuation-20261026/native/slot-replay-boundary-review.json). |
| G05: composed frontend Resume | Positive path blocked; host boundary and refusal checks pass | Actual unqualified profile stays false; optional capture omitted, explicit Resume and fresh-interpreter capability retrieval reject. [Receipt](../evidence/iso-continuation-20261026/frontend/g05-native-boundary.json). |
| G06: gameplay measurements | Partial; stationary host scope completed | Five independent 30-second 1x/2x pairs validate through the existing importer. Contaminated pair retained and replaced in isolation. Separate 1,800-second stationary run exits normally. Driving/action/title comparisons, audio quality, frame pacing and demanding-profile qualification remain untested. [Measurements](../evidence/iso-continuation-20261026/measurements/README.md). |
| G07: fixes/certification | Pass for selected host implementation | 1,213 strict checks, all five pinned sources, no skips/errors/failures. Clean package, installed smoke, fixture rollback, signatures/inventories and no-Git ZIP rebuilds pass. [Evidence](../evidence/iso-continuation-20261026/certification/README.md). |
| G08: report/handover | Pass within recorded scope | Sanitized reports, scripts, raw counters, failed attempts, explicit gaps and continuation instructions retained. No device completion inferred. |

## Gameplay measurements

The five matched stationary pairs measured median native speed readings of 100.0004% at 1x and 100.0001% at 2x. This is descriptive software-rendered host evidence; the difference provides no useful improvement claim. Native FPS is an approximate update-window count and cannot establish panel pacing.

The separate stationary soak collected 1,748 counter responses over 1,800.001648 seconds and exited normally. Its mean native speed reading was about 99.9994%. Other native gameplay/settings sessions overlapped this soak, as recorded. The separately sampled 20-minute resource segment observed peak RSS 261,537,792 bytes and net growth 4,100,096 bytes; this does not diagnose or rule out a leak. Closed WAVs contain readable nonzero PCM; audio quality was not reviewed. Frame pacing, input latency and energy remain unavailable.

## Verification and delivery

Baseline main passed 1,209 strict checks. Final changed-tree verification passed 1,213; its ten changed/new file hashes independently match clean commit `a962d6c`. The test ran immediately before committing, not on a later clean checkout. Packaging used a separate clean checkout of that implementation.

Local dev19 has 68 payload files and 236 original-source entries, inventory SHA-256 `8106a5775c74b49872875985c68a339aa7001ca715c3c18b8b579a0835ed5487`. Both ZIPs rebuilt byte for byte without Git. Generated development signing keys were deleted. See the [package receipt](../evidence/iso-continuation-20261026/certification/package-receipt.json). CI passed [run 40383733188](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/40383733188); its merge checkout and package have separate identities.

Private artifacts currently live under `/workspace/trimui-audit/`: `private-inputs/` contains image/receipt; `desktop/` gameplay actions/screenshots/scene states; `native/` full build and original protocol records; `frontend/` config experiments; `measurements/` raw counters and audio; `package-dev19/` local original-only artifacts. These session paths are not durable storage promises. GitHub retains hashes and commands, not game or save bytes. Reconstruction needs the same privately held input and exact recorded sources/configuration; hashes cannot recover missing files.

The original roadmap stays **14/25 complete**, with **0/13 physical areas run**. This batch does not qualify device performance, input, sleep, power, recovery, PS1, ports or production Resume. Run the existing inventory/recovery and 13-area casebook on the target before device recommendations. Full frontend state transfer still needs genuine source, foreground, writer and device qualification; no fixture or native packet grants those prerequisites.
