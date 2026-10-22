"""Common appearance UI through real journaled PPSSPP fixture transactions."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from psp_shell.app import AppError, Dispatcher, error_fields
from psp_shell.demo import DemoBackend
from psp_shell.ppsspp import PPSSPPThemeManager, PLATFORM_CONFIG, THEME_DIRECTORY, THEME_FILENAME, THEME_NAMES
from psp_shell.settings import SettingsStore
from psp_shell.ui.model import NavigationModel


PROJECT = Path(__file__).resolve().parents[1]
ORIGINAL = b'[Theme]\nThemeName = "Default" # keep\n[General]\nBackgroundAnimation = 0\n[SystemParam]\nButtonPreference = 1\n'


class AppearanceFlowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.card = self.root / "card"
        self.config = self.card / PLATFORM_CONFIG
        self.config.parent.mkdir(parents=True)
        self.config.write_bytes(ORIGINAL)
        self.binary = self.card / "Emu/PSP/PPSSPPSDL_TrimUI"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b'host fixture, never executed')
        self.gameplay = self.config.with_name("controls-SmartPro.ini")
        self.gameplay.write_bytes(b'[ControlMapping]\nCross = 1-190\nCircle = 1-191\n')
        profile = json.loads((PROJECT / "ppsspp/theme/compatibility-profile.example.json").read_text())
        profile.update(id="host-fixture-appearance", qualified=True, writer_inventory_verified=True,
                       path_contract_verified=True, installed_version=profile["source_version"],
                       executable_sha256=hashlib.sha256(self.binary.read_bytes()).hexdigest())
        self.running = False
        self.manager = PPSSPPThemeManager(self.card, self.root / "theme-state", profile,
            quiescent=lambda: True, process_probe=lambda path: self.running,
            theme_file=PROJECT / "ppsspp/theme/spruce-midnight.ini")
        self.settings = SettingsStore(str(self.root / "preferences"))
        self.dispatcher = Dispatcher(DemoBackend(), self.settings, self.root / "reports", theme_manager=self.manager)
        self.model = NavigationModel(session_id="appearance-fixture")
        self.commands(self.model.initial_commands())
        for _ in range(3):
            self.model.handle("right")

    def commands(self, commands):
        pending = list(commands)
        while pending:
            command = pending.pop(0)
            try:
                pending.extend(self.model.receive(command, self.dispatcher.dispatch(command.method, command.params)))
            except Exception as error:
                self.model.error(command, *error_fields(error))

    def action(self, action):
        self.commands(self.model.handle(action))

    def open_appearance(self):
        while self.model.snapshot().selected_item.id != "appearance":
            self.action("down")
        self.action("confirm")

    def test_match_preferences_preview_apply_and_targeted_undo(self):
        before_preferences = self.settings.get()
        before_gameplay = self.gameplay.read_bytes()
        before_binary = self.binary.read_bytes()
        self.open_appearance()
        self.action("confirm")
        dialog = self.model.snapshot().dialog
        self.assertEqual(dialog.title, "Review PPSSPP appearance")
        self.assertIn(THEME_NAMES[0], dialog.message)
        self.assertIn("Animated waves", dialog.message)
        self.assertEqual(self.config.read_bytes(), ORIGINAL)
        self.action("confirm")
        self.assertIn(b'ThemeName = "Spruce Midnight" # keep', self.config.read_bytes())
        self.assertIn(b'BackgroundAnimation = 3', self.config.read_bytes())
        self.assertEqual(self.model.generation, 0)
        self.config.write_bytes(self.config.read_bytes() + b'[Graphics]\nFrameSkip = 1\n')
        self.action("down")
        self.assertEqual(self.model.snapshot().selected_item.id, "appearance_undo")
        self.action("confirm")
        self.assertEqual(self.config.read_bytes(), ORIGINAL + b'[Graphics]\nFrameSkip = 1\n')
        self.assertEqual(self.gameplay.read_bytes(), before_gameplay)
        self.assertEqual(self.binary.read_bytes(), before_binary)
        self.assertEqual(self.settings.get(), before_preferences)
        self.assertEqual(self.manager.status()["generation"], 2)
        self.action("back")
        self.assertEqual(self.model.snapshot().title, "Make it yours")

    def test_high_contrast_and_motion_preview_follow_current_interface_preferences(self):
        preview = self.settings.preview({"changes": {"high_contrast": True, "motion": False}, "expected_generation": 0})
        self.settings.apply({"preview_id": preview["preview_id"], "request_id": "fixture-preferences", "expected_generation": 0})
        self.commands([self.model._request("settings.get", context="settings")])
        self.open_appearance()
        self.action("confirm")
        self.assertIn(THEME_NAMES[1], self.model.snapshot().dialog.message)
        self.assertIn("Still background", self.model.snapshot().dialog.message)
        self.action("confirm")
        self.assertEqual(self.manager.status()["theme"], THEME_NAMES[1])
        self.assertFalse(self.manager.status()["motion"])

    def test_existing_palette_overwrite_defaults_to_cancel_then_can_be_undone(self):
        palette = self.card / THEME_DIRECTORY / THEME_FILENAME
        palette.parent.mkdir(parents=True)
        palette.write_bytes(b'; owner palette\n')
        self.open_appearance()
        self.action("confirm")
        self.assertEqual(self.model.snapshot().dialog.selected, 1)
        self.assertIn("backup", self.model.snapshot().dialog.message)
        self.action("confirm")
        self.assertEqual(palette.read_bytes(), b'; owner palette\n')
        self.assertEqual(self.config.read_bytes(), ORIGINAL)
        self.action("confirm")
        self.action("up")
        self.action("confirm")
        self.assertNotEqual(palette.read_bytes(), b'; owner palette\n')
        self.action("down")
        self.action("confirm")
        self.assertEqual(palette.read_bytes(), b'; owner palette\n')

    def test_writer_starting_after_preview_blocks_apply_without_partial_writes(self):
        self.open_appearance()
        self.action("confirm")
        self.running = True
        self.action("confirm")
        self.assertTrue(self.model.snapshot().dialog.error)
        self.assertIn("BUSY_GAME", self.model.snapshot().dialog.message)
        self.assertEqual(self.config.read_bytes(), ORIGINAL)
        self.assertFalse((self.card / THEME_DIRECTORY / THEME_FILENAME).exists())

    def test_standalone_has_no_appearance_write_path_and_unknown_methods_are_rejected(self):
        self.dispatcher = Dispatcher(DemoBackend(), self.settings, self.root / "reports")
        self.open_appearance()
        self.action("confirm")
        self.assertIn("unavailable", self.model.snapshot().dialog.title)
        self.assertEqual(self.config.read_bytes(), ORIGINAL)
        for method in ("appearance.ppsspp.preview", "appearance.ppsspp.apply", "appearance.ppsspp.undo"):
            with self.subTest(method=method), self.assertRaises(AppError) as caught:
                self.dispatcher.dispatch(method, {})
            self.assertEqual(caught.exception.code, "UNQUALIFIED_THEME")
        with self.assertRaises(AppError):
            self.dispatcher.dispatch("appearance.ppsspp.execute", {"command": "never run"})
        with self.assertRaises(AppError):
            self.dispatcher.dispatch("appearance.ppsspp.extra.apply", {})
        with self.assertRaises(AppError):
            self.dispatcher.dispatch("appearance.ppsspp.status", {"path": "/untrusted"})

    def test_unqualified_installed_profile_allows_review_but_never_offers_apply(self):
        self.manager.profile_source["qualified"] = False
        self.open_appearance()
        self.action("confirm")
        self.assertEqual(self.model.snapshot().dialog.title, "PPSSPP appearance unavailable")
        self.assertEqual([choice.title for choice in self.model.snapshot().dialog.choices], ["Back"])
        self.assertEqual(self.config.read_bytes(), ORIGINAL)


if __name__ == "__main__":
    unittest.main()
