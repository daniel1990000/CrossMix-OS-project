# SPDX-License-Identifier: MIT
"""Review omission and stale-identity regressions on actual Git deltas."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.maintenance_review import changes, validate


class MaintenanceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Host fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.root / 'spruce/scripts').mkdir(parents=True)
        (self.root / 'spruce/scripts/runtime.sh').write_text('old\n')
        (self.root / 'outside.bin').write_bytes(b'old')
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline')
        self.base = self.git('rev-parse', 'HEAD').strip()
        (self.root / 'spruce/scripts/runtime.sh').write_text('new\n')
        (self.root / 'spruce/scripts/runtime.sh').chmod(0o755)
        (self.root / 'outside.bin').unlink()
        (self.root / 'new-file').write_bytes(b'new')
        self.git('add', '.')
        self.git('commit', '-qm', 'candidate')
        self.candidate = self.git('rev-parse', 'HEAD').strip()
        self.inventory = changes(self.root, self.base, self.candidate)
        self.packet = {'schema': 1, 'source': 'SPRUCE_SOURCE_ROOT',
                       'baseline_commit': self.base, 'candidate_commit': self.candidate,
                       'groups': [{'id': 'lifecycle', 'decision': 'hold-current-pin',
                                   'reason': 'Changed runtime authority needs a separate integration review.',
                                   'required_before_adoption': ['Exact-source regression and device lifecycle tests']}],
                       'paths': [{**record, 'group': 'lifecycle'} for record in self.inventory]}

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout

    def review(self, packet=None):
        return validate('SPRUCE_SOURCE_ROOT', self.base, self.candidate,
                        self.inventory, self.packet if packet is None else packet)

    def test_all_changes_include_deletion_addition_mode_and_outside_scope(self):
        report = self.review()
        self.assertEqual((3, 1, 2), (report['changed_paths'], report['changed_in_scope'], report['changed_outside_scope']))
        by_path = {item['path']: item for item in self.inventory}
        self.assertIsNone(by_path['outside.bin']['after'])
        self.assertIsNone(by_path['new-file']['before'])
        self.assertEqual('100755', by_path['spruce/scripts/runtime.sh']['after']['mode'])
        self.assertFalse(report['adoption_authorized'])

    def test_omitted_outside_change_fails(self):
        self.packet['paths'] = [item for item in self.packet['paths'] if item['path'] != 'outside.bin']
        with self.assertRaisesRegex(ValueError, 'omits'):
            self.review()

    def test_changed_mode_invalidates_decision(self):
        self.packet['paths'][-1]['after']['mode'] = '100644'
        # Mutate a separate copy: packet must never alter the observed inventory.
        inventory = changes(self.root, self.base, self.candidate)
        with self.assertRaisesRegex(ValueError, 'identity'):
            validate('SPRUCE_SOURCE_ROOT', self.base, self.candidate, inventory, self.packet)

    def test_wrong_candidate_invalidates_decision(self):
        self.packet['candidate_commit'] = self.base
        with self.assertRaisesRegex(ValueError, 'identities'):
            self.review()

    def test_duplicate_path_fails(self):
        self.packet['paths'].append(copy.deepcopy(self.packet['paths'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.review()

    def test_acceptance_cannot_be_smuggled_into_hold_review(self):
        self.packet['groups'][0]['decision'] = 'accept'
        with self.assertRaisesRegex(ValueError, 'hold'):
            self.review()

    def test_missing_decision_group_fails(self):
        self.packet['paths'][0]['group'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'decision group'):
            self.review()

    def test_moving_ref_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'exact commit'):
            changes(self.root, self.base, 'HEAD')

    def test_replacement_objects_do_not_substitute_candidate(self):
        self.git('replace', self.candidate, self.base)
        self.assertEqual(self.inventory, changes(self.root, self.base, self.candidate))

    def test_uncommitted_source_does_not_get_certified_as_executed(self):
        (self.root / 'spruce/scripts/runtime.sh').write_text('uncommitted\n')
        report = self.review()
        self.assertFalse(report['candidate_executed'])
        self.assertFalse(report['device_qualified'])
        self.assertEqual(self.inventory, changes(self.root, self.base, self.candidate))


if __name__ == '__main__':
    unittest.main()
