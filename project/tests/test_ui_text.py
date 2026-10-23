"""Text wrapping keeps explicit paragraph boundaries and reports truncation."""
# SPDX-License-Identifier: MIT
from collections import OrderedDict
import unittest

from psp_shell.ui.text import TextRasterizer


class MonospaceText(TextRasterizer):
    """Predictable measurements exercise the real shared wrap/fit methods."""
    def __init__(self):
        self._wrap_cache = OrderedDict()

    def measure(self, text, size):
        return len(text) * 10


class TextWrappingTests(unittest.TestCase):
    def setUp(self):
        self.text = MonospaceText()

    def test_repeated_paragraphs_mark_hidden_remainder(self):
        self.assertEqual(self.text.wrap("same\nsame\nsame", 20, 100, 2), ("same", "same…"))
        self.assertEqual(self.text.wrap("same\nsame\nsame\nsame", 20, 100, 2), ("same", "same…"))
        self.assertEqual(self.text.wrap("same\nsame", 20, 100, 2), ("same", "same"))

    def test_empty_paragraphs_preserve_breaks_and_mark_truncation(self):
        self.assertEqual(self.text.wrap("\n", 20, 100, 2), ("", ""))
        self.assertEqual(self.text.wrap("\n\n", 20, 100, 2), ("", "…"))
        self.assertEqual(self.text.wrap("first\n\nlast", 20, 100, 3), ("first", "", "last"))

    def test_word_and_long_token_wraps_stay_inside_width_and_line_budget(self):
        for value in ("one two three four five", "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "日本語" * 6):
            with self.subTest(text=value):
                lines = self.text.wrap(value, 20, 70, 2)
                self.assertEqual(len(lines), 2)
                self.assertTrue(lines[-1].endswith("…"))
                self.assertTrue(all(self.text.measure(line, 20) <= 70 for line in lines))
                self.assertEqual(lines, self.text.wrap(value, 20, 70, 2))


if __name__ == "__main__":
    unittest.main()
