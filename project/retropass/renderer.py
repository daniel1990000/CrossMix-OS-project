"""SDL translation of RetroPass's MainPage/GameCollectionPage presentation.

Derived from retropassdev/RetroPass at 65fa22fadc3c88bf8353d093c6fa9b3fa3d92f83,
especially MainPage.xaml, GameCollectionPage.xaml and FocusControl.xaml.
The platform API is the existing TrimUI SDL renderer; UWP is not emulated.
SPDX-License-Identifier: GPL-2.0-only
"""
from __future__ import annotations

import ctypes
import math

import sdl2

from psp_shell.ui.motion import StepGlide
from .layout import (ACCENT, ART_HEIGHT, BACKGROUND, BACKGROUND_TOP,
                     FOCUS_BORDER_WIDTH, FOCUS_RADIUS, TILE_BACKGROUND,
                     TILE_FOCUSED, TILE_WIDTH)


class RetroPassView:
    """One bounded cover shelf, using the native immutable navigation snapshot.

    RetroPass's horizontal playlist and Uniform cover fit are retained. The
    handheld adaptation reserves more room for title text, drops the expensive
    animated blur and keeps an immediate focus border while the shelf glides.
    """

    def __init__(self, renderer):
        self.renderer = renderer
        self.scroll = StepGlide()

    def background(self, high_contrast=False):
        r = self.renderer
        r._rect(0, 0, 1280, 720, (0, 0, 0) if high_contrast else BACKGROUND)
        if not high_contrast:
            # The XAML gradient reaches #1F1F1F at 27% of the screen.
            for line in range(24):
                fraction = line / 23
                shade = tuple(round(a + (b - a) * fraction)
                              for a, b in zip(BACKGROUND_TOP, BACKGROUND))
                r._rect(0, line * 9, 1280, 9, shade)

    def draw(self, snapshot, now):
        r, prefs = self.renderer, snapshot.preferences
        scale = prefs.text_scale
        white, muted = (255, 255, 255), (205, 205, 205)
        focus = white if prefs.high_contrast else ACCENT
        self.background(prefs.high_contrast)
        r._label("RetroPass", 48, 27, 29, white, 320)
        r._label("for TrimUI", 206, 37, 17, muted, 300)
        if snapshot.display_clock:
            width = r.text.measure(snapshot.display_clock, 19)
            r._label(snapshot.display_clock, 1232 - width, 35, 19, white, 300)
        elif snapshot.demo:
            r._label("Desktop preview", 982, 36, 16, muted, 250)

        # Retain all native categories. Adaptive measured tabs avoid clipping
        # Continue Playing at the 175% text setting.
        tab_font = round(21 * scale)
        x = 48
        for index, title in enumerate(snapshot.categories):
            width = r.text.measure(title, tab_font) + 38
            selected = index == snapshot.category
            r._round_rect(x, 91, width, tab_font + 30,
                          TILE_FOCUSED if selected else TILE_BACKGROUND,
                          radius=FOCUS_RADIUS)
            r._label(title, x + 19, 103, 21, white if selected else muted,
                     width - 28, scale)
            if selected:
                r._rect(x + 18, 91 + tab_font + 24, width - 36, 3, focus)
            x += width + 12

        title_y = 91 + tab_font + 62
        r._label(snapshot.title, 48, title_y, 29, white, 1020, scale)
        selected = snapshot.selected_item
        subtitle = snapshot.breadcrumb.replace(" / ", "  ›  ")
        if selected and selected.kind == "game":
            system = selected.system_label or selected.system_id
            subtitle = "  ·  ".join(text for text in (system, selected.subtitle) if text)
        r._label(subtitle, 49, title_y + round(29 * scale) + 12,
                 17, muted, 1180, scale)

        top = title_y + round(29 * scale) + round(17 * scale) + 42
        footer_top = 620 if scale > 1.2 else 660
        bottom = footer_top - (round(18 * scale) + 22 if snapshot.status or snapshot.loading else 16)
        if not snapshot.items:
            r._paragraph(snapshot.empty_message, 49, top + 20, 23,
                         white, 1130, 4, scale)
            return

        # Title capacity grows horizontally for accessibility instead of
        # shrinking type. Only visible covers reach the bounded art decoder.
        tile_width = round(TILE_WIDTH * (1.45 + .45 * max(0, scale - 1)))
        gap = 18
        stride = tile_width + gap
        visible = max(1, (1184 + gap) // stride)
        # Keep one spare slot at the leading scroll boundary so a newly
        # focused tile is already wholly visible during the short glide.
        target = min(max(0, len(snapshot.items) - visible),
                     max(0, snapshot.selected - visible + 2))
        identity = (snapshot.category, snapshot.title, snapshot.breadcrumb,
                    snapshot.offset, tuple(item.id for item in snapshot.items))
        position = self.scroll.position(target, now, identity, prefs.motion)
        title_font = round(20 * scale)
        title_height = 2 * (title_font + 5) + 18
        cover_height = max(72, min(round(ART_HEIGHT * 1.18), bottom - top - title_height))
        height = cover_height + title_height
        clip = sdl2.SDL_Rect(40, round(top - 7), 1200, max(1, round(bottom - top + 9)))
        sdl2.SDL_RenderSetClipRect(r.renderer, ctypes.byref(clip))
        try:
            # Bounded arithmetic rather than scanning the complete library.
            first = max(0, math.floor(position) - 1)
            last = min(len(snapshot.items), math.ceil(position) + visible + 2)
            for index in range(first, last):
                item = snapshot.items[index]
                x = round(48 + (index - position) * stride)
                active = index == snapshot.selected
                r._round_rect(x, top, tile_width, height,
                              TILE_FOCUSED if active else TILE_BACKGROUND,
                              radius=FOCUS_RADIUS)
                if item.kind == "game":
                    r._artwork(item, x + 6, round(top + 6), tile_width - 12,
                               cover_height - 12, prefs)
                else:
                    icon = min(108, cover_height - 28)
                    r._icon(r._item_icon(item), x + (tile_width - icon) / 2,
                            top + (cover_height - icon) / 2, icon, white)
                r._paragraph(item.title, x + 12, top + cover_height + 4,
                             20, white if active else muted, tile_width - 24, 2, scale)
                if active:
                    self._border(x - 4, top - 4, tile_width + 8, height + 8,
                                 focus, max(3, round(FOCUS_BORDER_WIDTH)))
                if item.favorite:
                    r._icon("favorites", x + tile_width - 33, top + 10, 23, white)
        finally:
            sdl2.SDL_RenderSetClipRect(r.renderer, None)

    def _border(self, x, y, width, height, color, thickness):
        r = self.renderer
        r._rect(x, y, width, thickness, color)
        r._rect(x, y + height - thickness, width, thickness, color)
        r._rect(x, y, thickness, height, color)
        r._rect(x + width - thickness, y, thickness, height, color)
