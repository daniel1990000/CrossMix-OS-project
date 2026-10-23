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

    def use_ppsspp(self, menu=""):
        self.config = self.config.with_name("ppsspp-SmartPro.ini")
        self.config.write_text('[SystemParam]\nButtonPreference = 1\n[ControlMapping]\nCross = 10-189\nCircle = 10-190\n' + menu)
        self.profile.update(engine="ppsspp", surface="native_menu",
                            config="Saves/ra-configs/ppsspp-SmartPro.ini",
                            native_menu_extension={"qualified": True,
                                "source_commit": hashlib.sha1(b"synthetic extension fixture, not upstream").hexdigest(),
                                "section": "ProjectNativeMenu", "conventions": {
                                    "south": {"IndependentMenuControls": True,
                                              "NativeMenuConfirm": "south", "NativeMenuBack": "east"},
                                    "east": {"IndependentMenuControls": True,
                                             "NativeMenuConfirm": "east", "NativeMenuBack": "south"}}})
        self.save_profile()

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
        self.use_ppsspp()
        adapter = self.adapter()
        before = self.config.read_text()
        preview = self.preview(adapter)
        self.assertEqual({item["key"] for item in preview["diff"]},
                         {"IndependentMenuControls", "NativeMenuConfirm", "NativeMenuBack"})
        self.assertTrue(preview["after_configuration"]["independent_menu_controls_enabled"])
        result = self.apply(adapter, preview)
        after = self.config.read_text()
        self.assertTrue(after.startswith(before))
        self.assertIn('[ProjectNativeMenu]\nIndependentMenuControls = "true"\nNativeMenuConfirm = "east"', after)
        self.assertIn('ButtonPreference = 1', after)
        self.assertIn('Cross = 10-189', after)
        self.assertTrue(result["configuration_effective"])
        self.assertEqual(result["configured_confirm"], "east")
        undo = adapter.undo({"transaction_id": result["transaction_id"], "request_id": "undo", "expected_generation": 1})
        self.assertEqual(self.config.read_text(), before)
        self.assertFalse(undo["independent_menu_controls_enabled"])
        self.assertFalse(undo["configuration_effective"])

    def test_ppsspp_matching_pair_without_enabled_opt_in_needs_a_reviewed_edit(self):
        for index, enabled in enumerate(("", "IndependentMenuControls = False # disabled\n")):
            with self.subTest(enabled=enabled):
                self.use_ppsspp('[ProjectNativeMenu]\n' + enabled +
                                 'NativeMenuConfirm = "east"\nNativeMenuBack = "south"\n')
                before = self.config.read_bytes()
                adapter = self.adapter()
                snapshot = adapter.snapshot("synthetic-ra")
                self.assertFalse(snapshot["configuration_effective"])
                self.assertIsNone(snapshot["configured_confirm"])
                self.assertFalse(snapshot["independent_menu_controls_enabled"])
                self.assertEqual(self.config.read_bytes(), before)
                preview = self.preview(adapter, generation=snapshot["generation"])
                self.assertEqual([item["key"] for item in preview["diff"]], ["IndependentMenuControls"])
                applied = self.apply(adapter, preview, f"enable{index}")
                self.assertTrue(applied["configuration_effective"])
                self.assertEqual(applied["configured_confirm"], "east")
                self.assertIn('ButtonPreference = 1', self.config.read_text())
                adapter.undo({"transaction_id": applied["transaction_id"], "request_id": f"undo{index}",
                              "expected_generation": applied["generation"]})
                self.assertEqual(self.config.read_bytes(), before)

    def test_ppsspp_source_supported_casing_boolean_and_hash_comment_semantics(self):
        for enabled in ('"TRUE"', '1'):
            with self.subTest(enabled=enabled):
                self.use_ppsspp('[projectnativemenu]\nindependentmenucontrols = ' + enabled + ' # keep\n'
                                 'NATIVEMENUCONFIRM = "east" # physical\nNativeMenuBack = south\n')
                adapter = self.adapter()
                snapshot = adapter.snapshot("synthetic-ra")
                self.assertTrue(snapshot["independent_menu_controls_enabled"])
                self.assertTrue(snapshot["configuration_effective"])
                self.assertEqual(snapshot["configured_confirm"], "east")
                self.assertCode("NO_CHANGES", lambda: self.preview(adapter))
        preview = self.preview(adapter, confirm="south")
        result = self.apply(adapter, preview)
        text = self.config.read_text()
        self.assertIn('NATIVEMENUCONFIRM = "south" # physical', text)
        self.assertNotIn('[ProjectNativeMenu]', text)
        self.assertTrue(result["configuration_effective"])

    def test_ppsspp_semicolon_and_json_escapes_cannot_falsely_enable_a_convention(self):
        for index, menu in enumerate((
                'IndependentMenuControls = true ; this is value data\nNativeMenuConfirm = east\nNativeMenuBack = south\n',
                'IndependentMenuControls = true\nNativeMenuConfirm = "e\\u0061st"\nNativeMenuBack = south\n')):
            with self.subTest(menu=menu):
                self.use_ppsspp('[ProjectNativeMenu]\n' + menu)
                adapter = self.adapter()
                snapshot = adapter.snapshot("synthetic-ra")
                self.assertFalse(snapshot["configuration_effective"])
                self.assertIsNone(snapshot["configured_confirm"])
                preview = self.preview(adapter, generation=snapshot["generation"])
                applied = self.apply(adapter, preview, f"repair{index}")
                self.assertTrue(applied["configuration_effective"])
                self.assertEqual(adapter.snapshot("synthetic-ra")["configured_confirm"], "east")

    def test_ppsspp_duplicate_sections_or_case_insensitive_keys_are_ambiguous(self):
        for menu in (
                '[ProjectNativeMenu]\nIndependentMenuControls = false\nindependentmenucontrols = true\n',
                '[projectnativemenu]\n# first section is authoritative\n[ProjectNativeMenu]\nIndependentMenuControls = true\n'):
            with self.subTest(menu=menu):
                self.use_ppsspp(menu)
                adapter = self.adapter()
                before = self.config.read_bytes()
                self.assertFalse(adapter.snapshot("synthetic-ra")["configuration_effective"])
                self.assertCode("AMBIGUOUS_CONFIG", lambda: self.preview(adapter))
                self.assertEqual(self.config.read_bytes(), before)

    def test_ppsspp_bracket_internal_spaces_are_a_different_section(self):
        self.use_ppsspp('[ ProjectNativeMenu ]\nIndependentMenuControls = true\n'
                         'NativeMenuConfirm = east\nNativeMenuBack = south\n')
        adapter = self.adapter()
        self.assertFalse(adapter.snapshot("synthetic-ra")["configuration_effective"])
        preview = self.preview(adapter)
        self.assertEqual(len(preview["diff"]), 3)
        self.apply(adapter, preview)
        self.assertIn('[ProjectNativeMenu]\nIndependentMenuControls = "true"', self.config.read_text())

    def test_ppsspp_unicode_whitespace_or_casefolding_cannot_invent_engine_values(self):
        for menu in (
                'IndependentMenuControls = true\u00a0\nNativeMenuConfirm = east\nNativeMenuBack = south\n',
                'IndependentMenuControls = true\nNativeMenuConfirm = east\u2028unrecognized\nNativeMenuBack = south\n',
                'IndependentMenuControl\u017f = true\nNativeMenuConfirm = east\nNativeMenuBack = south\n'):
            with self.subTest(menu=menu):
                self.use_ppsspp('[ProjectNativeMenu]\n' + menu)
                snapshot = self.adapter().snapshot("synthetic-ra")
                self.assertFalse(snapshot["configuration_effective"])
                self.assertIsNone(snapshot["configured_confirm"])

    def test_ppsspp_configuration_status_does_not_bypass_qualification_or_running_writers(self):
        self.use_ppsspp('[ProjectNativeMenu]\nIndependentMenuControls = true\nNativeMenuConfirm = east\nNativeMenuBack = south\n')
        for key, value in (("qualified", False), ("writer_inventory_verified", False), ("executable_sha256", "0" * 64)):
            previous = self.profile[key]
            self.profile[key] = value
            self.save_profile()
            snapshot = self.adapter().snapshot("synthetic-ra")
            self.assertEqual(snapshot["configured_confirm"], "east")
            self.assertFalse(snapshot["configuration_effective"])
            self.profile[key] = previous
            self.save_profile()
        self.assertFalse(self.adapter(process_probe=lambda _: True).snapshot("synthetic-ra")["configuration_effective"])

    def test_ppsspp_status_refuses_a_configuration_or_profile_changed_during_qualification(self):
        self.use_ppsspp('[ProjectNativeMenu]\nIndependentMenuControls = true\nNativeMenuConfirm = east\nNativeMenuBack = south\n')
        before = self.config.read_bytes()

        def concurrent_config_writer():
            self.config.write_bytes(before.replace(b'= true', b'= false', 1))
            return True

        snapshot = self.adapter(quiescent=concurrent_config_writer).snapshot("synthetic-ra")
        self.assertFalse(snapshot["configuration_effective"])
        self.assertEqual(snapshot["config_sha256"], hashlib.sha256(before).hexdigest())
        self.config.write_bytes(before)

        def concurrent_profile_writer():
            self.profile["qualified"] = False
            self.save_profile()
            return True

        self.assertFalse(self.adapter(quiescent=concurrent_profile_writer).snapshot("synthetic-ra")["configuration_effective"])

    def test_ppsspp_pair_only_or_invalid_profile_contract_refuses_writes(self):
        self.use_ppsspp()
        conventions = self.profile["native_menu_extension"]["conventions"]
        for change in (lambda: conventions["east"].pop("IndependentMenuControls"),
                       lambda: conventions["east"].update(IndependentMenuControls=False),
                       lambda: conventions["east"].update(NativeMenuBack="east")):
            original = copy.deepcopy(conventions["east"])
            change()
            self.save_profile()
            before = self.config.read_bytes()
            self.assertCode("UNSUPPORTED_PROFILE", lambda: self.preview(self.adapter()))
            self.assertEqual(self.config.read_bytes(), before)
            conventions["east"] = original

    def test_ppsspp_preview_cannot_omit_the_enable_edit_or_add_gameplay_edits(self):
        self.use_ppsspp()
        adapter = self.adapter()
        for mutate in (lambda changes: [item for item in changes if item["key"] != "IndependentMenuControls"],
                       lambda changes: [{**changes[0], "after": False}, *changes[1:]],
                       lambda changes: [*changes[:2], {**changes[2], "key": "ButtonPreference"}]):
            preview = self.preview(adapter)
            path = adapter.previews / (preview["preview_id"] + ".json")
            record = json.loads(path.read_text())
            record["diff"] = mutate(record["diff"])
            path.write_text(json.dumps(record))
            before = self.config.read_bytes()
            self.assertCode("INVALID_PREVIEW", lambda: self.apply(adapter, preview))
            self.assertEqual(self.config.read_bytes(), before)

    def test_ppsspp_undo_preserves_unrelated_edits_and_refuses_external_disable(self):
        self.use_ppsspp('[ProjectNativeMenu]\nIndependentMenuControls = false # keep\n')
        adapter = self.adapter()
        result = self.apply(adapter, self.preview(adapter))
        self.config.write_text(self.config.read_text().replace('"true"', 'false', 1))
        before = self.config.read_bytes()
        self.assertCode("UNDO_CONFLICT", lambda: adapter.undo(
            {"transaction_id": result["transaction_id"], "request_id": "undo", "expected_generation": 1}))
        self.assertEqual(self.config.read_bytes(), before)
        self.config.write_text(self.config.read_text().replace('IndependentMenuControls = false',
                                                             'IndependentMenuControls = "true"', 1) + 'external = keep\n')
        undone = adapter.undo({"transaction_id": result["transaction_id"], "request_id": "undo", "expected_generation": 1})
        self.assertFalse(undone["configuration_effective"])
        self.assertIn('IndependentMenuControls = false # keep', self.config.read_text())
        self.assertIn('external = keep', self.config.read_text())

    @unittest.skipUnless(hasattr(os, "fork"), "POSIX multi-file crash fixture")
    def test_ppsspp_three_key_crash_recovers_original_opt_in_and_gameplay(self):
        self.use_ppsspp()
        adapter = self.adapter()
        preview = self.preview(adapter)
        before = self.config.read_bytes()
        pid = os.fork()
        if pid == 0:
            adapter.fault_hook = lambda point, index: os._exit(75) if point == "after_replace" and index == 0 else None
            self.apply(adapter, preview, "crash-ppsspp")
            os._exit(99)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 75)
        self.assertIn(b'IndependentMenuControls = "true"', self.config.read_bytes())
        recovered = self.adapter()
        self.assertEqual(self.config.read_bytes(), before)
        snapshot = recovered.snapshot("synthetic-ra")
        self.assertFalse(snapshot["configuration_effective"])
        self.assertEqual(snapshot["generation"], 0)

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
