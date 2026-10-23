# Artwork refresh and controller text entry

Use **Games → Refresh library**, or F5 on a desktop, after changing artwork or
library metadata. Refresh keeps the current page and game when they still
exist. If a game disappears, focus stays on its nearest surviving neighbor. If
the old page disappears, the view requests the last surviving page.

The read-only snapshot provider invalidates its own records and repeats its
existing bounded inspection. Live integration continues to query initialized
PyUI managers; refresh does not instantiate history managers or add a second
ROM scanner. No game, save or configuration file is changed by refresh.

Refresh also clears successful and failed artwork entries. Each asynchronous
decode carries the library's artwork generation, so a completion from an older
refresh cannot replace a new cover or mark its new request as failed. Texture
uploads remain on the UI thread; file reads and decoding remain on the bounded
worker. The texture cache holds at most six 512×512 RGBA images, about 6 MiB of
pixel data. Negative entries are limited to 128; request and result queues each
hold at most two entries. These bounds exclude codec internals and SDL overhead.
See [formats and decoder limits](artwork-formats.md).

The on-screen keyboard uses five character rows and a separate wide action row.
All 50 keys fit the 1280×720 logical workspace at text scales 0.75 through 1.75.
Character, field, action and help text scale together. Long queries show their
newest characters and the end cursor. D-pad movement wraps within a row, clamps
at the top/bottom and retains the intended column across short and action rows.

| Physical control | Keyboard action |
|---|---|
| Configured Confirm, South or East | Select the focused key |
| Opposite of Confirm | Cancel without changing the submitted search |
| West | Delete the last code point |
| North | Submit the search |
| D-pad or existing left-stick navigation | Move focus |

Help uses physical button positions and follows the Confirm preference. Desktop
Enter submits, Escape cancels and Backspace/Delete removes the last code point.
Frontend preferences do not change gameplay or native emulator mappings.

Controller entry provides uppercase A–Z, digits, `-'.,:/!?()` and Space. The
standalone preview's external SDL text input preserves Unicode text while
excluding line breaks and C0/C1 controls. Embedded entry uses the existing
PyUI controller route and the on-screen character set. Queries are limited to
128 code points; deletion removes one code point. An IME, grapheme editing,
lowercase controller entry and complete font
coverage are outside the current contract. Non-Latin input remains useful only
where the installed font can display it.

The [captures](../evidence/ui-polish/) are actual SDL host renders using original
synthetic metadata and artwork. Host tests cover both Confirm preferences,
every key, punctuation/actions, Unicode input, actual maximum-size label bounds,
source metadata refresh, same-path replacement and stale worker completions.
Physical readability, controller behavior and target codec availability still
require an original Smart Pro trial.
