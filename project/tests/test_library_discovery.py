# SPDX-License-Identifier: MIT
"""Discovery uses existing native models and never mutates their files."""
from dataclasses import replace
import ast
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bridge.bootstrap import ExistingPyUIModels
from bridge.principal_integration import SOURCE_BLOBS, REQUIRED_PROJECT_MODULES
from psp_shell.adapters.spruce import SpruceBackend, SpruceError
import test_spruce_backend as source_fixtures
import test_state_evidence as state_fixtures


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = source_fixtures.LiveTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.card, self.provider, self.backend = self.fixture.card, self.fixture.provider, self.fixture.backend
        self.rows = [self.fixture.model]
        for index in range(150):
            path = self.card.write('Roms/GB/Game%03d.gb' % index, 'never executed fixture')
            self.rows.append(SimpleNamespace(game_system=self.fixture.system, rom_file_path=str(path),
                                             display_name='Game %03d' % index))
        self.provider.game_list = lambda _: self.rows
        self.backend.refresh()

    def test_all_pages_sorts_filters_and_random_use_the_same_complete_result(self):
        first = self.backend.games('GB', search='Game', limit=40)
        last = self.backend.games('GB', search='Game', offset=120, limit=40)
        self.assertEqual((first['total'], len(last['items'])), (150, 30))
        descending = self.backend.games('GB', search='Game', sort='title_desc')
        self.assertEqual(descending['items'][0]['label'], 'Game 149')
        with patch('psp_shell.adapters.spruce.secrets.choice', side_effect=lambda rows: rows[-1]) as choose:
            found = self.backend.random('GB', search='Game')
        self.assertEqual(len(choose.call_args.args[0]), 150)
        self.assertEqual(found['id'], last['items'][-1]['id'])
        self.assertFalse(self.backend._actions, 'Picking a game must not create a launch token')

    def test_random_excludes_unavailable_and_previous_result_and_empty_is_explicit(self):
        self.card.write('Roms/GB/Game149.gb', '')
        self.backend.refresh()
        all_rows = self.backend.games('GB', search='Game', limit=200)['items']
        excluded = all_rows[-2]['id']
        with patch('psp_shell.adapters.spruce.secrets.choice', side_effect=lambda rows: rows[-1]):
            self.assertEqual(self.backend.random('GB', search='Game', exclude_game_id=excluded)['label'], 'Game 147')
        self.assertEqual(self.backend.games('GB', search='Game', available_only=True)['total'], 149)
        with self.assertRaises(SpruceError) as error:
            self.backend.random('GB', search='nothing matches')
        self.assertEqual(error.exception.code, 'EMPTY_LIBRARY')

    def test_random_rechecks_a_disappeared_candidate_without_launching(self):
        self.backend.games('GB')
        Path(self.rows[-1].rom_file_path).unlink()
        with patch('psp_shell.adapters.spruce.secrets.choice', side_effect=lambda rows: rows[-1]):
            self.assertEqual(self.backend.random('GB', search='Game')['label'], 'Game 148')
        self.assertEqual(self.fixture.events, [])

    def test_histories_preserve_native_order_until_user_selects_sort(self):
        self.fixture.favorites.items[:] = [self.rows[20], self.rows[2], self.rows[10]]
        self.provider.recents_manager.get_recents = lambda: [self.rows[20], self.rows[2], self.rows[10]]
        for source in ('favorites', 'recent'):
            native = self.backend.games(source=source)['items']
            self.assertEqual([row['label'] for row in native], ['Game 019', 'Game 001', 'Game 009'])
            ascending = self.backend.games(source=source, sort='title_asc')['items']
            self.assertEqual([row['label'] for row in ascending], ['Game 001', 'Game 009', 'Game 019'])
            self.assertEqual(self.backend.games(source=source, search='019')['total'], 1)

    def test_jump_locates_the_matching_full_result_page_and_keeps_scope(self):
        self.rows[90].display_name = 'Mango'
        self.rows[100].display_name = 'Zebra'
        self.rows[120].display_name = '雪の冒険'
        page = self.backend.games('GB', sort='title_asc', jump='M', limit=40)
        focused = next(row for row in page['items'] if row['id'] == page['focus_id'])
        self.assertEqual(focused['label'], 'Mango')
        self.assertGreater(page['offset'], 0)
        filtered = self.backend.games('GB', search='Mango', sort='title_asc', jump='M', limit=40)
        self.assertEqual((filtered['total'], filtered['offset']), (1, 0))
        symbols = self.backend.games('GB', sort='title_asc', jump='#', limit=40)
        self.assertEqual(next(row['label'] for row in symbols['items'] if row['id'] == symbols['focus_id']), '雪の冒険')
        with self.assertRaises(SpruceError):
            self.backend.games('GB', jump='M')

    def test_focus_restore_locates_reordered_id_and_clamps_after_filter_shrink(self):
        selected = self.backend.games('GB', offset=120, limit=40)['items'][-1]['id']
        result = self.backend.games('GB', offset=120, limit=40, sort='title_desc', focus_game_id=selected)
        self.assertEqual(result['offset'], 0)
        self.assertEqual(result['focus_id'], selected)
        missing = self.backend.games('GB', search='Alpha', offset=120, limit=40, focus_game_id=selected)
        self.assertEqual((missing['offset'], missing['total'], missing['focus_id']), (0, 1, ''))

    def test_known_game_lookup_does_not_enumerate_unvisited_systems(self):
        selected = self.backend.games('GB')['items'][0]
        other = SimpleNamespace(system_name='OTHER', display_name='Other')
        self.card.write('Emu/OTHER/config.json', '{"label":"Other","extlist":"gb"}')
        self.provider.system_manager.get_active_systems = lambda: [self.fixture.system, other]
        with patch.object(self.provider, 'game_list', side_effect=AssertionError('unvisited system scanned')):
            self.assertEqual(self.backend.game_info(selected['id'])['id'], selected['id'])
        self.rows[0].display_name = 'Changed by native menu'
        self.backend.refresh()
        self.assertEqual(self.backend.games('GB')['items'][0]['label'], 'Changed by native menu')

    def test_history_model_retained_across_refresh_still_checks_own_system_collisions(self):
        pairs = []
        for name in ('Case.gb', 'case.gb'):
            path = self.card.write('Roms/GB/' + name, 'fixture')
            pairs.append(SimpleNamespace(game_system=self.fixture.system, rom_file_path=str(path), display_name=name))
        self.provider.game_list = lambda _: pairs
        self.fixture.favorites.items[:] = pairs
        self.backend.refresh()
        selected = self.backend.favorites()[0]['id']
        self.backend.refresh()
        result = self.backend.resolve_game(selected)
        self.assertFalse(result['launchable'])
        self.assertEqual(result['gate_reason'], 'GAME_REQUIRES_REVIEW')

    def test_native_collections_reuse_ready_owner_without_constructing_or_writing(self):
        ready = threading.Event(); ready.set()
        calls = []
        self.provider.collections_manager = SimpleNamespace(_init_event=ready,
            get_collection_names=lambda: ['Weekend', 'Empty'],
            get_games_in_collection=lambda name: calls.append(name) or ([self.rows[4], self.rows[2]] if name == 'Weekend' else []),
            initialize=lambda *_: self.fail('collection manager reinitialized'),
            save_to_file=lambda: self.fail('native collection was rewritten'))
        collections = self.backend.collections()
        self.assertEqual(calls, [], 'Collection listing must not enumerate every collection')
        identifier = collections[0]['id']
        self.assertNotEqual(identifier, 'Weekend')
        result = self.backend.games(source='collection', collection_id=identifier)
        self.assertEqual([row['label'] for row in result['items']], ['Game 003', 'Game 001'])
        self.assertEqual(self.backend.games(source='collection', collection_id=identifier, search='001')['total'], 1)
        self.assertEqual(self.backend.games(source='collection', collection_id=collections[1]['id'])['total'], 0)
        with self.assertRaises(SpruceError):
            self.backend.games(source='collection', collection_id='collection:missing')
        ready.clear()
        with self.assertRaises(SpruceError) as error:
            self.backend.collections()
        self.assertEqual(error.exception.code, 'MODELS_NOT_READY')
        self.assertEqual(calls, ['Weekend', 'Weekend', 'Empty'])

    def test_snapshot_collections_are_bounded_read_only_and_use_native_basename_order(self):
        target = self.card.write('Collections/collections.json', json.dumps([
            {'collection_name': '../Owner label', 'game_list': [
                {'game_system_name': 'GB', 'rom_file_path': '/mnt/SDCARD/Roms/GB/Game003.gb'},
                {'game_system_name': 'GB', 'rom_file_path': '/mnt/SDCARD/Roms/GB/Alpha.gb'},
                {'game_system_name': 'GB', 'rom_file_path': '/outside/nonexistent.gb'}]},
            {'collection_name': 'Empty', 'game_list': []}]))
        before = self.card.snapshot()
        backend = SpruceBackend(self.card.root)
        collections = backend.collections()
        rows = backend.games(source='collection', collection_id=collections[0]['id'])['items']
        self.assertEqual([row['label'] for row in rows], ['Alpha', 'Game003'])
        self.assertEqual(self.card.snapshot(), before)
        target.write_text('{bad native json')
        self.assertEqual(backend.collections(), [])
        self.assertEqual(target.read_text(), '{bad native json')
        target.unlink()
        self.assertEqual(backend.collections(), [])
        self.assertFalse(target.exists())

    def test_collection_symlink_escape_and_oversized_arrays_never_supply_records(self):
        with tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / 'collections.json'
            path.write_text('[{"collection_name":"outside","game_list":[]}]')
            (self.card.root / 'Collections').symlink_to(outside, target_is_directory=True)
            self.assertEqual(SpruceBackend(self.card.root).collections(), [])
        (self.card.root / 'Collections').unlink()
        self.card.write('Collections/collections.json', json.dumps([{'collection_name':str(i), 'game_list':[]} for i in range(257)]))
        self.assertEqual(SpruceBackend(self.card.root).collections(), [])

    def test_invalid_query_combinations_are_rejected(self):
        for params in ({'source':'unknown'}, {'sort':'unknown'}, {'source':'collection'},
                       {'collection_id':'native-name'}, {'available_only':1}, {'jump':'AB','sort':'title_asc'}):
            with self.subTest(params=params), self.assertRaises(SpruceError):
                self.backend.games(**params)


class ResumeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = source_fixtures.LiveTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.backend, self.provider, self.card = self.fixture.backend, self.fixture.provider, self.fixture.card
        self.game_id = self.fixture.game['id']

    def install_evidence(self):
        record, profile = self.fixture.evidence()
        self.backend.set_resume_evidence({self.game_id: record}, {'gambatte': profile})
        self.provider.mode_actions = {preset: {'resume': lambda *_: self.fail('wrong Resume handler reached')}
                                      for preset in ('gambatte', 'mgba')}

    def test_cached_preset_change_cannot_mint_resume_for_a_different_handler(self):
        self.install_evidence()
        self.card.config['menuOptions']['Emulator_64']['selected'] = 'mgba'; self.card.save_config()
        result = self.backend.resolve_game(self.game_id, mode='resume')
        self.assertEqual(result['preset_id'], 'mgba')
        self.assertFalse(result['resume_available'])
        self.assertFalse(result['launchable'])
        self.assertEqual(result['gate_reason'], 'RESUME_UNAVAILABLE')
        self.assertFalse(self.backend._actions)

    def test_descriptor_changes_during_resolution_and_validation_are_rejected(self):
        self.install_evidence()
        original = self.provider.resolve_game
        def change_after_read(*args):
            result = original(*args)
            self.card.config['menuOptions']['Emulator_64']['selected'] = 'mgba'; self.card.save_config()
            return result
        with patch.object(self.provider, 'resolve_game', side_effect=change_after_read):
            with self.assertRaises(SpruceError) as error:
                self.backend.resolve_game(self.game_id, mode='resume')
        self.assertEqual(error.exception.code, 'STALE_ACTION')
        self.card.config['menuOptions']['Emulator_64']['selected'] = 'gambatte'; self.card.save_config()
        action = self.backend.resolve_game(self.game_id, mode='resume')['action_id']
        with patch.object(self.provider, 'resolve_game', side_effect=change_after_read):
            with self.assertRaises(SpruceError) as error:
                self.backend.execute_action(action, mode='resume', release_ui=False)
        self.assertEqual(error.exception.code, 'STALE_ACTION')
        self.assertEqual(self.fixture.events, [])

    def test_bulk_recents_do_not_hash_state_inputs_but_explicit_selection_does(self):
        self.install_evidence()
        with patch('psp_shell.adapters.spruce._sha_file', side_effect=AssertionError('bulk hash')):
            row = self.backend.recent()[0]
            self.assertFalse(row['resume_available'])
            self.assertTrue(row['state_verification_required'])
            self.assertEqual(row['resume_reason'], 'VERIFICATION_REQUIRED')
        self.assertTrue(self.backend.game_info(self.game_id)['resume_available'])

    def test_mutated_or_replaced_native_model_cannot_change_normal_or_resume_target(self):
        self.install_evidence()
        original = self.fixture.model.rom_file_path
        for mode in ('normal', 'resume'):
            for replacement in (False, True):
                with self.subTest(mode=mode, replacement=replacement):
                    self.fixture.model.rom_file_path = original
                    self.provider.models[self.game_id] = self.fixture.model
                    action = self.backend.resolve_game(self.game_id, mode=mode)['action_id']
                    if replacement:
                        self.provider.models[self.game_id] = SimpleNamespace(**vars(self.fixture.model))
                    else:
                        self.fixture.model.rom_file_path = str(self.card.root / 'Roms/GB/nested/Beta.gbc')
                    with self.assertRaises(SpruceError) as error:
                        self.backend.execute_action(action, mode=mode, release_ui=False)
                    self.assertEqual(error.exception.code, 'STALE_ACTION')
        self.assertEqual(self.fixture.events, [])

    def test_sealed_state_capability_cannot_follow_cached_preset_to_another_handler(self):
        state = state_fixtures.StateEvidenceTests(); state.setUp(); self.addCleanup(state.doCleanups)
        state.card = self.card.root; state.game = state.card / 'Roms/GB/Alpha.gb'
        state.engine = state.card / 'Emu/GB/engine'
        state.states = state.card / 'Saves/states'; state.states.mkdir(parents=True)
        state.state = state.states / 'checkpoint.ppst'; state.state.write_bytes(b'disposable state')
        state.native_config = state.card / 'native.ini'; state.native_config.write_bytes(b'native fixture')
        state.profile = replace(state.profile, preset_id='gambatte', sd_root=state.card, executable=state.engine,
            engine_sha256=state.sha(state.engine), state_roots=(state.states,),
            config_hashes=((str(state.native_config), state.sha(state.native_config)),))
        state.identity = replace(state.identity, game_id=self.game_id, rom_path=state.game, rom_sha256=state.sha(state.game))
        evidence = state.verified()
        self.backend.set_verified_resume_evidence({self.game_id:evidence})
        self.provider.mode_actions = {preset:{'resume':lambda *_:self.fail('wrong handler')} for preset in ('gambatte','mgba')}
        self.card.config['menuOptions']['Emulator_64']['selected'] = 'mgba'; self.card.save_config()
        result = self.backend.resolve_game(self.game_id, mode='resume')
        self.assertEqual(result['resume_reason'], 'STATE_IDENTITY_MISMATCH')
        self.assertFalse(result['launchable'])


class CollectionSourceContractTests(unittest.TestCase):
    def test_independent_runtime_inventory_covers_every_shipped_python_module(self):
        from tools.build_payload import build_payload
        with tempfile.TemporaryDirectory(prefix='qualified-payload-inventory-') as temporary:
            destination = Path(temporary) / 'payload'
            build_payload(Path(__file__).resolve().parents[1], destination)
            actual = {path.relative_to(destination).as_posix() for path in destination.rglob('*.py')}
        self.assertEqual(len(REQUIRED_PROJECT_MODULES), len(set(REQUIRED_PROJECT_MODULES)))
        self.assertEqual(actual, set(REQUIRED_PROJECT_MODULES))

    def test_new_native_owner_is_pinned_and_initialized_binding_passes_it_through(self):
        path = 'App/PyUI/main-ui/menus/games/utils/collections_manager.py'
        self.assertEqual(SOURCE_BLOBS[path], 'fff05e158316e875096b4f07b35162a2acf2afd9')
        root = Path(os.environ.get('SPRUCE_SOURCE_ROOT', '/workspace/trimui-sources/spruce'))
        if not (root / path).is_file():
            self.skipTest('Provide untouched pinned SPRUCE_SOURCE_ROOT')
        tree = ast.parse((root / path).read_text())
        native_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'CollectionsManager')
        native_class.body = [node for node in native_class.body if isinstance(node, ast.FunctionDef) and
                             node.name in {'_wait_for_init', 'get_collection_names', 'get_games_in_collection'}]
        namespace = {}
        exec(compile(ast.Module(body=[native_class], type_ignores=[]), str(root / path), 'exec'), namespace)
        ready = threading.Event(); ready.set()
        native = namespace['CollectionsManager']
        native._init_event = ready
        native._collections = [SimpleNamespace(collection_name='Owner collection', game_list=['exact source member'])]
        native.load_entries_as_rom_info = classmethod(lambda cls, entries: entries)
        self.assertEqual(native.get_collection_names(), ['Owner collection'])
        self.assertEqual(native.get_games_in_collection('Owner collection'), ['exact source member'])
        self.assertEqual(native.get_games_in_collection('Missing'), [])
        manager = SimpleNamespace(_init_event=ready)
        models = ExistingPyUIModels(SimpleNamespace(get_active_systems=lambda: []), lambda _: [],
            SimpleNamespace(_init_event=ready, get_favorites=lambda: []),
            SimpleNamespace(_init_event=ready, get_recents=lambda: []), collections_manager=manager)
        with patch('psp_shell.adapters.spruce.PyUIModelProvider') as provider:
            models.provider('/unused', device=object(), release_resources=lambda:None, quiescent=lambda:True)
        self.assertIs(provider.call_args.kwargs['collections_manager'], manager)


if __name__ == '__main__':
    unittest.main()
