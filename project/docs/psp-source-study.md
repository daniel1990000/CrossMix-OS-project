# PSP menu source study — 22 October 2026

This is a targeted source-level study of the actual menu, navigation, text and artwork paths in the three requested repositories. It is not a claim that every file was read, every feature was audited, or any binary was decompiled. Source is available, so following its active call paths gives more useful evidence than reconstructing those paths from binaries.

The [PlayFieldPortal trace](../evidence/source-study/playfieldportal.json) records the release entry point, lifecycle state binding, category/list composition, controller dispatch, settings/modal boundaries and artwork pipeline. The [PPSSPP and EmuCoreA trace](../evidence/source-study/native-and-emucorea.json) records the inspected source files, hashes, topics and explicit limits. Both retain exact upstream revisions. The [earlier visual study](psp-visual-design.md) retains the actual Sony PSP reference screenshots and the overall design decisions.

## Applied findings

| Source observation | Result in this frontend |
|---|---|
| PlayFieldPortal passes explicit column/landing identities to its row motion policy. | Pagination, reordered results and replacement row IDs reset the animation coordinate space. Metadata-only changes preserve an active glide. |
| PlayFieldPortal measures a menu title with a two-line limit before positioning the divider. | Options headers use up to two measured lines. Longer titles remain available in the existing paged message body, including at the largest text preference. Choices stay below the message. |
| PlayFieldPortal preserves the selected ID through refresh, then falls back to the nearest remaining index. | Removing a focused row retains its nearest neighbor; an explicit fresh view still starts at the first row. |
| PPSSPP caches text geometry independently of draw color. | Shadows, focus tints and alpha changes reuse one white glyph texture through SDL color/alpha modulation. Existing cache bounds and texture ownership remain in force. |
| PPSSPP wrapping tracks input positions rather than comparing paragraph values. | Repeated and empty paragraphs correctly mark undisplayed text with an ellipsis. |

These are original Python implementations of observed policies. Kotlin/Compose, C++ rendering infrastructure, emulator engines and third-party icon packs were not imported into the presentation layer. Licensing scopes and upstream asset provenance remain as described in the visual study.

## Measured and visible evidence

The cache probe draws the same text/font/width through 100 alpha changes, including shadow and foreground. Raster/upload calls fell from **165 to 1**, and cached glyph data from **7,470,540 to 45,276 bytes**. The counts describe this specific software-renderer scenario. Single-sample host timings are retained in the trace for transparency and do not establish target-device speed, memory use or battery life.

[New options capture](../evidence/source-study/options.png) and [large-text capture](../evidence/source-study/large-text-options.png) are actual SDL output with original synthetic game metadata. [Home](../evidence/source-study/home.png) and [library](../evidence/source-study/library.png) are fresh captures of the standard demo application. [The capture script](../evidence/source-study/capture.py) runs those paths with fresh state; it does not composite or edit the application screenshots. The displayed clock is the actual host capture time.

The [verification record](../evidence/source-study/verification.json) retains the complete source-backed test and development-package receipts, including the initial failed run and its corrections. Hardware qualification, installed emulator binaries and activation gates are unchanged.

The complete local check passes **561 tests**: 500 host/source checks and 61 PPSSPP checks, with zero skips, failures or errors. The final dev6 development package passes signature/inventory verification, deterministic rebuilds, installed-payload smoke testing and fixture rollback. [Exact-commit GitHub CI](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39822730380) also passes all 561 checks, dev6 packaging and artifact upload. An existing shell-boundary test fixture now waits for its actual resident-start marker before reporting readiness; production behavior and its exact fail-closed assertions are unchanged.

## Deliberate limits

The active PlayFieldPortal XMB labels use ellipsis; a marquee was not found on that path. PPSSPP has a clipped long-label animation, but the measured options header already provides full title access without adding motion. PPSSPP's component named `AsyncImageFileView` explicitly says it is not actually asynchronous; its name is not evidence of an asynchronous loading contract. The existing bounded decoder/main-thread texture-upload split remains in place.

EmuCoreA's bounded cover jobs, cancellation checks, aspect-fit imagery and background readability were examined. This study does not add another scanner, downloader, input router or emulator owner. Per-path artwork revision invalidation and larger keyboard labels remain possible separate improvements and are not claimed here.
