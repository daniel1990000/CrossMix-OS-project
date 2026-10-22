# SPDX-License-Identifier: MIT
"""Qualified fixture profile tests; installed spruce engines stay unqualified."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from psp_shell.controls import (EmulatorConfigAdapter, IGM_EXTENSION_ID, IGM_RECIPE_COMMIT,
                               IGM_SCHEMA_SHA256, SPRUCE_COMMIT)
from psp_shell.settings import SettingsError


class IGMControlsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.card, self.profiles = self.root / 'card', self.root / 'profiles'
        self.profiles.mkdir()
        self.binary = self.card / 'RetroArch/fixture'
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b'synthetic engine; never run')
        self.config = self.card / 'RetroArch/igm.json'
        self.original = b'{"colors":{"text":"#123456"},"layout":{"row":8},"future":[1,2]}\n'
        self.config.write_bytes(self.original)
        self.profile = {'schema': 1, 'id': 'fixture', 'device': 'TRIMUI_SMART_PRO',
            'engine': 'retroarch', 'surface': 'spruce_igm', 'qualified': True,
            'base_commit': SPRUCE_COMMIT, 'igm_schema_sha256': IGM_SCHEMA_SHA256,
            'path_contract_verified': True, 'writer_inventory_verified': True,
            'writer_executables': ['RetroArch/fixture'], 'executable': 'RetroArch/fixture',
            'executable_sha256': hashlib.sha256(self.binary.read_bytes()).hexdigest(),
            'config': 'RetroArch/igm.json', 'igm_menu_extension': {'qualified': True,
                'source_commit': IGM_RECIPE_COMMIT, 'id': IGM_EXTENSION_ID,
                'section': 'project_menu_controls', 'physical_buttons': {'south': 0, 'east': 8}}}
        self.active, self.running = None, False
        self.save_profile()
        self.manager = self.make_manager()

    def save_profile(self):
        (self.profiles / 'fixture.json').write_text(json.dumps(self.profile))

    def make_manager(self, **kwargs):
        return EmulatorConfigAdapter(self.card, self.root / 'state', self.profiles,
            quiescent=lambda: True, process_probe=lambda _: self.running,
            active_theme_config=lambda: self.active, **kwargs)

    def preview(self, confirm='south', generation=0):
        return self.manager.preview({'profile_id': 'fixture', 'confirm': confirm, 'expected_generation': generation})

    def apply(self, preview=None):
        preview = preview or self.preview()
        return self.manager.apply({'preview_id': preview['preview_id'], 'request_id': 'apply',
                                   'expected_generation': preview['generation']})

    def assert_code(self, code, operation):
        with self.assertRaises(SettingsError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def test_distinct_native_surface_preserves_palette_layout_and_gameplay(self):
        result = self.apply()
        value = json.loads(self.config.read_bytes())
        self.assertEqual(value['project_menu_controls'], {'enabled': True, 'confirm': 'south', 'back': 'east'})
        for key, data in json.loads(self.original).items():
            self.assertEqual(value[key], data)
        self.assertFalse(result['gameplay_changed'])
        self.assertFalse(result['runtime_observed'])
        self.assertEqual(result['configured_confirm'], 'south')
        self.manager.undo({'transaction_id': result['transaction_id'], 'request_id': 'undo', 'expected_generation': 1})
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_east_confirm_and_targeted_undo_retain_external_colors(self):
        result = self.apply(self.preview('east'))
        value = json.loads(self.config.read_bytes())
        value['colors']['text'] = '#654321'
        value['project_menu_controls']['future_key'] = 'preserve'
        self.config.write_text(json.dumps(value))
        self.manager.undo({'transaction_id': result['transaction_id'], 'request_id': 'undo', 'expected_generation': 1})
        value = json.loads(self.config.read_bytes())
        self.assertEqual(value['project_menu_controls'], {'future_key': 'preserve'})
        self.assertEqual(value['colors']['text'], '#654321')

    def test_stock_fixed_controls_remain_unsupported(self):
        self.profile['igm_menu_extension'] = None
        self.save_profile()
        self.assert_code('UNSUPPORTED_CAPABILITY', self.preview)
        self.assertFalse(self.manager.snapshot('fixture')['menu_adapter_implemented'])
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_boolean_integer_does_not_claim_enabled_controls(self):
        self.config.write_text('{"project_menu_controls":{"enabled":1,"confirm":"south","back":"east"}}')
        before = self.manager.snapshot('fixture')
        self.assertIsNone(before['configured_confirm'])
        self.assertFalse(before['independent_menu_controls_enabled'])
        self.assertEqual([item['key'] for item in self.preview()['diff']], ['enabled'])

    def test_active_theme_precedence_rechecked_at_commit(self):
        preview = self.preview()
        self.active = 'Themes/Owner/igm.json'
        path = self.card / self.active
        path.parent.mkdir(parents=True)
        path.write_bytes(self.original)
        self.assert_code('IGM_THEME_OVERRIDE', lambda: self.apply(preview))
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_explicit_theme_target_and_missing_observer(self):
        self.active = self.profile['config'] = 'Themes/Owner/igm.json'
        target = self.card / self.active
        target.parent.mkdir(parents=True)
        target.write_bytes(self.original)
        self.save_profile()
        self.apply()
        self.assertIn('project_menu_controls', json.loads(target.read_bytes()))
        self.assertEqual(self.config.read_bytes(), self.original)
        self.manager.active_theme_config = None
        self.assert_code('UNSUPPORTED_PROFILE', lambda: self.preview('east', 1))

    def test_jsonc_and_duplicate_keys_are_preserved_unchanged(self):
        for data in (b'{/*comment*/"colors":{}}', b'{"project_menu_controls":{},"project_menu_controls":{}}'):
            self.config.write_bytes(data)
            self.assert_code('INVALID_CONFIG', self.preview)
            self.assertEqual(self.config.read_bytes(), data)

    def test_busy_writer_and_extension_fingerprint_are_required(self):
        self.running = True
        self.assert_code('BUSY_GAME', self.preview)
        self.running = False
        self.profile['igm_menu_extension']['physical_buttons']['south'] = 8
        self.save_profile()
        self.assert_code('UNSUPPORTED_CAPABILITY', self.preview)

    def test_incomplete_preview_and_modified_undo_journal_are_refused(self):
        preview = self.preview()
        path = self.manager.previews / (preview['preview_id'] + '.json')
        record = json.loads(path.read_bytes())
        record['diff'].pop()
        path.write_text(json.dumps(record))
        self.assert_code('INVALID_PREVIEW', lambda: self.apply(preview))
        result = self.apply(self.preview())
        journal_path = self.manager.state_dir / 'transactions' / (result['transaction_id'] + '.json')
        journal = json.loads(journal_path.read_bytes())
        journal['metadata']['diff'][0]['before_present'] = True
        journal['metadata']['diff'][0]['before'] = 'tampered'
        journal_path.write_text(json.dumps(journal))
        self.assert_code('UNDO_CONFLICT', lambda: self.manager.undo({'transaction_id': result['transaction_id'],
            'request_id': 'undo', 'expected_generation': 1}))
