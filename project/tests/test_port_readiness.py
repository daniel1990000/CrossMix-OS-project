# SPDX-License-Identifier: MIT
"""Source generation and stage-aware readiness do not grant launch permission."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from psp_shell.ports import DEFAULT_PROFILES, PortsManager


class PortReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manager = PortsManager(self.root)

    def write(self, name, data=b'nonempty synthetic fixture'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_marker_alone_is_not_an_executable_native_platform(self):
        self.write('Persistent/portmaster/PortMaster/pylibs/harbourmaster/platform.py', b'# NOT CODE\n# PlatformSpruce\n')
        report = self.manager.portmaster_status()
        self.assertTrue(report['legacy_marker_only'])
        self.assertEqual(report['installed_generation'], 'compatibility-or-incomplete')
        self.assertFalse(report['native_platform_support_observed'])

    def test_real_pinned_package_is_recognized_without_importing_or_executing(self):
        source = Path(os.environ.get('PORTMASTER_SOURCE_ROOT', '/workspace/portmaster-reference'))
        lock = json.loads(DEFAULT_PROFILES.with_name('ports-sources.lock.json').read_text())
        for item in lock['portmaster_gui_sources']:
            if not (source / item['path']).is_file():
                self.skipTest('Set PORTMASTER_SOURCE_ROOT to the pinned GUI source')
            data = (source / item['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
            self.write('Persistent/portmaster/' + item['path'], data)
        report = self.manager.portmaster_status()
        self.assertEqual(report['installed_generation'], 'native-package')
        self.assertTrue(report['package_registration_observed'])
        self.assertTrue(report['legacy_marker_only'])
        self.assertFalse(report['runtime_qualified'])
        self.assertFalse(report['executed'])
        self.assertFalse((self.root / 'Saves').exists())

    def test_legacy_class_and_pending_update_are_separate_observations(self):
        self.write('Persistent/portmaster/PortMaster/pylibs/harbourmaster/platform.py', b'class PlatformSpruce: pass\n')
        self.assertEqual(self.manager.portmaster_status()['installed_generation'], 'legacy-single-file')
        archive = self.write('Persistent/portmaster/PortMaster/pylibs.zip', b'pending update fixture')
        report = self.manager.portmaster_status()
        self.assertEqual(report['installed_generation'], 'self-update-pending')
        self.assertEqual(report['detected_source_generation'], 'legacy-single-file')
        archive.unlink()
        self.assertEqual(self.manager.portmaster_status()['installed_generation'], 'legacy-single-file')

    def test_malformed_platform_is_incomplete_instead_of_imported(self):
        self.write('Persistent/portmaster/PortMaster/pylibs/harbourmaster/platform.py', b'broken syntax !!!')
        self.assertEqual(self.manager.portmaster_status()['installed_generation'], 'compatibility-or-incomplete')

    def test_sonic_requires_game_library_and_supporting_library(self):
        self.write('Roms/ports/sonicmania/Data.rsdk')
        report = self.manager.installed_status('sonic_mania')
        paths = {r['path'] for r in report['support_files']}
        self.assertIn('Roms/ports/sonicmania/Game.so', paths)
        self.assertIn('Roms/ports/sonicmania/libs/libogg.so.0', paths)
        self.assertIn('SUPPORT_OR_RUNTIME_MISSING', report['readiness']['blockers'])
        self.assertFalse(report['readiness']['launch_qualified'])

    def test_prepared_render96_does_not_require_the_consumed_original_rom(self):
        self.write('Roms/ports/render96ex/res/base.zip')
        self.write('Roms/ports/render96ex/res/demos/synthetic')
        self.write('Roms/ports/render96ex/res/texts/synthetic')
        report = self.manager.installed_status('render96ex')
        self.assertFalse(report['owner_input_structure_present'])
        self.assertEqual(report['readiness']['stage'], 'prepared-inputs-observed')
        self.assertNotIn('OWNER_INPUTS_OR_PREPARATION_MISSING', report['readiness']['blockers'])
        self.assertFalse(report['runtime_qualified'])

    def test_empty_generated_resource_is_not_reported_as_prepared(self):
        self.write('Roms/ports/render96ex/res/base.zip', b'')
        self.write('Roms/ports/render96ex/res/demos/synthetic')
        self.write('Roms/ports/render96ex/res/texts/synthetic')
        self.assertFalse(self.manager.installed_status('render96ex')['readiness']['preparation_observed'])

    def test_celeste_managed_runtime_and_empty_marker_are_explicit_observations(self):
        self.write('Persistent/portmaster/PortMaster/libs/mono-6.12.0.122-aarch64.squashfs', b'hsqs' + b'fixture')
        self.write('Roms/ports/celeste/gamedata/.astc_done', b'')
        report = self.manager.installed_status('celeste')
        self.assertFalse(report['native_engine_header_present'])
        self.assertTrue(report['readiness']['preparation_observed'])
        self.assertNotIn('ENGINE_OR_MANAGED_RUNTIME_MISSING', report['readiness']['blockers'])
        self.assertIn('OWNER_INPUTS_OR_PREPARATION_MISSING', report['readiness']['blockers'])
        self.assertEqual(report['resume_capability'], 'in-game-save')
        self.assertFalse(report['readiness']['launch_qualified'])

    def test_library_enumeration_is_bounded_and_rejects_symlinks(self):
        folder = self.root / 'Roms/ports/sonicmania/libs'
        folder.mkdir(parents=True)
        for index in range(257): (folder / f'lib{index}.so').write_bytes(b'fixture')
        result = self.manager._library_directory('Roms/ports/sonicmania/libs')
        self.assertFalse(result['complete'])
        self.assertEqual(result['error']['code'], 'TOO_MANY_FILES')
        for path in folder.iterdir(): path.unlink()
        (folder / 'unsafe.so').symlink_to('/etc/passwd')
        result = self.manager._library_directory('Roms/ports/sonicmania/libs')
        self.assertFalse(result['complete'])
        self.assertEqual(result['error']['code'], 'UNSAFE_PATH')
