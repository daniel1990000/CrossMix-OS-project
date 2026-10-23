"""Original owner-file import tests using generated data, never commercial files."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from psp_shell.ports import DEFAULT_PROFILES, PortError, PortsManager


class OwnerPortImports(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.card = self.base / 'card'
        self.card.mkdir()
        self.owner = self.base / 'owner'
        self.owner.mkdir()
        self.manager = PortsManager(self.card)

    def tearDown(self):
        self.temporary.cleanup()

    def owner_file(self, name, value=b'generated fixture'):
        file = self.owner / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(value)
        return file

    def card_file(self, name, value=b'installed fixture'):
        file = self.card / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(value)
        return file

    def assert_code(self, code, operation):
        with self.assertRaises(PortError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def test_preview_cancel_leaves_both_trees_unchanged(self):
        source = self.owner_file('Data.rsdk')
        preview = self.manager.preview_import('sonic_mania', source)
        self.assertFalse((self.card / 'Saves').exists())
        self.manager.cancel_import(preview)
        self.assertEqual(source.read_bytes(), b'generated fixture')
        self.assert_code('STALE_PREVIEW', lambda: self.manager.apply_import(preview, confirm_idle=True))
        self.assertFalse((self.card / 'Roms').exists())

    def test_import_undo_preserves_owner_original(self):
        source = self.owner_file('Data.rsdk')
        preview = self.manager.preview_import('sonic_mania', source)
        self.assert_code('BUSY', lambda: self.manager.apply_import(preview))
        receipt = self.manager.apply_import(preview, confirm_idle=True)
        installed = self.card / 'Roms/ports/sonicmania/Data.rsdk'
        self.assertEqual(installed.read_bytes(), source.read_bytes())
        self.manager.rollback_import(receipt, confirm_idle=True)
        self.assertFalse(installed.exists())
        self.assertEqual(source.read_bytes(), b'generated fixture')

    def test_overwrite_requires_confirmation_and_undo_restores_previous_data(self):
        source = self.owner_file('Data.rsdk', b'new fixture')
        old = self.card_file('Roms/ports/sonicmania/Data.rsdk', b'old fixture')
        preview = self.manager.preview_import('sonic_mania', source)
        self.assertTrue(preview.as_dict()['overwrites'])
        self.assert_code('CONFIRM_OVERWRITE', lambda: self.manager.apply_import(preview, confirm_idle=True))
        receipt = self.manager.apply_import(preview, confirm_idle=True, confirm_overwrite=True)
        self.assertEqual(old.read_bytes(), b'new fixture')
        self.manager.rollback_import(receipt, confirm_idle=True)
        self.assertEqual(old.read_bytes(), b'old fixture')

    def test_source_edit_invalidates_preview(self):
        source = self.owner_file('Data.rsdk')
        preview = self.manager.preview_import('sonic_mania', source)
        source.write_bytes(b'external source edit')
        self.assert_code('CONFLICT', lambda: self.manager.apply_import(preview, confirm_idle=True))
        self.assertFalse((self.card / 'Roms').exists())

    def test_destination_edit_invalidates_preview(self):
        source = self.owner_file('Data.rsdk')
        live = self.card_file('Roms/ports/sonicmania/Data.rsdk')
        preview = self.manager.preview_import('sonic_mania', source)
        live.write_bytes(b'external installed edit')
        self.assert_code('CONFLICT', lambda: self.manager.apply_import(preview, confirm_idle=True, confirm_overwrite=True))
        self.assertEqual(live.read_bytes(), b'external installed edit')

    def test_undo_refuses_external_edits_before_any_write(self):
        source = self.owner_file('Data.rsdk')
        receipt = self.manager.apply_import(self.manager.preview_import('sonic_mania', source), confirm_idle=True)
        live = self.card / 'Roms/ports/sonicmania/Data.rsdk'
        live.write_bytes(b'external installed edit')
        self.assert_code('CONFLICT', lambda: self.manager.rollback_import(receipt, confirm_idle=True))
        self.assertEqual(live.read_bytes(), b'external installed edit')

    def test_missing_or_wrong_owner_data_is_rejected(self):
        self.owner_file('arbitrary.txt')
        self.assert_code('MISSING_OWNER_FILES', lambda: self.manager.preview_import('gta3', self.owner))
        self.assert_code('MISSING_OWNER_FILES', lambda: self.manager.preview_import('celeste', self.owner))
        rom = self.owner_file('baserom.us.z64')
        self.assert_code('WRONG_GAME_VERSION', lambda: self.manager.preview_import('render96ex', rom))
        self.assert_code('EXPERIMENTAL', lambda: self.manager.preview_import('gtasa', self.owner))

    def test_validated_rom_identification_uses_both_documented_digests(self):
        rom = self.owner_file('legal-test-fixture.z64', b'generated US ROM fixture')
        profiles = json.loads(DEFAULT_PROFILES.read_text())
        profile = next(p for p in profiles['ports'] if p['id'] == 'render96ex')
        profile['md5'] = hashlib.md5(rom.read_bytes()).hexdigest()
        profile['sha1'] = hashlib.sha1(rom.read_bytes()).hexdigest()
        custom = self.base / 'fixtures-only-profiles.json'
        custom.write_text(json.dumps(profiles))
        manager = PortsManager(self.card, profiles_file=custom)
        preview = manager.preview_import('render96ex', rom)
        self.assertGreater(preview.required_bytes, 1024 ** 3)
        receipt = manager.apply_import(preview, confirm_idle=True)
        self.assertEqual((self.card / 'Roms/ports/render96ex/baserom.us.z64').read_bytes(), rom.read_bytes())
        manager.rollback_import(receipt, confirm_idle=True)

    def test_gta_import_copies_only_data_and_keeps_installed_engine(self):
        for name in ('models/gta3.img', 'models/gta3.dir', 'data/gta3.dat'):
            self.owner_file(name)
        self.owner_file('gta3.exe', b'owner Windows executable fixture')
        engine = self.card_file('Roms/ports/gta3/re3', b'installed Linux engine fixture')
        preview = self.manager.preview_import('gta3', self.owner)
        receipt = self.manager.apply_import(preview, confirm_idle=True)
        self.assertEqual(engine.read_bytes(), b'installed Linux engine fixture')
        self.assertFalse((self.card / 'Roms/ports/gta3/gta3.exe').exists())
        self.manager.rollback_import(receipt, confirm_idle=True)

    def test_celeste_import_keeps_savedata_and_original_dlls_untouched(self):
        self.owner_file('Celeste.exe')
        self.owner_file('Content/Maps/test.bin')
        original = self.owner_file('FNA.dll')
        save = self.card_file('Roms/ports/celeste/savedata/0.celeste', b'user save')
        receipt = self.manager.apply_import(self.manager.preview_import('celeste', self.owner), confirm_idle=True)
        self.assertEqual(save.read_bytes(), b'user save')
        self.assertTrue(original.exists())
        self.manager.rollback_import(receipt, confirm_idle=True)
        self.assertEqual(save.read_bytes(), b'user save')

    def test_symlink_and_fat_case_collision_are_rejected(self):
        self.owner_file('Celeste.exe')
        self.owner_file('Content/Maps/test.bin')
        (self.owner / 'outside').symlink_to(self.base)
        self.assert_code('UNSAFE_PATH', lambda: self.manager.preview_import('celeste', self.owner))
        (self.owner / 'outside').unlink()
        self.owner_file('Content/Maps/TEST.bin')
        self.assert_code('CASE_COLLISION', lambda: self.manager.preview_import('celeste', self.owner))

    def test_free_space_is_checked_before_staging(self):
        source = self.owner_file('Data.rsdk')
        with patch('psp_shell.ports.shutil.disk_usage') as usage:
            usage.return_value.free = 0
            self.assert_code('STORAGE_FULL', lambda: self.manager.preview_import('sonic_mania', source))
        self.assertFalse((self.card / 'Saves').exists())

    def test_profile_snapshot_restore_and_undo_leave_saves_untouched(self):
        config = self.card_file('Roms/ports/sonicmania/Settings.ini', b'original config')
        save = self.card_file('Roms/ports/sonicmania/SaveData.bin', b'user save')
        snapshot = self.manager.snapshot_profile('sonic_mania', confirm_idle=True)
        config.write_bytes(b'tuned config')
        preview = self.manager.preview_profile_restore(snapshot)
        self.assert_code('CONFIRM_OVERWRITE', lambda: self.manager.restore_profile(snapshot, preview, confirm_idle=True))
        receipt = self.manager.restore_profile(snapshot, preview, confirm_idle=True, confirm_overwrite=True)
        self.assertEqual(config.read_bytes(), b'original config')
        self.manager.rollback_import(receipt, confirm_idle=True)
        self.assertEqual(config.read_bytes(), b'tuned config')
        self.assertEqual(save.read_bytes(), b'user save')

    def test_profile_restore_rechecks_external_changes(self):
        config = self.card_file('Roms/ports/sonicmania/Settings.ini')
        snapshot = self.manager.snapshot_profile('sonic_mania', confirm_idle=True)
        preview = self.manager.preview_profile_restore(snapshot)
        config.write_bytes(b'changed after preview')
        self.assert_code('CONFLICT', lambda: self.manager.restore_profile(snapshot, preview, confirm_idle=True, confirm_overwrite=True))

    def test_second_replacement_failure_rolls_back_first_file(self):
        self.owner_file('Celeste.exe', b'new exe fixture')
        self.owner_file('Content/test.bin', b'new content fixture')
        old = self.card_file('Roms/ports/celeste/gamedata/Celeste.exe', b'old exe fixture')
        preview = self.manager.preview_import('celeste', self.owner)
        from psp_shell import ports
        original = ports._install
        count = 0
        def fail_once(*args):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('injected storage failure')
            return original(*args)
        with patch('psp_shell.ports._install', side_effect=fail_once):
            self.assert_code('STORAGE_ERROR', lambda: self.manager.apply_import(preview, confirm_idle=True, confirm_overwrite=True))
        self.assertEqual(old.read_bytes(), b'old exe fixture')
        self.assertFalse((self.card / 'Roms/ports/celeste/gamedata/Content/test.bin').exists())


if __name__ == '__main__':
    unittest.main()
