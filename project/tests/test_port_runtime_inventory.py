# SPDX-License-Identifier: MIT
"""Generated fixtures only; inventory never executes installed port scripts."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from psp_shell.adapters.spruce import PyUIModelProvider, SpruceBackend, SpruceError
from psp_shell.ports import DEFAULT_PROFILES, PortError, PortsManager, _fingerprint


class PortRuntimeInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.card = self.root / 'card'
        self.card.mkdir()
        self.manager = PortsManager(self.card)

    def write(self, relative, data=b'generated fixture'):
        path = self.card / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def assert_code(self, code, operation):
        with self.assertRaises(PortError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def prepare_library(self):
        self.write('Emu/PORTS/config.json', json.dumps({'label': 'Ports',
            'launch': '../../spruce/scripts/emu/standard_launch.sh', 'extlist': 'sh',
            'default_emulator': 'sh', 'alternativeFolderNames': ['ports'],
            'devices': ['TRIMUI_A133P']}).encode())
        self.write('spruce/scripts/emu/standard_launch.sh', b'#!/bin/sh\nexit 72\n')
        self.script = self.write('Roms/ports/Sonic Mania.sh', b'#!/bin/sh\nexit 73\n')
        self.write('App/PortMaster/config.json', b'{"label":"PortMaster","launch":"launch.sh"}')
        self.write('App/PortMaster/launch.sh', b'#!/bin/sh\nexit 74\n')

    def live_backend(self):
        self.prepare_library()
        events = []
        system = SimpleNamespace(system_name='PORTS', display_name='Ports')
        model = SimpleNamespace(game_system=system, rom_file_path=str(self.script), display_name='Sonic Mania')
        provider = PyUIModelProvider(self.card,
            system_manager=SimpleNamespace(get_active_systems=lambda: [system]),
            game_list=lambda _: [model], device=SimpleNamespace(run_game=lambda item: events.append(('game', item))),
            favorites_manager=SimpleNamespace(get_favorites=lambda: []),
            recents_manager=SimpleNamespace(get_recents=lambda: []), release_resources=lambda: events.append(('release', None)),
            quiescent=lambda: True, tool_list=lambda: [{'id': 'app:PortMaster', 'label': 'PortMaster'}],
            tool_actions={'app:PortMaster': lambda: events.append(('tool', None))})
        return SpruceBackend(self.card, read_only=False, managers=provider), model, events

    def test_missing_and_present_inputs_do_not_imply_runtime_qualification(self):
        missing = self.manager.installed_status('sonic_mania')
        self.assertFalse(missing['owner_input_structure_present'])
        self.assertFalse(missing['native_engine_header_present'])
        self.write('Roms/ports/sonicmania/Data.rsdk')
        header = bytearray(64)
        header[:6] = b'\x7fELF\x02\x01'
        header[18:20] = (183).to_bytes(2, 'little')
        self.write('Roms/ports/sonicmania/sonicmania', header)
        self.write('Roms/ports/Sonic Mania.sh', b'#!/bin/sh\nexit 1\n')
        before = {str(p.relative_to(self.card)): p.read_bytes() for p in self.card.rglob('*') if p.is_file()}
        status = self.manager.installed_status('sonic_mania')
        self.assertTrue(status['owner_input_structure_present'])
        self.assertTrue(status['native_engine_header_present'])
        self.assertFalse(status['launcher']['pinned_text_matches'])
        for key in ('runtime_qualified', 'source_binary_correspondence_verified', 'distribution_cleared', 'executed'):
            self.assertFalse(status[key])
        self.assertIsNone(status['measured_fps'])
        self.assertEqual(before, {str(p.relative_to(self.card)): p.read_bytes() for p in self.card.rglob('*') if p.is_file()})
        self.assertFalse((self.card / 'Saves').exists())

    def test_celeste_runtime_is_observed_without_mounting_or_evaluating_control_files(self):
        self.write('Persistent/portmaster/PortMaster/libs/mono-6.12.0.122-aarch64.squashfs', b'hsqs' + b'fixture' * 10)
        self.write('Persistent/portmaster/PortMaster/control.txt', b'$(touch MUST_NOT_RUN)\n')
        self.write('Roms/ports/celeste/gamedata/Celeste.exe')
        self.write('Roms/ports/celeste/gamedata/Content/fixture')
        result = self.manager.installed_status('celeste')
        self.assertTrue(result['runtime_files'][0]['squashfs_magic'])
        self.assertTrue(result['owner_input_structure_present'])
        self.assertFalse(result['portmaster']['native_platform_support_observed'])
        self.assertFalse(result['runtime_qualified'])
        self.assertFalse((self.card / 'MUST_NOT_RUN').exists())

    def test_arm32_engine_is_not_reported_as_native_aarch64_header(self):
        header = bytearray(64)
        header[:6] = b'\x7fELF\x01\x01'
        header[18:20] = (40).to_bytes(2, 'little')
        self.write('Roms/ports/gta3/re3', header)
        status = self.manager.installed_status('gta3')
        self.assertFalse(status['native_engine_header_present'])
        self.assertEqual(len(status['engine_alternatives']), 2)

    def test_symlink_ancestor_and_fifo_are_rejected_without_blocking(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'Data.rsdk').write_bytes(b'outside data')
        target = self.card / 'Roms/ports/sonicmania'
        target.parent.mkdir(parents=True)
        target.symlink_to(outside, target_is_directory=True)
        self.assert_code('UNSAFE_PATH', lambda: _fingerprint(target / 'Data.rsdk'))
        target.unlink()
        target.mkdir()
        os.mkfifo(target / 'Data.rsdk')
        status = self.manager.installed_status('sonic_mania')
        self.assertEqual(status['owner_files'][0]['error']['code'], 'UNSAFE_PATH')

    def test_growing_file_is_detected_with_a_fixed_initial_read_budget(self):
        path = self.write('Roms/ports/sonicmania/Data.rsdk', b'abcdefgh')
        real_sha = hashlib.sha256
        mutated = False
        class GrowingHash:
            def __init__(self):
                self.digest = real_sha()
            def update(self, chunk):
                nonlocal mutated
                self.digest.update(chunk)
                if not mutated:
                    mutated = True
                    with path.open('ab') as output:
                        output.write(b'unexpected growth')
            def hexdigest(self):
                return self.digest.hexdigest()
        with patch('psp_shell.ports.CHUNK', 4), patch('psp_shell.ports.hashlib.sha256', GrowingHash):
            self.assert_code('CONFLICT', lambda: _fingerprint(path))

    def test_snapshot_route_preserves_backend_launch_block_and_lexical_system_path(self):
        self.prepare_library()
        backend = SpruceBackend(self.card)
        context = self.manager.resolve_existing_port('sonic_mania', backend)
        self.assertFalse(context['launchable'])
        self.assertEqual(context['gate_reason'], 'SNAPSHOT_READ_ONLY')
        self.assertIn('/Emu/PORTS/../../spruce/', context['executable'])
        self.assertFalse(self.manager.resolve_existing_portmaster(backend)['launchable'])

    def test_existing_live_tokens_and_lifecycle_remain_owned_by_backend(self):
        backend, model, events = self.live_backend()
        game = self.manager.resolve_existing_port('sonic_mania', backend)
        manager = self.manager.resolve_existing_portmaster(backend)
        self.assertEqual(events, [])
        self.assertTrue(game['launchable'])
        self.assertTrue(manager['launchable'])
        backend.execute_action(game['action_id'], release_ui=False)
        backend.execute_action(manager['action_id'], release_ui=False)
        self.assertEqual(events, [('game', model), ('tool', None)])
        with self.assertRaises(SpruceError):
            backend.execute_action(game['action_id'])

    def test_stale_library_action_still_fails_in_existing_backend(self):
        backend, _, events = self.live_backend()
        action = self.manager.resolve_existing_port('sonic_mania', backend)
        self.script.write_bytes(b'changed installed script')
        with self.assertRaises(SpruceError) as caught:
            backend.execute_action(action['action_id'])
        self.assertEqual(caught.exception.code, 'STALE_ACTION')
        self.assertEqual(events, [])

    def test_wrong_card_missing_item_and_experimental_recipe_are_rejected(self):
        other = self.root / 'other'
        other.mkdir()
        self.assert_code('INVALID_BACKEND', lambda: self.manager.resolve_existing_port('sonic_mania', SpruceBackend(other)))
        self.assert_code('EXISTING_PORT_UNAVAILABLE', lambda: self.manager.resolve_existing_port('sonic_mania', SpruceBackend(self.card)))
        self.assert_code('EXPERIMENTAL', lambda: self.manager.installed_status('gtasa'))

    def test_source_lock_pins_scripts_and_shipped_profiles_keep_all_gates_false(self):
        lock = json.loads((DEFAULT_PROFILES.parent / 'ports-sources.lock.json').read_text())
        self.assertGreaterEqual(len(lock['sources']), 17)
        for profile in self.manager.profiles():
            self.assertFalse(profile['runtime_qualified'])
            self.assertFalse(profile['distribution_cleared'])
            self.assertIsNone(profile['measured_fps'])
            if profile['enabled']:
                script = next(s for s in lock['sources'] if s['port_id'] == profile['id'] and s['path'].endswith('.sh'))
                self.assertEqual(profile['installation']['launcher_source_sha256'], script['sha256'])
                self.assertEqual(len(script['commit']), 40)
