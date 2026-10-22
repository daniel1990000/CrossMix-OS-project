# SPDX-License-Identifier: MIT
"""Large synthetic libraries exercise the actual adapters and UI focus model."""
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from psp_shell.adapters.spruce import SpruceBackend, SpruceError
from psp_shell.ui.model import NavigationModel
from tools.library_benchmark import create_library, live_backend, measure


class LargeLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='large-library-tests-')
        cls.root = Path(cls.temporary.name) / 'card'
        cls.models = create_library(cls.root, 10000)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def backend(self, models=None):
        return live_backend(self.root, self.models if models is None else models)

    def test_ten_thousand_entries_have_complete_stable_pagination(self):
        backend = self.backend()
        with mock.patch.object(backend.provider, 'game_list', wraps=backend.provider.game_list) as source:
            identifiers = []
            for offset in range(0, 10000, 200):
                page = backend.games('GB', offset=offset, limit=200)
                self.assertEqual(page['total'], 10000)
                identifiers.extend(row['id'] for row in page['items'])
            self.assertEqual(len(set(identifiers)), 10000)
            self.assertEqual(source.call_count, 1, 'Paging must reuse the initialized list snapshot')
            self.assertEqual(backend.games('GB', offset=10000)['items'], [])

    def test_non_latin_and_canonically_equivalent_search(self):
        backend = self.backend()
        for text in ('雪の冒険', 'العربية', '한국어', 'CAFE\u0301'):
            with self.subTest(text=text):
                self.assertEqual(backend.games('GB', search=text)['total'], 2500)

    def test_long_titles_remain_bounded_and_identified_by_path(self):
        rows = self.backend().games('GB', search='Long title', limit=200)
        self.assertEqual(rows['total'], 100)
        self.assertTrue(all(200 < len(r['label']) < 512 for r in rows['items']))
        self.assertEqual(len({r['id'] for r in rows['items']}), 100)

    def test_bad_individual_models_do_not_hide_the_rest_of_the_library(self):
        from types import SimpleNamespace
        invalid = [SimpleNamespace(rom_file_path=None),
                   SimpleNamespace(game_system=self.models[0].game_system,
                                   rom_file_path='/missing/non-game.gb', display_name='Missing'),
                   SimpleNamespace(game_system=self.models[0].game_system,
                                   rom_file_path=self.models[0].rom_file_path, display_name='\ud800')]
        backend = self.backend(invalid + self.models[:2])
        self.assertEqual(backend.games('GB')['total'], 2)
        self.assertEqual(len(backend.provider.warnings), 3)

    def test_empty_live_library_is_cached_until_explicit_refresh(self):
        backend = self.backend([])
        with mock.patch.object(backend.provider, 'game_list', wraps=backend.provider.game_list) as source:
            self.assertEqual(backend.games('GB')['total'], 0)
            self.assertEqual(backend.games('GB')['total'], 0)
            self.assertEqual(source.call_count, 1)
            backend.refresh()
            backend.games('GB')
            self.assertEqual(source.call_count, 2)

    def test_refresh_releases_old_models_and_reloads_existing_manager(self):
        models = self.models[:2].copy()
        backend = self.backend(models)
        old = backend.games('GB')['items'][0]['id']
        self.assertIn(old, backend.provider.models)
        models.clear()
        backend.refresh()
        self.assertNotIn(old, backend.provider.models)
        self.assertEqual(backend.games('GB')['total'], 0)

    def test_duplicate_basename_keeps_two_ids_and_upstream_preset_semantics(self):
        import copy
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'card'
            models = create_library(root, 2)
            source = Path(models[0].rom_file_path)
            second = root / 'Roms/GB/another' / source.name
            second.parent.mkdir()
            second.write_bytes(source.read_bytes())
            models[1] = copy.copy(models[0])
            models[1].rom_file_path = str(second)
            config_path = root / 'Emu/GB/config.json'
            config = json.loads(config_path.read_text())
            config['menuOptions'] = {'Emulator_64': {'options': ['fixture', 'alternate'],
                'selected': 'fixture', 'overrides': {source.name: 'alternate'}}}
            config_path.write_text(json.dumps(config))
            rows = live_backend(root, models).games('GB')['items']
            self.assertEqual(len({r['id'] for r in rows}), 2)
            self.assertEqual({r['selected_preset'] for r in rows}, {'alternate'})

    def test_infinite_duplicate_manager_is_stopped_by_input_budget(self):
        backend = self.backend()
        backend.provider.max_entries = 4
        backend.provider.game_list = lambda _: itertools.repeat(self.models[0])
        with self.assertRaises(SpruceError) as error:
            backend.games('GB')
        self.assertEqual(error.exception.code, 'MODEL_LIMIT')
        self.assertFalse(backend.provider._library_cache)

    def test_empty_file_is_visible_for_review_but_cannot_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'card'
            models = create_library(root, 1)
            Path(models[0].rom_file_path).write_bytes(b'')
            backend = live_backend(root, models)
            backend.read_only = False
            row = backend.games('GB')['items'][0]
            self.assertEqual(row['availability'], 'review_required')
            self.assertIn('EMPTY_ROM', row['warnings'])
            self.assertFalse(row['capabilities']['launch'])
            self.assertFalse(backend.resolve_game(row['id'])['launchable'])

    def test_file_truncated_after_cache_or_action_preview_cannot_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'card'
            models = create_library(root, 1)
            backend = live_backend(root, models)
            backend.read_only = False
            row = backend.games('GB')['items'][0]
            action = backend.resolve_game(row['id'])
            self.assertTrue(action['launchable'])
            Path(models[0].rom_file_path).write_bytes(b'')
            self.assertFalse(backend.resolve_game(row['id'])['launchable'])
            with mock.patch.object(backend.provider.device, 'run_game') as launch:
                with self.assertRaises(SpruceError):
                    backend.execute_action(action['action_id'])
                launch.assert_not_called()

    def test_repeated_failed_system_loads_do_not_retain_partial_bindings(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'card'
            models = create_library(root, 2)
            backend = live_backend(root, models)
            backend.provider.max_entries = 3
            backend.games('GB')
            original = set(backend.provider.models)
            for system in ('GB2', 'GB3'):
                descriptor = root / f'Emu/{system}/config.json'
                descriptor.parent.mkdir()
                descriptor.write_bytes((root / 'Emu/GB/config.json').read_bytes())
                others = []
                for index in range(2):
                    rom = root / f'Roms/{system}/{index}.gb'
                    rom.parent.mkdir(parents=True, exist_ok=True)
                    rom.write_bytes(b'fixture')
                    others.append(SimpleNamespace(game_system=SimpleNamespace(system_name=system),
                                                  rom_file_path=str(rom), display_name=str(index)))
                backend.provider.game_list = lambda name, rows=others: rows
                with self.assertRaises(SpruceError): backend.games(system)
                self.assertEqual(set(backend.provider.models), original)
            backend.refresh()
            self.assertEqual(backend.provider.models, {})

    def test_aggregate_live_cache_cannot_grow_past_its_budget(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'card'
            models = create_library(root, 3)
            descriptor = root / 'Emu/GB2/config.json'
            descriptor.parent.mkdir()
            descriptor.write_bytes((root / 'Emu/GB/config.json').read_bytes())
            others = []
            for index in range(3):
                rom = root / f'Roms/GB2/game-{index}.gb'
                rom.parent.mkdir(parents=True, exist_ok=True)
                rom.write_bytes(b'fixture')
                others.append(SimpleNamespace(game_system=SimpleNamespace(system_name='GB2'),
                                              rom_file_path=str(rom), display_name=str(index)))
            backend = live_backend(root, models)
            backend.provider.game_list = lambda name: models if name == 'GB' else others
            backend.provider.max_entries = 4
            backend.games('GB')
            with self.assertRaises(SpruceError):
                backend.games('GB2')
            self.assertLessEqual(sum(len(rows) for rows in backend.provider._library_cache.values()), 4)
            self.assertLessEqual(len(backend.provider.models), 4)

    def test_empty_and_corrupt_snapshot_descriptors_are_isolated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'card'
            create_library(root, 2)
            for system, content in (('EMPTY', ''), ('CORRUPT', '{broken')):
                descriptor = root / f'Emu/{system}/config.json'
                descriptor.parent.mkdir()
                descriptor.write_text(content)
            backend = SpruceBackend(root)
            self.assertEqual(backend.games()['total'], 2)
            self.assertEqual(len(backend.provider.warnings), 2)

    def test_refresh_preserves_selected_identity_on_a_large_library_page(self):
        backend = self.backend()
        model = NavigationModel()
        model._games_view, model._system_id = 'system', 'GB'
        command = model._query(offset=500)
        model.receive(command, backend.games('GB', offset=500, limit=model.PAGE_SIZE))
        for _ in range(7):
            model.handle('down')
        selected = model.snapshot().selected_item.id
        backend.refresh()
        command = model._query(offset=500, keep_focus=True)
        model.receive(command, backend.games('GB', offset=500, limit=model.PAGE_SIZE))
        self.assertEqual(model.snapshot().selected_item.id, selected)

    def test_benchmark_records_real_samples_without_timing_assertions(self):
        result = measure(self.backend(self.models[:20]), repeats=2)
        self.assertEqual(result['total'], 20)
        self.assertEqual(result['page']['count'], 2)
        self.assertGreater(result['startup_ms'], 0)

    def test_fixture_refuses_existing_or_symlink_destination(self):
        with self.assertRaises(ValueError):
            create_library(self.root, 1)
        with tempfile.TemporaryDirectory() as temporary:
            link = Path(temporary) / 'link'
            link.symlink_to(self.root, target_is_directory=True)
            with self.assertRaises(ValueError):
                create_library(link / 'child', 1)
