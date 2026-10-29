# SPDX-License-Identifier: MIT
"""The RetroPass datasource port feeds metadata into existing native identities."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from retropass.library import parse_gamelist
from test_spruce_backend import Card


class RetroPassMetadataIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.card = Card(self.temp.name)

    def alpha(self, backend):
        return next(row for row in backend.games("GB")["items"] if row["relative_path"] == "Roms/GB/Alpha.gb")

    def test_port_parser_reads_thumbnail_and_preserves_native_identity_and_launch(self):
        original = self.alpha(self.card.backend())
        self.card.write("Imgs/GB/shared.png", "art fixture")
        self.card.write("Roms/GB/gamelist.xml", '''<gameList><game>
            <path>/mnt/SDCARD/Roms/GB/Alpha.gb</path><name>RetroPass title</name>
            <thumbnail>/mnt/SDCARD/Imgs/GB/shared.png</thumbnail>
            </game><game><path>./missing.gb</path><name>Missing</name></game></gameList>''')
        before = self.card.snapshot()
        with patch("retropass.library.parse_gamelist", wraps=parse_gamelist) as actual_port:
            backend = self.card.backend()
            current = self.alpha(backend)
            actual_port.assert_called_once()
        self.assertEqual(current["id"], original["id"])
        self.assertEqual(current["rom_path"], original["rom_path"])
        self.assertEqual(current["label"], "RetroPass title")
        self.assertEqual(current["artwork"], str(self.card.root / "Imgs/GB/shared.png"))
        self.assertEqual(backend.games("GB")["total"], 2)
        context = backend.resolve_game(current["id"])
        self.assertEqual(context["argv"][1], original["rom_path"])
        self.assertFalse(context["launchable"])
        self.assertEqual(context["gate_reason"], "SNAPSHOT_READ_ONLY")
        self.assertEqual(before, self.card.snapshot())

    def test_thumbnail_falls_back_to_image_and_bad_entry_keeps_valid_metadata(self):
        self.card.write("Imgs/GB/shared.png", "art fixture")
        self.card.write("Roms/GB/gamelist.xml", '''<gameList>
            <game><path>/etc/passwd</path><name>Bad ROM</name></game>
            <game><path>./Alpha.gb</path><name>Valid Alpha</name><thumbnail>/etc/passwd</thumbnail>
            <image>../../Imgs/GB/shared.png</image></game>
            <game><path>./nested/Beta.gbc</path><name>Valid Beta</name><image>/etc/shadow</image></game>
            </gameList>''')
        backend = self.card.backend()
        games = backend.games("GB")["items"]
        self.assertEqual({row["label"] for row in games}, {"Valid Alpha", "Valid Beta"})
        self.assertEqual(self.alpha(backend)["artwork"], str(self.card.root / "Imgs/GB/shared.png"))
        beta = next(row for row in games if row["label"] == "Valid Beta")
        self.assertEqual(beta["artwork"], "")

    def test_first_present_list_precedence_and_missing_title_stays_native_fallback(self):
        self.card.write("Roms/GB/miyoogamelist.xml", '<gameList><game><path>./Alpha.gb</path></game></gameList>')
        self.card.write("Roms/GB/gamelist.xml", '<gameList><game><path>./Alpha.gb</path><name>Other list</name></game></gameList>')
        alpha = self.alpha(self.card.backend())
        self.assertEqual(alpha["label"], "Alpha")
        self.assertFalse(alpha["metadata_label"])
        self.card.write("Roms/GB/miyoogamelist.xml", "<malformed>")
        backend = self.card.backend()
        self.assertEqual(self.alpha(backend)["label"], "Alpha")
        self.assertIn("INVALID_GAMELIST", {warning["code"] for warning in backend.provider.warnings})

    def test_metadata_rom_is_bounded_to_system_folder_and_media_to_card(self):
        self.card.write("Roms/OTHER/Other.gb", "fixture")
        self.card.write("Roms/GB/gamelist.xml", '''<gameList>
            <game><path>../OTHER/Other.gb</path><name>Wrong system</name></game>
            <game><path>./Alpha.gb</path><name>Good</name></game></gameList>''')
        backend = self.card.backend()
        self.assertEqual(self.alpha(backend)["label"], "Good")
        self.assertNotIn(str(self.card.root / "Roms/OTHER/Other.gb"), backend.provider._metadata)
        with tempfile.TemporaryDirectory() as outside:
            (Path(outside) / "cover.png").write_text("fixture")
            (self.card.root / "Roms/GB/escape").symlink_to(outside, target_is_directory=True)
            self.card.write("Roms/GB/gamelist.xml", '''<gameList><game><path>./Alpha.gb</path>
                <name>Good</name><thumbnail>./escape/cover.png</thumbnail></game></gameList>''')
            alpha = self.alpha(self.card.backend())
            self.assertEqual(alpha["label"], "Good")
            self.assertEqual(alpha["artwork"], "")

    def test_existing_byte_and_all_element_budgets_remain_enforced(self):
        self.card.write("Roms/GB/gamelist.xml", "<gameList>" + " " * (2 * 1024 * 1024) + "</gameList>")
        backend = self.card.backend()
        self.assertEqual(self.alpha(backend)["label"], "Alpha")
        self.assertIn("INPUT_TOO_LARGE", {warning["code"] for warning in backend.provider.warnings})
        self.card.write("Roms/GB/gamelist.xml", "<gameList><game><path>./Alpha.gb</path>" +
                        "<unused/>" * 50000 + "</game></gameList>")
        backend = self.card.backend()
        self.assertEqual(self.alpha(backend)["label"], "Alpha")
        self.assertIn("INPUT_TOO_LARGE", {warning["code"] for warning in backend.provider.warnings})


if __name__ == "__main__":
    unittest.main()
