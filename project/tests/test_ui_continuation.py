"""Host navigation checks for the continuation of the existing dev14 UI."""
import importlib.util
import os
import unittest
from dataclasses import replace
from unittest import mock

from psp_shell.ui.model import NavigationModel, UICommand, UIItem


def game(identifier="psp:one", system="PSP", **values):
    return {"game_id": identifier, "display_name": "Skyline Circuit", "system_id": system,
            "availability": "available", **values}


def choose(model, label):
    dialog = model.snapshot().dialog
    for _ in range(len(dialog.choices)):
        if model.snapshot().dialog.choices[model.snapshot().dialog.selected].title == label:
            return model.handle("confirm")
        model.handle("down")
    raise AssertionError("Missing choice: " + label)


def receive(model, context, result, method="fixture", params=None):
    request = model._request(method, params, context)
    return model.receive(request, result)


class CombinedFilterTests(unittest.TestCase):
    def test_selected_system_stays_with_search_and_pagination(self):
        model = NavigationModel()
        receive(model, "systems", [{"system_id": "PSP", "label": "PSP", "game_count": 80}])
        for _ in range(4):
            model.handle("down")
        query = model.handle("confirm")[0]
        model.receive(query, {"items": [game(str(n)) for n in range(40)], "offset": 0, "total": 80})
        model.handle("search")
        model.handle("text", "Circuit")
        search = model.handle("submit_text")[0]
        self.assertEqual(search.params, {"offset": 0, "limit": 40, "system_id": "PSP", "search": "Circuit"})
        model.receive(search, {"items": [game(str(n)) for n in range(40)], "offset": 0, "total": 80})
        for _ in range(40):
            commands = model.handle("down")
        self.assertEqual(commands[0].params, {"offset": 40, "limit": 40, "system_id": "PSP", "search": "Circuit"})
        self.assertIn("PSP", model.snapshot().breadcrumb)
        self.assertIn("Circuit", model.snapshot().breadcrumb)

    def test_favorites_and_recent_filters_are_independent_and_reject_stale_reply(self):
        model = NavigationModel()
        receive(model, "systems", [{"system_id": "PSP", "label": "PSP"}, {"system_id": "PS", "label": "PS1"}])
        model.handle("down")
        initial = model.handle("confirm")[0]
        model.receive(initial, [game()])
        model.handle("menu")
        choose(model, "System: All systems")
        psp = choose(model, "PSP")[0]
        self.assertEqual(psp.method, "library.favorites")
        self.assertEqual(psp.params, {"system_id": "PSP"})
        model.handle("menu")
        choose(model, "System: PSP")
        ps1 = choose(model, "PS1")[0]
        self.assertEqual(ps1.params, {"system_id": "PS"})
        model.receive(ps1, [game("ps:one", "PS")])
        model.receive(psp, [game("stale")])
        self.assertEqual(model.snapshot().selected_item.id, "ps:one")
        model.handle("right")
        model.handle("menu")
        choose(model, "System: All systems")
        recent = choose(model, "PSP")[0]
        self.assertEqual(recent.method, "library.recent")
        self.assertEqual(recent.params, {"system_id": "PSP"})
        self.assertEqual(model.export_state()["history_filters"], {"favorites": "PS", "recent": "PSP"})

    def test_history_pagination_and_favorite_removal_keep_game_identity(self):
        model = NavigationModel()
        model.handle("down")
        request = model.handle("confirm")[0]
        records = [game(str(n)) for n in range(85)]
        model.receive(request, records)
        self.assertEqual(model.snapshot().total, 85)
        self.assertEqual(len(model.snapshot().items), model.PAGE_SIZE)
        for _ in range(40):
            self.assertEqual(model.handle("down"), [])
        self.assertEqual(model.snapshot().offset, 40)
        self.assertEqual(model.snapshot().selected_item.id, "40")
        removal = model.handle("favorite")[0]
        refresh = model.receive(removal, {})[0]
        model.receive(refresh, records[:40] + records[41:])
        self.assertEqual(model.snapshot().selected_item.id, "41")
        model.handle("up")
        self.assertEqual(model.snapshot().offset, 0)
        self.assertEqual(model.snapshot().selected_item.id, "39")

    def test_refresh_preserves_history_focus_across_page_boundary(self):
        model = NavigationModel()
        model.handle("down")
        request = model.handle("confirm")[0]
        records = [game(str(n)) for n in range(85)]
        model.receive(request, records)
        for _ in range(40):
            model.handle("down")
        self.assertEqual(model.snapshot().selected_item.id, "40")
        refresh = model._history_query("favorites")
        model.receive(refresh, records[1:])
        self.assertEqual(model.snapshot().selected_item.id, "40")
        self.assertEqual(model.snapshot().offset, 0)
        self.assertEqual(model.snapshot().selected, 39)

    def test_pending_game_query_cannot_populate_favorites(self):
        model = NavigationModel()
        old_games = model.handle("confirm")[0]
        model.handle("back")
        model.handle("down")
        favorites = model.handle("confirm")[0]
        self.assertEqual(model.snapshot().title, "Favorites")
        model.receive(old_games, {"items": [game("not-a-favorite")], "offset": 0, "total": 1})
        self.assertEqual(model.snapshot().items, ())
        model.receive(favorites, [game("favorite")])
        self.assertEqual(model.snapshot().selected_item.id, "favorite")

    def test_pending_favorites_reply_cannot_populate_all_games(self):
        model = NavigationModel()
        model.handle("down")
        old_favorites = model.handle("confirm")[0]
        model.handle("back")
        model.handle("up")
        games = model.handle("confirm")[0]
        self.assertEqual(model.snapshot().title, "All games")
        model.receive(old_favorites, [game("favorite")])
        self.assertEqual(model.snapshot().items, ())
        model.receive(games, {"items": [game("ordinary")], "offset": 0, "total": 1})
        self.assertEqual(model.snapshot().selected_item.id, "ordinary")
        # The response still updates favorite badges while its old view is closed.
        model.set_category_items(1, [game("favorite")])
        model.handle("right")
        self.assertTrue(model.snapshot().selected_item.favorite)

    def test_restore_retains_filters_and_current_system_search(self):
        state = {"schema": 1, "games_view": "search", "system_id": "PSP", "system_label": "PSP", "search": "Circuit",
                 "history_filters": {"recent": "PS", "favorites": "PSP"}}
        model = NavigationModel(restored_state=state)
        requests = model.initial_commands()
        self.assertEqual(next(c for c in requests if c.method == "library.recent").params, {"system_id": "PS"})
        self.assertEqual(next(c for c in requests if c.method == "library.query").params["system_id"], "PSP")
        self.assertEqual(model.export_state()["history_filters"], state["history_filters"])


class InformationAndStatusTests(unittest.TestCase):
    def test_explicit_readonly_capability_hides_launch_in_confirmation_and_information(self):
        for resume in (False, True):
            for surface in ("confirmation", "information"):
                with self.subTest(resume=resume, surface=surface):
                    model = NavigationModel()
                    receive(model, "capabilities", {"game_information": True, "game_launch": False, "game_options": True})
                    record = game("psp:actual-image", resume_available=resume)
                    model.set_category_items(0, [record])
                    model.handle("confirm")
                    if surface == "information":
                        request = choose(model, "Game information")[0]
                        model.receive(request, record)
                    dialog = model.snapshot().dialog
                    self.assertFalse(any(choice.method == "game.launch" for choice in dialog.choices))
                    self.assertIn("Game launch is unavailable in this view", dialog.message)
                    self.assertNotIn("Resume available for this boot", dialog.message)
                    self.assertTrue(any(choice.method == "game.options" for choice in dialog.choices))

    def test_live_launch_and_demo_choices_survive_readonly_presentation_guard(self):
        for demo, allowed in ((False, True), (True, False)):
            with self.subTest(demo=demo, allowed=allowed):
                model = NavigationModel(demo=demo)
                receive(model, "capabilities", {"game_information": True, "game_launch": allowed})
                record = game(resume_available=True)
                model.set_category_items(0, [record])
                model.handle("confirm")
                self.assertEqual([choice.title for choice in model.snapshot().dialog.choices
                                  if choice.method == "game.launch"], ["Resume", "Fresh start"])
                request = choose(model, "Game information")[0]
                model.receive(request, record)
                self.assertEqual([choice.title for choice in model.snapshot().dialog.choices
                                  if choice.method == "game.launch"], ["Resume", "Fresh start"])

    def test_info_panel_preserves_launch_and_native_routes_with_disc_warnings(self):
        model = NavigationModel()
        receive(model, "capabilities", {"game_information": True, "game_options": True})
        record = game("ps:multi", "PS", artwork="art/missing.png", selected_emulator="PCSX ReARMed", selected_preset="Current PS1")
        model.set_category_items(0, [record])
        model.handle("confirm")
        request = choose(model, "Game information")[0]
        self.assertEqual(request.params, {"game_id": "ps:multi"})
        model.receive(request, {**record, "system_label": "PlayStation", "disc_set": {"kind": "playlist", "disc_count": 2,
            "discs": [{"label": "Disc 1.chd", "available": True}, {"label": "Disc 2.chd", "available": False}],
            "warnings": ["MISSING_DISC"]}, "disc_management": {"description": "Change discs in the current emulator's in-game menu."}})
        dialog = model.snapshot().dialog
        self.assertIn("System: PlayStation", dialog.message)
        self.assertIn("Emulator: PCSX ReARMed", dialog.message)
        self.assertIn("Preset: Current PS1", dialog.message)
        self.assertIn("Disc 2: Disc 2.chd · missing", dialog.message)
        self.assertIn("A referenced disc file is missing", dialog.message)
        self.assertNotIn("MISSING_DISC", dialog.message)
        self.assertEqual(dialog.artwork, "art/missing.png")
        request = choose(model, "Existing emulator options")[0]
        self.assertEqual(request.method, "game.options")
        self.assertEqual(request.params, {"game_id": "ps:multi"})

    def test_continue_distinguishes_recent_and_verified_resume_with_reason(self):
        model = NavigationModel()
        model.set_category_items(1, [game(resume_available=False, resume_reason="The checkpoint belongs to a previous boot.")])
        model.handle("right")
        self.assertIn("Recently played", model.snapshot().selected_item.subtitle)
        model.handle("confirm")
        self.assertIn("Resume unavailable", model.snapshot().dialog.message)
        self.assertIn("previous boot", model.snapshot().dialog.message)
        self.assertNotIn("Resume", [c.title for c in model.snapshot().dialog.choices])
        model.handle("back")
        model.set_category_items(1, [game(resume_available=True, state_recorded_at="2026-10-23T00:01:02Z")])
        self.assertIn("Resume available", model.snapshot().selected_item.subtitle)
        model.handle("confirm")
        self.assertIn("Checkpoint verified 2026-10-23 00:01:02 UTC", model.snapshot().dialog.message)
        self.assertNotIn("saved 2026", model.snapshot().dialog.message)

    def test_backup_status_never_turns_partial_or_unknown_into_full_recovery(self):
        model = NavigationModel()
        receive(model, "backup_status", {"status": "unavailable", "verified_at_utc": None,
            "reason": "No trusted backup mapping is configured.", "supported_actions": [
                {"id": "restore_live_card", "label": "Unsafe arbitrary route", "available": True},
                {"id": "recovery_guide", "label": "Recovery instructions", "available": True}]})
        dialog = model.snapshot().dialog
        self.assertIn("Verified backup unavailable", dialog.message)
        self.assertNotIn("readback verified", dialog.message)
        self.assertEqual([c.title for c in dialog.choices], ["Recovery instructions", "Back"])
        request = choose(model, "Recovery instructions")[0]
        self.assertEqual(request.method, "backup.action")
        self.assertEqual(request.params, {"action_id": "recovery_guide"})
        model.receive(request, {"message": "Restore only into new expendable media using the existing tool."})
        self.assertIn("expendable", model.snapshot().dialog.message)
        receive(model, "backup_status", {"status": "partial", "verified_at_utc": "2026-10-23T00:01:02Z", "scope": ["saves"], "reason": "Card backup unavailable.",
            "readbacks": [{"scope": "saves", "status": "verified"}, {"scope": "card-files", "status": "unavailable"}]})
        self.assertIn("Some backup scopes verified", model.snapshot().dialog.message)
        self.assertIn("Saves: backup bytes verified", model.snapshot().dialog.message)
        self.assertIn("Card files: backup unavailable", model.snapshot().dialog.message)
        self.assertIn("physical restoration", model.snapshot().dialog.message)

    def test_performance_preview_is_explicit_and_undo_is_scoped_to_that_game(self):
        model = NavigationModel()
        status = {"game_id": "psp:one", "generation": 4, "writable": True, "options": [
            {"id": "resolution", "label": "Rendering resolution", "value": None, "description": "Lower resolution reduces image detail.",
             "choices": [{"value": None, "label": "Use current global setting"}, {"value": 1, "label": "1×", "description": "Lower image detail."}]}]}
        receive(model, "performance_status", status)
        choose(model, "Rendering resolution")
        self.assertIn("untested", model.snapshot().dialog.message)
        preview = choose(model, "1×")[0]
        self.assertEqual(preview.params, {"game_id": "psp:one", "changes": {"resolution": 1}, "expected_generation": 4})
        model.receive(preview, {"preview_id": "p", "diff": [{"option_id": "resolution", "before": None, "after": 1}]})
        self.assertEqual(model.snapshot().dialog.selected, 1)
        apply = choose(model, "Apply per-game change")[0]
        self.assertEqual(apply.method, "performance.apply")
        refresh = model.receive(apply, {"applied": True, "transaction_id": "t", "generation": 5, "game_id": "psp:one"})[0]
        model.receive(refresh, {**status, "generation": 5})
        self.assertIn("Undo last performance change", [c.title for c in model.snapshot().dialog.choices])
        receive(model, "performance_status", {**status, "game_id": "psp:other"})
        self.assertNotIn("Undo last performance change", [c.title for c in model.snapshot().dialog.choices])


    def test_performance_display_distinguishes_local_inherited_and_unavailable(self):
        model = NavigationModel()
        status = {"game_id": "psp:one", "generation": 2, "writable": True, "options": [
            {"id": "resolution", "label": "Rendering resolution", "value": 2, "inherited": False, "value_available": True,
             "choices": [{"value": 2, "label": "2x PSP"}]},
            {"id": "frameskip", "label": "Manual frameskip", "value": None, "inherited": True,
             "value_available": True, "effective_value": 0, "choices": [{"value": 0, "label": "Off"}]},
            {"id": "auto_frameskip", "label": "Automatic frameskip", "value": None, "inherited": True,
             "value_available": False, "effective_value": None}]}
        receive(model, "performance_status", status)
        message = model.snapshot().dialog.message
        self.assertIn("Rendering resolution: Local: 2x PSP", message)
        self.assertIn("Manual frameskip: Inherited: Off (current global)", message)
        self.assertIn("Automatic frameskip: Unavailable", message)
        receive(model, "performance_status", {**status, "writable": False,
            "options": [{**option, "value_available": False, "inherited": None} for option in status["options"]]})
        self.assertIn("Rendering resolution: Unavailable", model.snapshot().dialog.message)
        self.assertEqual([choice.title for choice in model.snapshot().dialog.choices], ["Back"])

    def test_native_return_refreshes_authority_without_reopening_stale_dialog_or_losing_undo(self):
        model = NavigationModel()
        status = {"game_id": "psp:one", "generation": 4, "writable": True, "options": [
            {"id": "frameskip", "label": "Manual frameskip", "value": None, "inherited": True,
             "effective_value": 0, "value_available": True,
             "choices": [{"value": None, "label": "Use current global setting"}, {"value": 0, "label": "Off"}]}]}
        receive(model, "performance_status", status)
        model._performance_transaction = "owned-transaction"
        model._performance_transaction_game = "psp:one"
        choose(model, "Manual frameskip")
        old_preview = choose(model, "Use current global setting")[0]
        commands = model.refresh_commands()
        refresh = next(command for command in commands if command.method == "performance.status")
        self.assertEqual(refresh.params, {"game_id": "psp:one"})
        self.assertIsNone(model.snapshot().dialog)
        model.receive(old_preview, {"preview_id": "stale", "diff": []})
        self.assertIsNone(model.snapshot().dialog)
        local = {**status, "options": [{**status["options"][0], "value": 0, "inherited": False}]}
        model.receive(refresh, local)
        self.assertIsNone(model.snapshot().dialog)
        self.assertFalse(model._performance_status["options"][0]["inherited"])
        receive(model, "performance_status", local)
        self.assertIn("Manual frameskip: Local: Off", model.snapshot().dialog.message)
        self.assertIn("Undo last performance change", [choice.title for choice in model.snapshot().dialog.choices])

    def test_failed_native_settings_refresh_clears_stale_values_without_opening_a_dialog(self):
        model = NavigationModel()
        receive(model, "performance_status", {"game_id": "psp:one", "writable": True,
            "options": [{"id": "frameskip", "value": None, "effective_value": 0, "inherited": True}]})
        refresh = next(command for command in model.refresh_commands() if command.method == "performance.status")
        model.error(refresh, "BUSY_WRITER", "Native settings writer is still active")
        self.assertEqual(model._performance_status, {})
        self.assertIsNone(model.snapshot().dialog)
        self.assertIn("refresh unavailable", model.snapshot().status)

    def test_older_native_refresh_cannot_replace_newer_performance_read(self):
        model = NavigationModel()
        receive(model, "performance_status", {"game_id": "psp:one", "writable": False})
        cached = next(command for command in model.refresh_commands() if command.method == "performance.status")
        receive(model, "performance_status", {"game_id": "psp:two", "generation": 7, "writable": False})
        model.receive(cached, {"game_id": "psp:one", "generation": 0, "writable": False})
        self.assertEqual(model._performance_status["game_id"], "psp:two")
        self.assertEqual(model._performance_generation, 7)


@unittest.skipUnless(importlib.util.find_spec("sdl2") and importlib.util.find_spec("PIL"), "Install host SDL/Pillow dependencies")
class ContinuationRenderTests(unittest.TestCase):
    def test_large_text_info_scrolls_every_action_and_keeps_art_placeholder(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        from psp_shell.ui.model import Dialog, DialogChoice
        from psp_shell.ui.renderer import Renderer
        model = NavigationModel(preferences={"motion": False, "text_scale": 1.75})
        choices = tuple(DialogChoice(label) for label in ("Resume", "Fresh start", "Performance options", "Existing emulator options", "Back"))
        title = "A very long game title " * 18
        dialog = Dialog(title, "System: PSP\nEmulator: PPSSPP\nPreset: Current selection\nAvailability: available", choices,
                        selected=4, artwork="missing-art.png", system_id="PSP")
        drawn = []
        with Renderer(software=True) as renderer:
            label = renderer._label
            artwork = renderer._artwork
            def record(text, x, y, size, color, max_width, scale=1):
                result = label(text, x, y, size, color, max_width, scale)
                drawn.append((text, y, result[1]))
                return result
            with mock.patch.object(renderer, "_label", side_effect=record), mock.patch.object(renderer, "_artwork", wraps=artwork) as art:
                renderer.render(replace(model.snapshot(), dialog=dialog), 0)
                self.assertTrue(any(row[0] == "Back" for row in drawn))
                self.assertFalse(any(row[0] == "Resume" for row in drawn))
                self.assertTrue(art.called)
                self.assertEqual(art.call_args.args[0].artwork, "missing-art.png")
                self.assertTrue(any(row[0].startswith("More text") for row in drawn))
                drawn.clear()
                renderer.render(replace(model.snapshot(), dialog=replace(dialog, selected=0)), 0)
                self.assertTrue(any(row[0] == "Resume" for row in drawn))
                self.assertTrue(all(0 <= y < 720 and y + height <= 720 for _, y, height in drawn))


if __name__ == "__main__":
    unittest.main()
