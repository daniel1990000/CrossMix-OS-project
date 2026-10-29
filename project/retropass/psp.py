"""RetroPass's artwork and recent-five landing presentation inside PSP XMB.

Derived from MainPage.xaml, Game.cs and Playlist.cs at the upstream identity
recorded in NOTICE.txt. This adaptation retains the existing PSP waves,
crossbar, vertical navigation and renderer instead of adding a second owner.
SPDX-License-Identifier: GPL-2.0-only
"""
from __future__ import annotations

from .layout import ART_HEIGHT, LANDING_LIMIT, TILE_WIDTH
from .library import landing_items


class PSPRetroPassView:
    """A read-only detail/landing preview beside the native XMB item column."""

    def __init__(self, renderer):
        self.renderer = renderer

    def visible(self, snapshot):
        if snapshot.preferences.text_scale > 1.2 or snapshot.dialog or snapshot.keyboard:
            return False
        selected = snapshot.selected_item
        if selected and selected.kind == "game":
            # A full selected title outranks the optional cover panel. Keep
            # the existing two-line full-width treatment for longer names.
            width = 460 if selected.favorite else 500
            pixels = round(31 * snapshot.preferences.text_scale)
            if len(self.renderer.text.wrap(selected.title, pixels, width, 128)) > 2:
                return False
            return True
        return bool(getattr(snapshot, "landing_items", ()))

    def draw(self, snapshot, now, primary, muted):
        if not self.visible(snapshot):
            return
        r, prefs = self.renderer, snapshot.preferences
        scale = prefs.text_scale
        selected = snapshot.selected_item
        # Keep the PSP background visible: source Uniform artwork fit and a
        # restrained white focus treatment replace Xbox's dark card and green.
        r._line(920, 297, 920, 618, (*primary[:3], 38))
        if selected and selected.kind == "game":
            self._game(snapshot, selected, primary, muted)
            return
        supplied = getattr(snapshot, "landing_items", ())
        # Reuse the actual Playlist.cs translation; IDs keep duplicate display
        # titles distinct. This never changes the interactive snapshot order.
        picks = landing_items(supplied, (item.id for item in supplied), LANDING_LIMIT)
        r._text("Quick picks", 948, 292, 21, primary, 266, scale)
        height = 47
        width = round(height * TILE_WIDTH / ART_HEIGHT)
        for index, item in enumerate(picks):
            y = 332 + index * 55
            r._artwork(item, 949, y, width, height, prefs)
            r._paragraph(item.title, 994, y + 1, 15, primary, 221, 2, scale)
        if not picks:
            r._paragraph("Your library picks appear here.", 948, 341, 17,
                         muted, 266, 3, scale)

    def _game(self, snapshot, item, primary, muted):
        r, prefs = self.renderer, snapshot.preferences
        scale = prefs.text_scale
        system = item.system_label or item.system_id
        r._text(system or "Game", 948, 292, 19, muted, 267, scale)
        bottom = 660 - (round(18 * scale) + 24 if snapshot.status or snapshot.loading else 20)
        # Geometry comes from RetroPass's 136x210 template, then uses Uniform
        # fitting so landscape artwork is never stretched into a portrait box.
        title_height = 2 * (round(18 * scale) + 7)
        art_height = min(ART_HEIGHT + 24, bottom - 329 - title_height - 19)
        art_width = round(art_height * TILE_WIDTH / ART_HEIGHT)
        x = 948 + (267 - art_width) // 2
        r._artwork(item, x, 329, art_width, art_height, prefs)
        # No animated blur or unbounded texture: a few white lines are enough
        # to emphasize the focused image alongside the XMB scale transition.
        r._line(x - 4, 325, x + art_width + 4, 325, (*primary[:3], 72))
        r._line(x - 4, 329 + art_height + 4, x + art_width + 4,
                329 + art_height + 4, (*primary[:3], 44))
        r._paragraph(item.title, 948, 329 + art_height + 15,
                     18, primary, 267, 2, scale)
