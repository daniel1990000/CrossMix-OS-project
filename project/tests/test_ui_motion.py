"""Selection must settle promptly across repeats, jumps and reduced motion."""
from dataclasses import replace
import importlib.util
import unittest
from unittest import mock

from psp_shell.ui.motion import StepGlide
from psp_shell.ui.model import NavigationModel, UIItem


class CrossbarMotionTests(unittest.TestCase):
    def test_step_is_frame_rate_independent_and_finishes_in_one_tenth_second(self):
        a, b = StepGlide(), StepGlide()
        for glide in (a, b):
            self.assertEqual(glide.position(0, 0, "games", True), 0)
            self.assertEqual(glide.position(1, 1, "games", True), 0)
        for now in (1.01, 1.025, 1.04):
            a.position(1, now, "games", True)
        self.assertAlmostEqual(a.position(1, 1.05, "games", True), .5)
        self.assertAlmostEqual(b.position(1, 1.05, "games", True), .5)
        self.assertEqual(a.position(1, 1.2, "games", True), 1)

    def test_long_jump_only_animates_last_row_and_view_change_snaps(self):
        glide = StepGlide()
        glide.position(0, 0, "games", True)
        self.assertEqual(glide.position(39, 1, "games", True), 38)
        self.assertEqual(glide.position(39, 1.2, "games", True), 39)
        self.assertEqual(glide.position(3, 1.21, "settings", True), 3)

    def test_held_repeat_catches_up_and_reduced_motion_stops_immediately(self):
        glide = StepGlide()
        glide.position(0, 0, "games", True)
        for index in range(1, 12):
            glide.position(index, index * .025, "games", True)
            self.assertLessEqual(glide.duration, .2)
        self.assertEqual(glide.position(11, .5, "games", True), 11)
        self.assertEqual(glide.position(12, .51, "games", False), 12)
        self.assertEqual(glide.position(12, 9, "games", False), 12)


@unittest.skipUnless(importlib.util.find_spec("sdl2") is not None,
                     "Install the optional host PySDL2 dependency")
class ListReplacementMotionTests(unittest.TestCase):
    """A newly published library page must not glide as the old page's rows."""

    def setUp(self):
        from psp_shell.ui.renderer import Renderer

        # Exercise the actual row layout and its persistent motion state while
        # recording draw calls. No window, font, artwork decoder or GPU is used.
        self.renderer = Renderer.__new__(Renderer)
        self.renderer.renderer = None
        self.renderer._item_glide = StepGlide()
        self.renderer._artwork = mock.Mock()
        self.renderer._icon = mock.Mock()
        self.renderer._polyline = mock.Mock()
        self.renderer._text = mock.Mock(return_value=(100, 31))
        self.renderer.text = mock.Mock()
        self.renderer.text.wrap.side_effect = lambda text, *_: (text,)
        clipping = mock.patch("psp_shell.ui.renderer.sdl2.SDL_RenderSetClipRect")
        clipping.start()
        self.addCleanup(clipping.stop)
        self.base = replace(NavigationModel(preferences={"motion": True}).snapshot(),
                            title="All games", breadcrumb="Games / All games", total=80)

    def page(self, first, selected, *, offset=None):
        return replace(self.base,
                       items=tuple(UIItem(f"game:{i}", f"Game {i}")
                                   for i in range(first, first + 40)),
                       selected=selected, offset=first if offset is None else offset)

    def draw(self, snapshot, now):
        self.renderer._artwork.reset_mock()
        self.renderer._text.reset_mock()
        self.renderer._items(snapshot, now, (255, 255, 255), (222, 238, 251))
        selected = snapshot.selected_item
        cover = next(call.args for call in self.renderer._artwork.call_args_list
                     if call.args[0].id == selected.id)
        title = next(call.args for call in self.renderer._text.call_args_list
                     if call.args[0] == selected.title)
        return cover[2] + cover[4] / 2, title[2]

    def assert_at_anchor(self, snapshot, now):
        cover_y, title_y = self.draw(snapshot, now)
        self.assertAlmostEqual(cover_y, 368, delta=.5)
        self.assertEqual(title_y, 344)

    def test_next_page_lands_first_row_without_a_reverse_glide(self):
        self.draw(self.page(0, 39), 0)
        self.assert_at_anchor(self.page(40, 0), 1)

    def test_previous_page_lands_last_row_without_a_forward_glide(self):
        self.draw(self.page(40, 0), 0)
        self.assert_at_anchor(self.page(0, 39), 1)

    def test_same_offset_replacement_and_reorder_land_on_the_new_focus(self):
        for replacement in ("different games", "same games reordered"):
            with self.subTest(replacement=replacement):
                previous = self.page(0, 30)
                self.draw(previous, 0)
                if replacement == "different games":
                    current = self.page(100, 1, offset=0)
                else:
                    rows = list(previous.items)
                    rows.insert(1, rows.pop(30))
                    current = replace(previous, items=tuple(rows), selected=1)
                self.assert_at_anchor(current, 1)

    def test_subtitle_and_favorite_updates_preserve_an_in_progress_step(self):
        previous = self.page(0, 0)
        self.draw(previous, 0)
        current = replace(previous, selected=1)
        before, _ = self.draw(current, 1)
        rows = list(current.items)
        rows[1] = replace(rows[1], subtitle="Updated while moving", favorite=True)
        updated = replace(current, items=tuple(rows))
        during, _ = self.draw(updated, 1.05)
        self.assertGreater(before, during)
        self.assertGreater(during, 368)
        self.assert_at_anchor(updated, 1.2)


if __name__ == "__main__":
    unittest.main()
