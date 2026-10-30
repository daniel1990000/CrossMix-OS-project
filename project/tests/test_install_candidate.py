# SPDX-License-Identifier: MIT
"""Offline preparation regression tests. Fixtures establish no target behavior."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from install import build_candidate as builder


class InstallCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def selectors(self, directory, body="return None"):
        target = directory / builder.release.PAYLOAD_ROOT / "app/bridge"
        target.mkdir(parents=True, exist_ok=True)
        for name in ("qualified_runtime.py", "experimental_runtime.py"):
            (target / name).write_text('def configuration():\n    """Fixed unavailable fixture."""\n    ' + body + '\n')

    def test_retained_permission_is_the_recorded_private_scope(self):
        review = builder.retained_source_review()
        self.assertEqual(review.scope, "private-source-candidate")
        self.assertIn(builder.PERMISSION_SHA256, review.evidence_reference)

    def test_arbitrary_permission_file_cannot_authorize_composition(self):
        path = self.root / "permission.json"
        path.write_text('{"private_noncommercial_source_candidate_authorized":true}')
        with mock.patch.object(builder, "PERMISSION_PATH", path):
            with self.assertRaisesRegex(ValueError, "decision changed"):
                builder.retained_source_review()

    def test_disabled_selectors_are_checked_without_execution(self):
        self.selectors(self.root)
        builder.require_disabled_selectors(self.root)
        path = self.root / builder.release.PAYLOAD_ROOT / 'app/bridge/qualified_runtime.py'
        path.write_text('raise RuntimeError("must not execute")\ndef configuration():\n    return None\n')
        builder.require_disabled_selectors(self.root)

    def test_enabled_selector_refused(self):
        self.selectors(self.root, 'return {"hardware_qualified": True}')
        with self.assertRaisesRegex(ValueError, "unavailable runtime"):
            builder.require_disabled_selectors(self.root)

    def test_redefined_or_decorated_selector_refused(self):
        self.selectors(self.root)
        path = self.root / builder.release.PAYLOAD_ROOT / 'app/bridge/qualified_runtime.py'
        path.write_text('def configuration():\n    return None\ndef configuration():\n    return True\n')
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            builder.require_disabled_selectors(self.root)
        path.write_text('@turn_on\ndef configuration():\n    return None\n')
        with self.assertRaisesRegex(ValueError, "unavailable runtime"):
            builder.require_disabled_selectors(self.root)

    def test_linked_input_and_wrong_archive_refused(self):
        source = self.root / 'archive.7z'
        source.write_bytes(b'not a spruce archive')
        with self.assertRaisesRegex(ValueError, 'size mismatch'):
            builder.check_base_archive(source)
        link = self.root / 'link'
        link.symlink_to(source)
        with self.assertRaisesRegex(ValueError, 'non-link'):
            builder.sha256_file(link)

    def test_deployment_preimage_and_source_mode_are_bound(self):
        source = self.root / 'source'
        candidate = self.root / 'candidate'
        (source / 'spruce').mkdir(parents=True)
        (candidate / 'tree/spruce').mkdir(parents=True)
        old = source / 'spruce/runtime.sh'
        old.write_bytes(b'old\n')
        old.chmod(0o755)
        new = candidate / 'tree/spruce/runtime.sh'
        new.write_bytes(b'new\n')
        manifest = {'changes': [{'path': 'spruce/runtime.sh',
                               'before_sha256': builder.sha256_file(old),
                               'after_sha256': builder.sha256_file(new)}]}
        result = builder.deployment_files(candidate, source, manifest)
        self.assertEqual(result[0]['intended_posix_mode'], '0755')
        self.assertEqual(result[0]['operation'], 'replace-exact-preimage')
        old.write_bytes(b'later source\n')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            builder.deployment_files(candidate, source, manifest)

    def test_unexpected_new_source_and_symlinks_refused(self):
        tree = self.root / 'candidate/tree'
        tree.mkdir(parents=True)
        (tree / 'unexpected.sh').write_text('no')
        with self.assertRaisesRegex(ValueError, 'unreviewed new'):
            builder.deployment_files(self.root / 'candidate', self.root, {'changes': []})
        (tree / 'unexpected.sh').unlink()
        (tree / 'link').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            builder.tree_inventory(tree)

    def test_full_base_public_ca_bundle_is_inventoried_not_executed(self):
        (self.root / 'cacert.pem').write_text('public certificate fixture')
        files = builder.tree_inventory(self.root)
        self.assertEqual(files[0]['path'], 'cacert.pem')
        self.assertEqual(files[0]['sha256'], hashlib.sha256(b'public certificate fixture').hexdigest())

    def test_full_base_windows_unsafe_and_case_colliding_names_refused(self):
        for name in ('bad:name', 'CON.txt', 'trailing.', 'bad?name'):
            with self.subTest(name=name):
                path = self.root / name
                path.write_text('fixture')
                with self.assertRaisesRegex(ValueError, 'unsafe full-base path'):
                    builder.tree_inventory(self.root)
                path.unlink()
        (self.root / 'Case').write_text('a')
        (self.root / 'case').write_text('b')
        with self.assertRaisesRegex(ValueError, 'case-colliding'):
            builder.tree_inventory(self.root)

    def test_empty_windows_reserved_directory_refused(self):
        (self.root / 'CON').mkdir()
        with self.assertRaisesRegex(ValueError, 'unsafe full-base path'):
            builder.tree_inventory(self.root)

    def fake_extract(self, files):
        extractor = self.root / 'fixture-extractor'
        extractor.write_text('#!' + os.sys.executable + '\nimport sys,pathlib,json\n'
                             'root=pathlib.Path(next(x[2:] for x in sys.argv if x.startswith("-o")))\n'
                             'files=json.loads(' + repr(json.dumps(files)) + ')\n'
                             'for name,data in files.items():\n'
                             ' p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)\n')
        extractor.chmod(0o700)
        return extractor

    def candidate_fixture(self):
        staging = self.root / 'staging'
        staging.mkdir()
        candidate = staging / 'candidate'
        self.selectors(candidate / 'tree')
        (candidate / 'tree/runtime.sh').write_text('patched')
        source = self.root / 'source'
        source.mkdir()
        (source / 'runtime.sh').write_text('original')
        manifest = {'changes': [{'path': 'runtime.sh',
                                'before_sha256': hashlib.sha256(b'original').hexdigest(),
                                'after_sha256': hashlib.sha256(b'patched').hexdigest()}]}
        files = builder.deployment_files(candidate, source, manifest)
        return staging, candidate, files

    def test_full_base_composition_preserves_native_bytes_and_verifies_payload(self):
        staging, candidate, files = self.candidate_fixture()
        extractor = self.fake_extract({'runtime.sh': 'original', 'Emu/PSP/engine': 'native bytes'})
        result = builder.materialize_base(staging, self.root / 'fixture.7z', extractor, candidate, files)
        self.assertFalse(result['activated'])
        self.assertTrue(result['unselected_base_files_unchanged'])
        self.assertEqual((staging / 'prepared-card/Emu/PSP/engine').read_text(), 'native bytes')
        self.assertEqual((staging / 'prepared-card/runtime.sh').read_text(), 'patched')
        builder.require_disabled_selectors(staging / 'prepared-card')
        self.assertEqual(result['prepared_inventory_sha256'], builder.sha256_file(staging / 'prepared-card-files.json'))

    def test_full_base_preimage_failure_happens_before_patching(self):
        staging, candidate, files = self.candidate_fixture()
        extractor = self.fake_extract({'runtime.sh': 'wrong version', 'Emu/PSP/engine': 'native bytes'})
        with self.assertRaisesRegex(ValueError, 'patch preimage'):
            builder.materialize_base(staging, self.root / 'fixture.7z', extractor, candidate, files)
        self.assertEqual((staging / 'prepared-card/runtime.sh').read_text(), 'wrong version')
        self.assertFalse((staging / 'prepared-card' / builder.release.PAYLOAD_ROOT).exists())


if __name__ == '__main__':
    unittest.main()
