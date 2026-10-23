# SPDX-License-Identifier: MIT
"""External save backups, reviewed restore and undo use generated data only."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from psp_shell.ports import PortError, PortsManager


class PortSaveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.card = self.root / 'card'
        self.card.mkdir()
        self.manager = PortsManager(self.card)
        self.backup = self.root / 'external-backup'

    def write(self, relative, data=b'original synthetic save'):
        path = self.card / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def assert_code(self, code, operation):
        with self.assertRaises(PortError) as error: operation()
        self.assertEqual(error.exception.code, code)

    def test_all_enabled_ports_have_explicit_save_scope_and_no_state_resume(self):
        for profile in self.manager.profiles():
            if not profile['enabled']: continue
            registry = profile['save_registry']
            self.assertTrue(registry['directories'] or registry['file_patterns'])
            self.assertFalse(registry['device_paths_verified'])
            self.assertEqual(profile['resume_capability'], 'in-game-save')

    def test_directory_backup_is_external_and_roundtrip_restore_can_be_undone(self):
        save = self.write('Roms/ports/celeste/savedata/Saves/0.celeste')
        setting = self.write('Roms/ports/celeste/savedata/settings.celeste', b'original settings')
        owner = self.write('Roms/ports/celeste/gamedata/Celeste.exe', b'owner data')
        backup = self.manager.snapshot_saves('celeste', self.backup, confirm_idle=True)
        self.assertEqual(save.read_bytes(), b'original synthetic save')
        save.write_bytes(b'new progress')
        extra = self.write('Roms/ports/celeste/savedata/Saves/1.celeste', b'new slot')
        preview = self.manager.preview_save_restore(backup)
        transaction = self.manager.restore_saves(backup, preview, confirm_idle=True, confirm_overwrite=True)
        self.assertEqual(save.read_bytes(), b'original synthetic save')
        self.assertEqual(extra.read_bytes(), b'new slot')
        self.assertEqual(owner.read_bytes(), b'owner data')
        self.manager.rollback_import(transaction, confirm_idle=True)
        self.assertEqual(save.read_bytes(), b'new progress')
        self.assertEqual(setting.read_bytes(), b'original settings')

    def test_render96_conf_is_preserved_including_nested_progress(self):
        self.write('Roms/ports/render96ex/conf/progress/sm64_save_file.bin')
        inventory = self.manager.save_inventory('render96ex')
        self.assertEqual(len(inventory['files']), 1)
        self.assertFalse(inventory['uninstall_enabled'])
        self.assertFalse(inventory['device_paths_verified'])

    def test_sonic_binary_save_pattern_excludes_game_data_and_engine(self):
        self.write('Roms/ports/sonicmania/SaveData.bin')
        self.write('Roms/ports/sonicmania/UDATA.BIN')
        self.write('Roms/ports/sonicmania/Data.rsdk')
        self.write('Roms/ports/sonicmania/Game.so')
        inventory = self.manager.save_inventory('sonic_mania')
        self.assertEqual(len(inventory['files']), 2)
        self.assertTrue(all(r['target'].lower().endswith('.bin') for r in inventory['files']))

    def test_gta_patterns_preserve_slots_without_importing_models(self):
        self.write('Roms/ports/gta3/GTA3sf1.b')
        self.write('Roms/ports/gta3/models/gta3.img')
        self.assertEqual(len(self.manager.save_inventory('gta3')['files']), 1)

    def test_snapshot_requires_idle_and_never_creates_an_empty_success_backup(self):
        self.assert_code('BUSY', lambda: self.manager.snapshot_saves('sonic_mania', self.backup))
        self.assert_code('NO_SAVES', lambda: self.manager.snapshot_saves('sonic_mania', self.backup, confirm_idle=True))
        self.assertFalse(self.backup.exists())

    def test_on_card_and_symlink_backup_destinations_are_rejected(self):
        self.write('Roms/ports/sonicmania/SaveData.bin')
        self.assert_code('UNSAFE_PATH', lambda: self.manager.snapshot_saves('sonic_mania', self.card / 'backup', confirm_idle=True))
        link = self.root / 'link'
        link.symlink_to(self.root, target_is_directory=True)
        self.assert_code('UNSAFE_PATH', lambda: self.manager.snapshot_saves('sonic_mania', link / 'backup', confirm_idle=True))

    def test_parent_components_cannot_hide_a_backup_on_the_card(self):
        self.write('Roms/ports/sonicmania/SaveData.bin')
        sibling = self.root / 'sibling'
        sibling.mkdir()
        disguised = sibling / '..' / 'card' / 'backup'
        self.assert_code('UNSAFE_PATH', lambda: self.manager.snapshot_saves('sonic_mania', disguised, confirm_idle=True))
        self.assertFalse((self.card / 'backup').exists())
        (self.card / 'backup').mkdir()
        self.assert_code('UNSAFE_PATH', lambda: self.manager.preview_save_restore(disguised))

    def test_completion_syncs_files_and_new_ancestor_entries_before_receipt(self):
        from psp_shell import ports
        self.write('Roms/ports/sonicmania/SaveData.bin')
        output = self.root / 'new-parent' / 'nested' / 'backup'
        sync = ports._sync
        observations = []
        def record(directory):
            observations.append((Path(directory), (output / 'receipt.json').exists()))
            sync(directory)
        with mock.patch('psp_shell.ports._sync', side_effect=record):
            self.manager.snapshot_saves('sonic_mania', output, confirm_idle=True)
        for directory in (output / 'files', output, output.parent, output.parent.parent, self.root):
            self.assertIn((directory, False), observations)
        self.assertTrue(json.loads((output / 'receipt.json').read_text())['complete'])

    def test_fifo_and_symlink_in_save_scope_are_rejected(self):
        path = self.write('Roms/ports/sonicmania/SaveData.bin')
        path.unlink()
        os.mkfifo(path)
        self.assert_code('UNSAFE_PATH', lambda: self.manager.save_inventory('sonic_mania'))
        path.unlink()
        path.symlink_to(self.write('outside.bin'))
        self.assert_code('UNSAFE_PATH', lambda: self.manager.save_inventory('sonic_mania'))

    def test_restore_checks_confirmation_staleness_and_backup_integrity(self):
        save = self.write('Roms/ports/sonicmania/SaveData.bin')
        self.manager.snapshot_saves('sonic_mania', self.backup, confirm_idle=True)
        preview = self.manager.preview_save_restore(self.backup)
        self.assert_code('CONFIRM_OVERWRITE', lambda: self.manager.restore_saves(self.backup, preview, confirm_idle=True))
        save.write_bytes(b'changed after preview')
        self.assert_code('CONFLICT', lambda: self.manager.restore_saves(self.backup, preview, confirm_idle=True, confirm_overwrite=True))
        (self.backup / 'files/0').write_bytes(b'broken backup')
        self.assert_code('INVALID_BACKUP', lambda: self.manager.preview_save_restore(self.backup))
        self.assertEqual(save.read_bytes(), b'changed after preview')

    def test_tampered_backup_cannot_restore_over_a_game_binary(self):
        self.write('Roms/ports/sonicmania/SaveData.bin')
        self.manager.snapshot_saves('sonic_mania', self.backup, confirm_idle=True)
        path = self.backup / 'receipt.json'
        receipt = json.loads(path.read_text())
        receipt['files'][0]['target'] = 'Roms/ports/sonicmania/Game.so'
        path.write_text(json.dumps(receipt))
        self.assert_code('UNSAFE_PATH', lambda: self.manager.preview_save_restore(self.backup))

    def test_copy_failure_removes_partial_backup_and_preserves_live_saves(self):
        save = self.write('Roms/ports/sonicmania/SaveData.bin')
        with mock.patch('psp_shell.ports._copy_checked', side_effect=OSError('injected full disk')):
            with self.assertRaises(OSError):
                self.manager.snapshot_saves('sonic_mania', self.backup, confirm_idle=True)
        self.assertFalse(self.backup.exists())
        self.assertEqual(save.read_bytes(), b'original synthetic save')

    def test_malformed_backup_manifest_is_a_structured_failure(self):
        self.write('Roms/ports/sonicmania/SaveData.bin')
        self.manager.snapshot_saves('sonic_mania', self.backup, confirm_idle=True)
        (self.backup / 'receipt.json').write_bytes(b'{broken')
        self.assert_code('INVALID_BACKUP', lambda: self.manager.preview_save_restore(self.backup))

    def test_second_restore_failure_rolls_back_the_first_save(self):
        from psp_shell import ports
        first = self.write('Roms/ports/celeste/savedata/Saves/0.celeste', b'backup zero')
        second = self.write('Roms/ports/celeste/savedata/Saves/1.celeste', b'backup one')
        self.manager.snapshot_saves('celeste', self.backup, confirm_idle=True)
        first.write_bytes(b'live zero')
        second.write_bytes(b'live one')
        preview = self.manager.preview_save_restore(self.backup)
        install = ports._install
        calls = [0]
        def fail_once(*arguments):
            calls[0] += 1
            if calls[0] == 2: raise OSError('injected storage failure')
            return install(*arguments)
        with mock.patch('psp_shell.ports._install', side_effect=fail_once):
            self.assert_code('STORAGE_ERROR', lambda: self.manager.restore_saves(
                self.backup, preview, confirm_idle=True, confirm_overwrite=True))
        self.assertEqual(first.read_bytes(), b'live zero')
        self.assertEqual(second.read_bytes(), b'live one')
