# Classic PSP presentation — 22 October 2026

The SDL frontend now uses a crossbar with its selected category at roughly 23% of screen width and 26% of screen height. Category icons move along a horizontal strip; only the active category has a label. The vertical item column shares that anchor. The selected item grows brighter and larger, with its title to the right. The previous panel layout, branding header, tab underlines and colored selection tiles have been removed.

The background is an original blue color field with two broad translucent wave surfaces. Pictograms are original vector geometry, oversampled into cached SDL textures. Text uses the existing OFL Noto Sans font. Real artwork stays rectangular and aspect-fit; missing artwork shows a quiet generic placeholder. Options use a translucent side sheet, and the keyboard uses flat keys. Reduced motion, large text, high contrast and the existing physical Confirm/Back preference remain available.

The upper-right clock comes from the coordinator's actual local time. Rendering consumes the immutable clock string. No battery value is displayed because these snapshots do not have a verified battery reading. Footer diamonds indicate actual TrimUI button positions: Search is west/X, Favorite is north/Y, and Confirm/Back follow the user's selected convention.

## Actual PSP references

These official Sony manual screenshots were downloaded and visually inspected on 22 October 2026:

| Source | What informed the design |
|---|---|
| [Game category](https://manuals.playstation.net/document/en/psp/current/game/game.html), `img/game001.jpg` | Left-of-center anchor, selected label, vertical UMD/Memory Stick placement, sparse composition and blue waves |
| [Photo](https://manuals.playstation.net/document/en/psp/current/photo/photo.html), `img/photo001.jpg` | Category pictogram spacing and relative sizes |
| [Music](https://manuals.playstation.net/document/en/psp/current/music/music.html), `img/music001.jpg` | Inactive icons, white text and empty space |
| [Game options](https://manuals.playstation.net/document/en/psp/current/game/options.html), `img/g_options001.jpg` | Translucent right-side options list |

The source manual images are 240×136. Screenshot comparisons must identify those as real PSP references and the new 1280×720 SDL captures as host renders. Sony screenshots remain comparison references outside the runtime payload. No Sony firmware, font, icon pack or audio was extracted.

## Use of the requested repositories

| Repository and inspected revision | Applied here |
|---|---|
| [JohnnyCollado/PlayFieldPortal](https://github.com/JohnnyCollado/PlayFieldPortal/tree/5ee271ea9545685417aecdd13b5ace033cdb7806), `5ee271ea9545685417aecdd13b5ace033cdb7806` | `feature/feature-xmb/.../ui/XMBCategoryBar.kt` informs the anchored filmstrip, selected-only labels and .58 inactive opacity. `XmbStepMotion.kt` informs a 100 ms row glide, 200 ms catch-up cap, last-row glide after jumps larger than three rows, and immediate placement when the page changes. `ui/motion.py` is a new Python implementation of that policy. |
| [sashkinbro/EmuCoreA](https://github.com/sashkinbro/EmuCoreA/tree/16c1bfb244e9359b242e410e468032cae0c111ef), `16c1bfb244e9359b242e410e468032cae0c111ef` | `app/src/main/java/com/sbro/emucorea/ui/home/HomeShelfMode.kt` informs flat, aspect-fit cover presentation and a restrained missing-cover fallback. Android/Compose, its emulator core, metadata scanner and input router were not imported into the existing SDL runtime. |
| [hrydgard/PPSSPP](https://github.com/hrydgard/ppsspp/tree/d357e6a32934800d3d80b49f910a603e1b069751), pinned v1.20.3 | The native palette was checked against `UI/Theme.cpp` and `assets/themes/defaultthemes.ini`, then updated to azure/white using supported theme fields. PPSSPP continues to provide its own native menus, fonts, icons, controls and wave implementation. The theme keeps its existing identifiers and transaction/Undo contracts. |

PlayFieldPortal's pinned README links to a root LICENSE, but that file is absent from the inspected tree. The owner supplied permission to use the named repositories in this conversation. The work above uses documented layout/motion policies with attribution and original Python/geometry; it does not import its Kotlin code or third-party icon packs. EmuCoreA retains PPSSPP/PSPSDK and dependency notices. No EmuCoreA or PPSSPP source was copied into the MIT presentation layer. Existing native patches remain in their separate GPL scopes.

## Validation boundary

The subsequent [source study](psp-source-study.md) traces the active paths more deeply and records the resulting pagination, focus, text-cache and long-title fixes, with fresh SDL screenshots.

Check the current visual evidence record for the exact test and packaging receipts. Host screenshots demonstrate this SDL implementation, including settings, game lists, side-sheet options and search. The PPSSPP SVG is a palette illustration, not an emulator screenshot. These design changes do not activate a device profile, replace an emulator binary, or establish physical TG5040 performance/readability.
