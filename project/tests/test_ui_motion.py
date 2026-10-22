"""Selection must settle promptly across repeats, jumps and reduced motion."""
import unittest

from psp_shell.ui.motion import StepGlide


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


if __name__ == "__main__":
    unittest.main()
