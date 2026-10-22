"""Synthetic engine/profile fixtures; no shipped binary is qualified here."""

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from psp_shell.controls import EmulatorConfigAdapter, set_config_token, ui_convention, validate_ui_mapping
from psp_shell.settings import SettingsError


class ControlPolicy(unittest.TestCase):
    def test_ui_conventions_use_physical_labels_without_gameplay_changes(self):
        south = ui_convention("south")
        east = ui_convention("east")
        self.assertEqual(south["hints"], {"confirm": "B", "back": "A"})
        self.assertEqual(east["hints"], {"confirm": "A", "back": "B"})
        self.assertFalse(south["gameplay_changed"])
        validate_ui_mapping(south["physical_to_action"])
        with self.assertRaises(SettingsError):
            validate_ui_mapping({**south["physical_to_action"], "east": "confirm"})
        with self.assertRaises(SettingsError):
            ui_convention([])

    def test_cfg_editor_preserves_bom_crlf_comments_unknowns_and_quoted_hash(self):
        before = '\ufeff# keep\r\nmenu_swap_ok_cancel_buttons  =  "false"  # note\r\nunknown = "$a;`b`#inside"\r\n'
        after = set_config_token(before, "menu_swap_ok_cancel_buttons", '"true"')
        self.assertEqual(after, before.replace('"false"', '"true"', 1))
        self.assertEqual(set_config_token(after, "menu_swap_ok_cancel_buttons", '"false"'), before)

    def test_ini_editor_does_not_put_global_or_section_key_in_wrong_section(self):
        text = "# first\n[Other]\nunknown = 1\n[ProjectNativeMenu]\nkeep = hello\n[Last]\nmore = 2\n"
        changed = set_config_token(text, "NativeMenuConfirm", '"south"', section="ProjectNativeMenu")
        self.assertIn('keep = hello\nNativeMenuConfirm = "south"\n[Last]', changed)
        global_change = set_config_token(text, "menu_swap_ok_cancel_buttons", '"true"')
        self.assertTrue(global_change.startswith('# first\nmenu_swap_ok_cancel_buttons = "true"\n[Other]'))
        missing = set_config_token("[Other]\nkeep = 1\n", "NativeMenuBack", '"east"', section="ProjectNativeMenu")
        self.assertTrue(missing.endswith('[ProjectNativeMenu]\nNativeMenuBack = "east"\n'))

    def test_duplicate_and_unterminated_owned_keys_are_rejected(self):
        for text in ('menu_swap_ok_cancel_buttons="false"\nmenu_swap_ok_cancel_buttons="true"\n',
                     'menu_swap_ok_cancel_buttons="false\n'):
            with self.assertRaises(SettingsError):
                set_config_token(text, "menu_swap_ok_cancel_buttons", '"true"')


class EmulatorTransactions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sd = self.root / "card"
        self.profiles = self.root / "profiles"
        self.sd.mkdir()
        self.profiles.mkdir()
        self.executable = self.sd / "RetroArch" / "fixture-emulator"
        self.executable.parent.mkdir()
        self.executable.write_bytes(b"synthetic host engine; never executed")
        self.executable.chmod(0o755)
        self.config = self.sd / "Saves" / "ra-configs" / "retroarch-SmartPro.cfg"
        self.config.parent.mkdir(parents=True)
        self.config.write_text('# keep\nmenu_swap_ok_cancel_buttons = "false" # menu only\ninput_player1_a_btn = "1"\nunknown = "keep"\n')
        self.profile = {"schema": 1, "id": "synthetic-ra", "device": "TRIMUI_SMART_PRO",
                        "qualified": True, "engine": "retroarch", "surface": "standard_menu",
                        "executable": "RetroArch/fixture-emulator",
                        "executable_sha256": hashlib.sha256(self.executable.read_bytes()).hexdigest(),
                        "config": "Saves/ra-configs/retroarch-SmartPro.cfg",
                        "writer_inventory_verified": True,
                        "writer_executables": ["RetroArch/fixture-emulator"],
                        "supported_keys": ["menu_swap_ok_cancel_buttons"],
                        "confirm_values": {"south": False, "east": True}}
        self.save_profile()

    def save_profile(self):
        (self.profiles / "synthetic-ra.json").write_text(json.dumps(self.profile))

    def adapter(self, **kwargs):
        return EmulatorConfigAdapter(self.sd, self.root / "state", self.profiles,
                                     quiescent=kwargs.pop("quiescent", lambda: True),
                                     process_probe=kwargs.pop("process_probe", lambda _: False), **kwargs)

    def assertCode(self, code, callback):
        with self.assertRaises(SettingsError) as raised:
            callback()
        self.assertEqual(raised.exception.code, code)

    def preview(self, adapter, confirm="east", generation=0):
        return adapter.preview({"profile_id": "synthetic-ra", "confirm": confirm,
                                "expected_generation": generation})

    def apply(self, adapter, preview, request="apply"):
        return adapter.apply({"preview_id": preview["preview_id"], "request_id": request,
                              "expected_generation": preview["generation"]})

    def test_read_only_snapshot_changes_neither_authority_nor_gameplay(self):
        before = self.config.read_bytes()
        adapter = self.adapter()
        snapshot = adapter.snapshot("synthetic-ra")
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(snapshot["keys"], {"menu_swap_ok_cancel_buttons": '"false"'})
        self.assertFalse(snapshot["gameplay_changed"])

    def test_ra_preview_apply_and_targeted_undo_preserve_unknown_fields(self):
        adapter = self.adapter()
        before = self.config.read_text()
        preview = self.preview(adapter)
        self.assertEqual(self.config.read_text(), before)
        result = self.apply(adapter, preview)
        self.assertEqual(self.config.read_text(), before.replace('"false"', '"true"', 1))
        self.assertFalse(result["gameplay_changed"])
        self.assertTrue(self.apply(adapter, preview)["idempotent"])
        self.config.write_text(self.config.read_text() + 'external = "retain"\n')
        adapter.undo({"transaction_id": result["transaction_id"], "request_id": "undo", "expected_generation": 1})
        self.assertEqual(self.config.read_text(), before + 'external = "retain"\n')

    def test_undo_refuses_changed_owned_key(self):
        adapter = self.adapter()
        result = self.apply(adapter, self.preview(adapter))
        self.config.write_text(self.config.read_text().replace('"true"', '"false"', 1))
        before = self.config.read_bytes()
        self.assertCode("UNDO_CONFLICT", lambda: adapter.undo(
            {"transaction_id": result["transaction_id"], "request_id": "undo", "expected_generation": 1}))
        self.assertEqual(self.config.read_bytes(), before)

    def test_added_key_undo_preserves_other_lines_but_not_edited_inserted_line(self):
        self.config.write_text('# no menu preference\nunknown="keep"\n')
        adapter = self.adapter()
        before = self.config.read_bytes()
        result = self.apply(adapter, self.preview(adapter))
        adapter.undo({"transaction_id": result["transaction_id"], "request_id": "undo", "expected_generation": 1})
        self.assertEqual(self.config.read_bytes(), before)
        result = self.apply(adapter, self.preview(adapter, generation=2), "apply2")
        self.config.write_text(self.config.read_text().replace('"true"', '"true" # external comment'))
        self.assertCode("UNDO_CONFLICT", lambda: adapter.undo(
            {"transaction_id": result["transaction_id"], "request_id": "undo2", "expected_generation": 3}))

    def test_qualified_hash_writer_and_quiescence_are_all_required(self):
        self.assertCode("BUSY_WRITER", lambda: self.preview(self.adapter(quiescent=lambda: False)))
        self.assertCode("BUSY_GAME", lambda: self.preview(self.adapter(process_probe=lambda _: True)))
        for key, value in (("qualified", False), ("writer_inventory_verified", False),
                           ("executable_sha256", "0" * 64)):
            original = self.profile[key]
            self.profile[key] = value
            self.save_profile()
            self.assertCode("UNSUPPORTED_PROFILE", lambda: self.preview(self.adapter()))
            self.profile[key] = original
            self.save_profile()

    def test_changed_fingerprint_or_profile_after_preview_is_rejected(self):
        adapter = self.adapter()
        preview = self.preview(adapter)
        self.executable.write_bytes(b"different engine")
        self.assertCode("UNSUPPORTED_PROFILE", lambda: self.apply(adapter, preview))
        self.executable.write_bytes(b"synthetic host engine; never executed")
        self.profile["note"] = "changed after preview"
        self.save_profile()
        self.assertCode("STALE_SNAPSHOT", lambda: self.apply(adapter, preview))

    def test_stale_config_and_read_only_file_are_preserved(self):
        adapter = self.adapter()
        preview = self.preview(adapter)
        self.config.write_text(self.config.read_text() + "external=true\n")
        before = self.config.read_bytes()
        self.assertCode("STALE_SNAPSHOT", lambda: self.apply(adapter, preview))
        self.assertEqual(self.config.read_bytes(), before)
        preview = self.preview(adapter)
        self.config.chmod(0o444)
        try:
            self.assertCode("STORAGE_READ_ONLY", lambda: self.apply(adapter, preview, "readonly"))
        finally:
            self.config.chmod(0o600)
        self.assertEqual(self.config.read_bytes(), before)

    def test_spruce_igm_is_not_misrepresented_as_standard_ra_menu(self):
        self.profile["surface"] = "spruce_igm"
        self.save_profile()
        before = self.config.read_bytes()
        self.assertCode("UNSUPPORTED_CAPABILITY", lambda: self.preview(self.adapter()))
        self.assertEqual(self.config.read_bytes(), before)

    def test_ppsspp_native_menu_declines_without_touching_psp_preference(self):
        self.profile.update(engine="ppsspp", surface="native_menu")
        self.config.write_text('[SystemParam]\nButtonPreference = 1\n[ControlMapping]\nCross = 10-189\nCircle = 10-190\n')
        self.save_profile()
        before = self.config.read_bytes()
        self.assertCode("UNSUPPORTED_CAPABILITY", lambda: self.preview(self.adapter()))
        self.assertEqual(self.config.read_bytes(), before)

    def test_null_unqualified_extension_remains_a_read_only_snapshot(self):
        self.profile.update(engine="ppsspp", surface="native_menu", qualified=False, native_menu_extension=None)
        self.save_profile()
        before = self.config.read_bytes()
        snapshot = self.adapter().snapshot("synthetic-ra")
        self.assertFalse(snapshot["menu_adapter_implemented"])
        self.assertEqual(self.config.read_bytes(), before)

    def test_explicit_synthetic_ppsspp_extension_edits_only_extension_keys(self):
        self.config = self.config.with_name("ppsspp-SmartPro.ini")
        self.config.write_text('[SystemParam]\nButtonPreference = 1\n[ControlMapping]\nCross = 10-189\nCircle = 10-190\n')
        self.profile.update(engine="ppsspp", surface="native_menu",
                            config="Saves/ra-configs/ppsspp-SmartPro.ini",
                            native_menu_extension={"qualified": True,
                                "source_commit": hashlib.sha1(b"synthetic extension fixture, not upstream").hexdigest(),
                                "section": "ProjectNativeMenu", "conventions": {
                                    "south": {"NativeMenuConfirm": "south", "NativeMenuBack": "east"},
                                    "east": {"NativeMenuConfirm": "east", "NativeMenuBack": "south"}}})
        self.save_profile()
        adapter = self.adapter()
        before = self.config.read_text()
        self.apply(adapter, self.preview(adapter))
        after = self.config.read_text()
        self.assertTrue(after.startswith(before))
        self.assertIn('[ProjectNativeMenu]\nNativeMenuConfirm = "east"', after)
        self.assertIn('ButtonPreference = 1', after)
        self.assertIn('Cross = 10-189', after)

    def test_path_traversal_and_symlink_escape_are_rejected(self):
        self.profile["config"] = "../../outside"
        self.save_profile()
        self.assertCode("UNSAFE_PATH", lambda: self.adapter().snapshot("synthetic-ra"))
        self.profile["config"] = "Saves/ra-configs/retroarch-SmartPro.cfg"
        self.save_profile()
        self.config.unlink()
        outside = self.root / "outside.cfg"
        outside.write_text('menu_swap_ok_cancel_buttons="false"\n')
        self.config.symlink_to(outside)
        self.assertCode("UNSAFE_PATH", lambda: self.adapter().snapshot("synthetic-ra"))

    @unittest.skipUnless(hasattr(os, "fork"), "POSIX multi-file crash fixture")
    def test_multi_file_crash_restores_config_and_generation(self):
        adapter = self.adapter()
        preview = self.preview(adapter)
        before = self.config.read_bytes()
        pid = os.fork()
        if pid == 0:
            adapter.fault_hook = lambda point, index: os._exit(75) if point == "after_replace" and index == 0 else None
            self.apply(adapter, preview, "crash")
            os._exit(99)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 75)
        self.assertNotEqual(self.config.read_bytes(), before)
        recovered = self.adapter()
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(recovered.capabilities()["generation"], 0)


if __name__ == "__main__":
    unittest.main()
