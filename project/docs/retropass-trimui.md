# RetroPass for TrimUI

This port uses the actual [RetroPass source](https://github.com/retropassdev/RetroPass), pinned at `65fa22fadc3c88bf8353d093c6fa9b3fa3d92f83`. The complete tracked upstream tree is retained unchanged under `project/vendor/retropass`: 177 files, 9,560,952 bytes. That includes its C# implementation, XAML interface, assets, setup documentation, authors and GPL version 2 licence. `project/retropass/source-lock.json` records every file's size and SHA-256; packaging rejects missing, added or changed upstream files.

The upstream application targets Xbox's Windows UWP APIs. Its `.sln` and `.csproj` cannot execute directly on TrimUI's Linux runtime. The working port translates the relevant source into Python/SDL and connects it to the existing spruce/PyUI frontend. Windows storage, XAML and URI-launching calls stay in the preserved upstream reference. Existing native owners continue to handle device input, display, emulator launch, return and saves.

## Source carried into the port

| Upstream implementation | TrimUI adaptation |
|---|---|
| `RetroPass/Playlist.cs` | `retropass/library.py` preserves recent-first, distinct landing-page ordering, with five entries by default. Stable game IDs prevent duplicate titles from collapsing into one entry. |
| `RetroPass/DataSourceEmulationStation.cs` | `retropass/library.py` translates the gamelist metadata fields and core-name extraction to Linux paths and `.so` cores. Parsing does not execute emulator commands. |
| `RetroPass/MainPage.xaml`, `GameCollectionPage.xaml` | `retropass/layout.py` and `retropass/renderer.py` carry the source tile proportions and dashboard presentation into SDL. |
| `RetroPass/FocusControl.xaml`, default theme resources | The adapted renderer uses the source's rectangular accent focus treatment with bounded artwork loading and retargetable movement. |

The selected theme is separate from the existing interface ownership switch. Choosing the RetroPass appearance does not activate a device profile or create a second input or process owner. Existing settings, dialogs, search, collections, backup history and launch confirmation remain available through their established contracts.

## Licence and source delivery

`project/retropass` is the GPL-2.0-only adaptation scope. The upstream licence and `AUTHORS.md` remain unchanged in `project/vendor/retropass`; `retropass/NOTICE.txt` identifies the port and its changes. The surrounding original project helpers retain their existing MIT notices. The MIT project licence does not relicense RetroPass or its adaptations.

The signed preview includes the adapted Python source under `app/retropass`, a complete copy of upstream under `notices/RetroPass-source`, the GPL text and the port notice. The source ZIP contains both the original helpers and the same complete upstream source. Python wheels include the adapted `retropass` package, its licence/notice/source lock, and all 177 upstream files under `share/psp_shell/source/vendor/retropass`. Existing archive paths containing `original-source` are retained for tool compatibility; the descriptor, provenance and notices explicitly identify the third-party scope. The current development descriptor uses `retropass-host-preview` and `selected_third_party_payload: ["retropass"]`.

The owner reports that the author gave full permission to use and import RetroPass into this OS. The source lock records this as owner-provided information; no author message was sent by the assistant. The shipped GPL notices and corresponding source are preserved.

## Verification boundary

The provenance tests verify all imported bytes, reject missing/changed/extra source, check source materialization without Git, and verify the packaged corresponding source and notices. Rendering and navigation checks cover the host SDL port. Host checks establish neither physical TrimUI performance nor input/display behavior on an actual device. Device qualification follows the existing casebook; this port does not enable those gates or replace emulator binaries.
