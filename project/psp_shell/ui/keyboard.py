"""Controller text entry, shared layout and physical button hints.

The on-screen character set is uppercase Latin, digits and common title
punctuation. Space is an action key. External SDL text input accepts Unicode;
text is bounded by code points, and deletion removes one code point. This is
not an IME, a grapheme editor or a claim of complete font/language coverage.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

from dataclasses import dataclass
import math


KEYBOARD_COLUMNS = 10
KEYBOARD_TEXT_LIMIT = 128
KEYBOARD_CHARACTERS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-'.,:/!?()")
KEYBOARD_ACTIONS = ("Space", "Delete", "Find", "Cancel")
KEYBOARD_KEYS = KEYBOARD_CHARACTERS + KEYBOARD_ACTIONS


def keyboard_text(value: object) -> str:
    """Keep literal text, without line breaks or C0/C1 control characters."""
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value[:KEYBOARD_TEXT_LIMIT]
                   if character >= " " and not "\x7f" <= character <= "\x9f")


def _rows(keys: tuple[str, ...]) -> tuple[tuple[int, ...], ...]:
    characters = tuple(index for index, key in enumerate(keys) if key not in KEYBOARD_ACTIONS)
    actions = tuple(index for index, key in enumerate(keys) if key in KEYBOARD_ACTIONS)
    rows = tuple(characters[start:start + KEYBOARD_COLUMNS]
                 for start in range(0, len(characters), KEYBOARD_COLUMNS))
    return rows + ((actions,) if actions else ())


def _center(keys: tuple[str, ...], row: tuple[int, ...], position: int) -> float:
    # Character columns stay aligned on a partial row. Wide actions span the
    # whole workspace; matching their centres avoids an arbitrary index jump.
    columns = len(row) if keys[row[0]] in KEYBOARD_ACTIONS else KEYBOARD_COLUMNS
    return (position + .5) / columns


def move_keyboard_focus(selected: int, action: str, preferred_column: float | None = None,
                        keys: tuple[str, ...] = KEYBOARD_KEYS) -> tuple[int, float | None]:
    """Wrap within a row; clamp vertically and retain the intended column."""
    rows = _rows(keys)
    if not rows:
        return 0, None
    selected = selected if 0 <= selected < len(keys) else 0
    row_index, column = next((r, row.index(selected)) for r, row in enumerate(rows) if selected in row)
    row = rows[row_index]
    if action in ("left", "right"):
        column = (column + (-1 if action == "left" else 1)) % len(row)
        return row[column], _center(keys, row, column)
    if action not in ("up", "down"):
        return selected, preferred_column
    target_row = rows[max(0, min(len(rows) - 1, row_index + (-1 if action == "up" else 1)))]
    intended = preferred_column if preferred_column is not None else _center(keys, row, column)
    target_column = min(range(len(target_row)), key=lambda c: abs(_center(keys, target_row, c) - intended))
    return target_row[target_column], intended


@dataclass(frozen=True)
class KeyboardCell:
    index: int
    key: str
    x: int
    y: int
    width: int
    height: int
    font_size: int


@dataclass(frozen=True)
class KeyboardHint:
    position: str
    title: str


def keyboard_hints(confirm: str = "south") -> tuple[KeyboardHint, ...]:
    confirm = "east" if confirm == "east" else "south"
    return (KeyboardHint(confirm, "Select key"),
            KeyboardHint("south" if confirm == "east" else "east", "Cancel"),
            KeyboardHint("west", "Delete"), KeyboardHint("north", "Find"))


@dataclass(frozen=True)
class KeyboardLayout:
    title: tuple[int, int, int]
    field: tuple[int, int, int, int]
    text: tuple[int, int, int, int]
    cells: tuple[KeyboardCell, ...]
    hint_positions: tuple[tuple[int, int], ...]
    hint_font_size: int


def keyboard_layout(text_scale: float = 1.0,
                    keys: tuple[str, ...] = KEYBOARD_KEYS) -> KeyboardLayout:
    """Return pre-scaled text sizes in a fixed 1280×720 workspace.

    Five character rows and a separate wide action row leave two help rows.
    Cell geometry is shared with focus navigation, including the partial row.
    """
    scale = (float(text_scale) if type(text_scale) in (int, float) and math.isfinite(text_scale)
             else 1.0)
    scale = max(.75, min(1.75, scale))
    cells = []
    rows = _rows(keys)
    for row_index, row in enumerate(rows):
        is_action = keys[row[0]] in KEYBOARD_ACTIONS
        count = len(row) if is_action else KEYBOARD_COLUMNS
        gap = 8
        width = (1032 - (count - 1) * gap) // count
        y = 546 if is_action else 223 + row_index * 63
        for column, index in enumerate(row):
            cells.append(KeyboardCell(index, keys[index], 124 + column * (width + gap),
                                      y, width, 60 if is_action else 55,
                                      round((18 if is_action else 22) * scale)))
    return KeyboardLayout(title=(124, 66, round(27 * scale)),
                          field=(124, 130, 1032, 76),
                          text=(141, 146, round(24 * scale), 998),
                          cells=tuple(cells),
                          hint_positions=((143, 626), (664, 626), (143, 665), (664, 665)),
                          hint_font_size=round(15 * scale))
