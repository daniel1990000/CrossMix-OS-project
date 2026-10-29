# SPDX-License-Identifier: MIT
"""RetroPass selection inside the PSP root view preserves native authority."""
import unittest
from unittest.mock import patch

from psp_shell.ui.model import Dialog, DialogChoice, Keyboard, NavigationModel, UIItem
from retropass.library import landing_items


def record(identifier, *, system="GB", title=None, artwork="", favorite=False, available=True):
    return {"game_id": identifier, "display_name": title or identifier,
            "system_id": system, "artwork_ref": artwork,
            "favorite": favorite, "available": available}


class PSPRetroPassLandingTests(unittest.TestCase):
    def model(self, recent=(), favorites=(), games=()):
        model = NavigationModel(preferences={"theme": "psp"})
        commands = model.initial_commands()
        by_context = {command.context: command for command in commands}
        model.receive(by_context["systems"], [{"id": "GB", "label": "Game Boy", "game_count": 10},
                                               {"id": "PSP", "label": "PSP", "game_count": 10}])
        model.receive(by_context["favorites_cache"], favorites)
        model.receive(by_context["recent"], recent)
        if games:
            model._games_view = "all"
            query = model._query()
            model.receive(query, {"items": games, "offset": 0, "total": len(games)})
            model.handle("back")
        return model

    def focus(self, model, identifier):
        model._systems.selected = next(index for index, item in enumerate(model._systems.items)
                                       if item.id == identifier)

    def ids(self, model):
        return tuple(item.id for item in model.snapshot().landing_items)

    def test_actual_port_recent_first_bounded_stable_ids_and_unchanged_navigation(self):
        recents = [record("six", title="Same title"), record("two", title="Same title")]
        games = [record(str(index)) for index in range(10)]
        model = self.model(recents, games=games)
        before = model.export_state()
        pending, serial = set(model._pending), model._serial
        original = model._systems.items
        with patch("retropass.library.landing_items", wraps=landing_items) as actual_port:
            snapshot = model.snapshot()
            actual_port.assert_called_once()
        self.assertEqual(tuple(item.id for item in snapshot.landing_items), ("six", "two", "0", "1", "2"))
        self.assertEqual(snapshot.landing_items[0].title, "Same title")
        self.assertEqual(snapshot.landing_items[1].title, "Same title")
        self.assertTrue(all(not item.id.startswith("retropass-es:") for item in snapshot.landing_items))
        self.assertEqual(before, model.export_state())
        self.assertEqual(pending, model._pending)
        self.assertEqual(serial, model._serial)
        self.assertIs(model._systems.items, original)
        self.assertEqual(snapshot.selected_item.id, "all")

    def test_selected_system_and_favorites_are_scoped_without_moving_root_focus(self):
        model = self.model([record("psp", system="PSP"), record("gb")],
                           [record("favorite", system="PSP"), record("gb")],
                           [record("gb-fallback"), record("other", system="PSP")])
        self.focus(model, "GB")
        self.assertEqual(self.ids(model), ("gb", "gb-fallback"))
        self.focus(model, "favorites")
        self.assertEqual(self.ids(model), ("gb", "favorite"))
        self.assertEqual(model.snapshot().selected_item.id, "favorites")
        mutation = model._request("library.favorite.set", {"game_id": "gb", "enabled": False}, "favorite_set")
        model.receive(mutation, {})
        self.assertEqual(self.ids(model), ("favorite",))
        self.focus(model, "PSP")
        self.assertEqual(self.ids(model)[0], "psp")

    def test_native_recent_order_survives_display_sort_and_letter_jump(self):
        model = self.model()
        model._sorts["recent"] = "title_asc"
        request = model._history_query("recent")
        model.receive(request, [record("last-played", title="Zed"), record("older", title="Alpha")])
        self.assertEqual(tuple(item.id for item in model._history_records["recent"]), ("older", "last-played"))
        self.assertEqual(self.ids(model), ("last-played", "older"))
        model.category = 1
        model._activate_choice(DialogChoice("Jump", "jump", params={"letter": "A"}))
        model.category = 0
        self.assertEqual(self.ids(model), ("last-played", "older"))

    def test_refresh_invalidates_old_art_and_page_before_new_read_or_error(self):
        model = self.model([record("old-recent", artwork="old-recent.png")],
                           games=[record("old-page", artwork="old-page.png")])
        self.assertEqual(self.ids(model), ("old-recent", "old-page"))
        old = model._history_query("recent")
        commands = model.refresh_commands()
        self.assertEqual(self.ids(model), ())
        model.receive(old, [record("stale", artwork="stale.png")])
        self.assertEqual(self.ids(model), ())
        fresh = next(command for command in commands if command.context == "recent")
        model.receive(fresh, [record("new-recent", artwork="new.png")])
        self.assertEqual(self.ids(model), ("new-recent",))
        self.assertEqual(model.snapshot().landing_items[0].artwork, "new.png")
        self.assertNotIn("old-page", self.ids(model))

    def test_favorites_wait_for_fresh_membership_after_refresh(self):
        model = self.model([record("one")], [record("one")])
        self.focus(model, "favorites")
        self.assertEqual(self.ids(model), ("one",))
        commands = model.refresh_commands()
        recent = next(command for command in commands if command.context == "recent")
        model.receive(recent, [record("one", favorite=True)])
        self.assertEqual(self.ids(model), ())
        favorites = next(command for command in commands if command.context == "favorites_cache")
        model.receive(favorites, [])
        self.assertEqual(self.ids(model), ())

    def test_filtered_fresh_favorites_do_not_reuse_old_global_membership(self):
        model = self.model([record("old", system="PSP"), record("fresh")],
                           [record("old", system="PSP"), record("fresh")])
        self.focus(model, "favorites")
        commands = model.refresh_commands()
        recent = next(command for command in commands if command.context == "recent")
        model.receive(recent, [record("old", system="PSP"), record("fresh")])
        model._history_filters["favorites"] = "GB"
        filtered = model._history_query("favorites")
        model.receive(filtered, [record("fresh")])
        self.assertIn("old", model._favorites)
        self.assertEqual(self.ids(model), ("fresh",))

    def test_no_suggestions_for_unrelated_rows_views_modals_or_empty_data(self):
        model = self.model([record("one")])
        for identifier in ("search", "random", "collections", "library_filters", "help", "refresh_library"):
            self.focus(model, identifier)
            self.assertEqual(self.ids(model), (), identifier)
        self.focus(model, "all")
        for category in (1, 2, 3):
            model.category = category
            self.assertEqual(self.ids(model), ())
        model.category = 0
        for view in ("all", "favorites", "search", "system", "collections", "collection"):
            model._games_view = view
            self.assertEqual(self.ids(model), ())
        model._games_view = "systems"
        model._dialog = Dialog("Help", "Text")
        self.assertEqual(self.ids(model), ())
        model._dialog = None
        model._keyboard = Keyboard("Find", 0)
        self.assertEqual(self.ids(model), ())
        self.assertEqual(self.ids(self.model()), ())

    def test_result_cache_avoids_repeat_large_history_iteration(self):
        model = self.model([record(str(index)) for index in range(50000)])

        class CountedTuple(tuple):
            visited = 0

            def __iter__(self):
                for value in super().__iter__():
                    self.visited += 1
                    yield value

        recent = CountedTuple(model._landing_records["recent"])
        model._landing_records["recent"] = recent
        with patch("retropass.library.landing_items", wraps=landing_items) as actual_port:
            first = model.snapshot().landing_items
            visited = recent.visited
            for _ in range(20):
                self.assertIs(model.snapshot().landing_items, first)
            actual_port.assert_called_once()
        self.assertEqual(visited, 5)
        self.assertEqual(recent.visited, visited)

    def test_unavailable_and_duplicate_candidates_do_not_consume_five_slots(self):
        model = self.model([record("bad", available=False), record("same"), record("same"), record("good")])
        self.assertEqual(self.ids(model), ("same", "good"))


if __name__ == "__main__":
    unittest.main()
