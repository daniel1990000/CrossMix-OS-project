# SPDX-License-Identifier: MIT
"""IGM JSON appearance is separate from native/RetroArch menu controls."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from psp_shell.controls import (IGM_PALETTES, IGM_SCHEMA_SHA256, SPRUCE_COMMIT,
    EmulatorConfigAdapter, SpruceIGMAppearanceAdapter)
from psp_shell.settings import SettingsError


class IGMAppearanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.card, self.profiles = self.root / "card", self.root / "profiles"
        self.card.mkdir()
        self.profiles.mkdir()
        self.binary = self.card / "RetroArch/ra64.fixture"
        self.binary.parent.mkdir()
        self.binary.write_bytes(b"synthetic engine; never run")
        self.config = self.card / "RetroArch/igm.json"
        self.original = b'{\n "colors": {"text": "#ABCDEF", "future_color": "#010203"}, "layout": {"item_h_pct": 8}, "labels": {"exit": "Exit safely"}\n}\n'
        self.config.write_bytes(self.original)
        self.profile = {"schema": 1, "id": "igm-fixture", "device": "TRIMUI_SMART_PRO", "engine": "retroarch",
            "surface": "spruce_igm", "qualified": True, "appearance_qualified": True,
            "path_contract_verified": True, "base_commit": SPRUCE_COMMIT, "igm_schema_sha256": IGM_SCHEMA_SHA256,
            "executable": "RetroArch/ra64.fixture", "executable_sha256": hashlib.sha256(self.binary.read_bytes()).hexdigest(),
            "writer_inventory_verified": True, "writer_executables": ["RetroArch/ra64.fixture"], "config": "RetroArch/igm.json"}
        self.active, self.running = None, False
        self.save_profile()
        self.manager = self.make_manager()

    def save_profile(self):
        (self.profiles / "igm-fixture.json").write_text(json.dumps(self.profile))

    def make_manager(self, fault=None):
        return SpruceIGMAppearanceAdapter(self.card, self.root / "state", self.profiles,
            quiescent=lambda: True, process_probe=lambda _: self.running, active_theme_config=lambda: self.active,
            fault_hook=fault)

    def preview(self):
        return self.manager.preview({"profile_id": "igm-fixture", "palette": "midnight", "expected_generation": 0})

    def apply(self, preview=None):
        preview = preview or self.preview()
        return self.manager.apply({"preview_id": preview["preview_id"], "request_id": "apply", "expected_generation": 0})

    def assert_code(self, code, callback):
        with self.assertRaises(SettingsError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_palette_changes_only_supported_colors_and_exact_undo_restores_original_bytes(self):
        preview = self.preview()
        self.assertEqual(self.config.read_bytes(), self.original)
        result = self.apply(preview)
        value = json.loads(self.config.read_bytes())
        self.assertEqual(value["colors"]["future_color"], "#010203")
        self.assertEqual(value["labels"], {"exit": "Exit safely"})
        self.assertEqual(value["layout"], {"item_h_pct": 8})
        self.assertEqual(value["colors"]["text"], IGM_PALETTES["midnight"]["text"])
        self.assertTrue(self.apply(preview)["idempotent"])
        self.assertTrue(result["read_on_next_game_launch"])
        self.manager.undo({"transaction_id": result["transaction_id"], "request_id": "undo", "expected_generation": 1})
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_theme_override_precedence_is_observed_before_write(self):
        path = self.card / "Themes/Owner/igm.json"
        path.parent.mkdir(parents=True)
        path.write_bytes(self.original)
        self.active = "Themes/Owner/igm.json"
        preview = self.preview()
        self.assertFalse(preview["adoption_available"])
        self.assertEqual(preview["gate_reason"], "IGM_THEME_OVERRIDE")
        self.assert_code("IGM_THEME_OVERRIDE", lambda: self.apply(preview))
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_explicit_current_theme_target_is_separate_from_the_global_fallback(self):
        target = self.card / "Themes/Original/igm.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(self.original)
        self.profile["config"] = self.active = "Themes/Original/igm.json"
        self.save_profile()
        self.apply()
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertIn(b"#64FFDFFF", target.read_bytes())
        self.active = None
        self.assertFalse(self.manager.status("igm-fixture")["adoption_available"])

    def test_unsupported_controls_are_not_represented_by_palette_support(self):
        status = self.manager.status("igm-fixture")
        self.assertTrue(status["appearance_adapter_implemented"])
        self.assertFalse(status["controls_adapter_implemented"])
        adapter = EmulatorConfigAdapter(self.card, self.root / "control-state", self.profiles,
            quiescent=lambda: True, process_probe=lambda _: False)
        self.assert_code("UNSUPPORTED_CAPABILITY", lambda: adapter.preview(
            {"profile_id": "igm-fixture", "confirm": "east", "expected_generation": 0}))

    def test_jsonc_is_refused_without_destroying_comments(self):
        raw = b'{ // native parser supports JSONC, this adapter deliberately does not rewrite it\n "colors": {}\n}\n'
        self.config.write_bytes(raw)
        self.assert_code("INVALID_CONFIG", self.preview)
        self.assertEqual(self.config.read_bytes(), raw)

    def test_unqualified_parser_or_busy_writer_cannot_change_palette(self):
        preview = self.preview()
        self.running = True
        self.assert_code("BUSY_GAME", lambda: self.apply(preview))
        self.running = False
        self.profile["appearance_qualified"] = False
        self.save_profile()
        self.assert_code("UNSUPPORTED_PROFILE", lambda: self.apply(preview))
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_interrupted_palette_commit_rolls_back_before_ui_reopens(self):
        def fault(point, index):
            if point == "after_replace" and index == 0:
                raise RuntimeError("interrupted IGM write")
        self.manager = self.make_manager(fault)
        with self.assertRaises(RuntimeError):
            self.apply()
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(self.manager.status("igm-fixture")["generation"], 0)

    def test_undo_preserves_external_nonowned_fields_but_refuses_owned_edits(self):
        result = self.apply()
        value = json.loads(self.config.read_bytes())
        value["labels"]["resume"] = "Owner label"
        self.config.write_text(json.dumps(value))
        self.manager.undo({"transaction_id": result["transaction_id"], "request_id": "undo", "expected_generation": 1})
        value = json.loads(self.config.read_bytes())
        self.assertEqual(value["labels"]["resume"], "Owner label")
        self.assertEqual(value["colors"]["text"], "#ABCDEF")

    def test_schema_source_matches_actual_pinned_spruce_docs(self):
        source = Path(os.environ.get("SPRUCE_SOURCE_ROOT", "/workspace/spruce-base"))
        raw = (source / "RetroArch/igm/README.md").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), IGM_SCHEMA_SHA256)
        colors = json.loads((source / "RetroArch/igm/spruce.json").read_text())["colors"]
        self.assertEqual(set(IGM_PALETTES["midnight"]), set(colors))
        self.assertIn(b"A theme's file wins outright", raw)
        self.assertIn(b"once, when a game launches", raw)


if __name__ == "__main__":
    unittest.main()
