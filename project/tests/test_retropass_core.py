# SPDX-License-Identifier: GPL-2.0-only
"""RetroPass port identity, datasource mapping and bounded metadata checks."""
from dataclasses import dataclass
from pathlib import Path
import tempfile
import unittest

from retropass.library import core_name, landing_items, parse_gamelist, parse_systems


@dataclass(frozen=True)
class Item:
    id: str
    title: str = "Same title"


class RetroPassPlaylistTests(unittest.TestCase):
    def test_recent_first_fallback_and_same_title_identity(self):
        items = tuple(Item(str(i)) for i in range(7))
        actual = landing_items(items, ["stale", "6", "6", "2"])
        self.assertEqual([item.id for item in actual], ["6", "2", "0", "1", "3"])
        self.assertIs(actual[0], items[6])

    def test_duplicate_fallbacks_do_not_shorten_row(self):
        values = [{"game_id": str(i)} for i in range(5)]
        self.assertEqual(len(landing_items([values[0]] * 5 + values, [])), 5)

    def test_empty_and_invalid_limit(self):
        self.assertEqual(landing_items([], []), ())
        self.assertEqual(landing_items([Item("a")], [], 0), ())
        for value in (-1, True, 0.5):
            with self.assertRaises(ValueError):
                landing_items([], [], value)


class RetroPassESTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.system = self.base / "snes"
        self.system.mkdir()
        self.path = self.system / "gamelist.xml"

    def write(self, content):
        self.path.write_text(content, encoding="utf-8")

    def test_systems_and_linux_or_windows_core_names(self):
        self.write('<systemList><system><name>snes</name><fullname>Super Nintendo</fullname>'
                   '<path>./snes</path><command>retroarch -L /cores/snes9x_libretro.so %ROM%</command>'
                   '</system></systemList>')
        value, = parse_systems(self.path)
        self.assertEqual(value.fullname, "Super Nintendo")
        self.assertEqual(value.core_name, "snes9x_libretro.so")
        self.assertEqual(core_name(r'retroarch -L "D:\cores\snes9x_libretro.dll" %ROM%'), "snes9x_libretro.dll")
        self.assertEqual(core_name("/usr/bin/ppsspp %ROM%"), "")

    def test_game_metadata_preference_sort_and_deduplication(self):
        self.write('''<gameList><folder><path>./folder</path></folder>
          <game><path>./b.sfc</path><name>Zed</name><image>./media/b.png</image></game>
          <game><path>.\\a.sfc</path><name>A &amp; B</name><thumbnail>./media/thumb.png</thumbnail>
          <image>./media/screen.png</image><video>./media/video.mp4</video><desc>Description</desc>
          <developer>Maker</developer><publisher>Press</publisher><genre>Action</genre>
          <releasedate>19920101T000000</releasedate></game>
          <game><path>./a.sfc</path><name>Duplicate</name></game><game><name>No path</name></game>
          </gameList>''')
        a, b = parse_gamelist(self.path, command="retroarch -L /cores/snes9x_libretro.so %ROM%")
        self.assertEqual(a.title, "A & B")
        self.assertEqual(a.path, str(self.system / "a.sfc"))
        self.assertEqual(a.artwork, str(self.system / "media/thumb.png"))
        self.assertEqual(b.artwork, str(self.system / "media/b.png"))
        self.assertEqual(a.developer, "Maker")
        self.assertEqual(a.to_record()["game_id"], a.id)
        self.assertEqual(a.core_name, "snes9x_libretro.so")
        self.assertNotEqual(a.id, b.id)

    def test_identity_survives_mount_location_and_title_change(self):
        self.write('<gameList><game><path>./a.sfc</path><name>Before</name></game></gameList>')
        before, = parse_gamelist(self.path)
        other = self.base / "different-mount" / "snes"
        other.mkdir(parents=True)
        copy = other / "gamelist.xml"
        copy.write_text('<gameList><game><path>./a.sfc</path><name>After</name></game></gameList>')
        after, = parse_gamelist(copy)
        self.assertEqual(before.id, after.id)

    def test_root_contains_roms_and_artwork(self):
        for value in ("../outside.sfc", "C:\\Roms\\a.sfc", "/etc/passwd"):
            self.write(f'<gameList><game><path>{value}</path></game></gameList>')
            with self.assertRaises(ValueError):
                parse_gamelist(self.path)
        self.write('<gameList><game><path>./a.sfc</path><image>../outside.png</image></game></gameList>')
        with self.assertRaises(ValueError):
            parse_gamelist(self.path)
        value, = parse_gamelist(self.path, root=self.base)
        self.assertEqual(value.artwork, str(self.base / "outside.png"))

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.system / "linked").symlink_to(outside, target_is_directory=True)
            self.write('<gameList><game><path>./linked/a.sfc</path></game></gameList>')
            with self.assertRaises(ValueError):
                parse_gamelist(self.path)

    def test_xml_validation_and_entities(self):
        for value in ('<wrong/>', '<gameList>',
                      '<!DOCTYPE gameList [<!ENTITY x "expanded">]><gameList/>'):
            self.write(value)
            with self.assertRaises(ValueError):
                parse_gamelist(self.path)
        self.path.write_bytes('<!DOCTYPE gameList><gameList/>'.encode("utf-16"))
        with self.assertRaises(ValueError):
            parse_gamelist(self.path)


if __name__ == "__main__":
    unittest.main()
