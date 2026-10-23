# SPDX-License-Identifier: MIT
"""Execute the real pinned/patched scripts with fake mount/runtime helpers only.

No device nodes, root mounts, game binaries or owner data are accessed. Required
upstream bytes are copied to temporary storage and checked before patching.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('PORTS_SOURCE_ROOT', '/workspace/ports-reference'))


class CelestePreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = json.loads((PROJECT / 'ports/celeste-fix.lock.json').read_text())
        if not (SOURCE / cls.lock['files'][0]['path']).is_file():
            raise unittest.SkipTest('Set PORTS_SOURCE_ROOT to the untouched pinned PortMaster-New source')
        cls.temporary = tempfile.TemporaryDirectory(prefix='celeste-source-')
        cls.patched = Path(cls.temporary.name)
        for item in cls.lock['files']:
            original = SOURCE / item['path']
            if hashlib.sha256(original.read_bytes()).hexdigest() != item['base_sha256']:
                raise AssertionError('Celeste source preimage differs: ' + item['path'])
            target = cls.patched / item['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
        patch = PROJECT / 'ports' / cls.lock['patch']
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=cls.patched, check=True, capture_output=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=cls.patched, check=True, capture_output=True)
        for item in cls.lock['files']:
            target = cls.patched / item['path']
            if hashlib.sha256(target.read_bytes()).hexdigest() != item['patched_sha256']:
                raise AssertionError('Celeste patched bytes differ')
            subprocess.run(['bash', '-n', str(target)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'temporary'): cls.temporary.cleanup()

    def fixture(self, patched=True):
        temporary = tempfile.TemporaryDirectory(prefix='celeste isolated 雪 ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game = self.root / 'celeste'
        self.home_dir = self.root / 'runtime-home'
        self.bin = self.root / 'bin'
        for name in ('gamedata/Content/Graphics', 'utils', 'libs', 'savedata'):
            (self.game / name).mkdir(parents=True)
        self.bin.mkdir()
        self.trace = self.root / 'trace'
        self.trace.touch()
        self.marker = self.game / 'gamedata/.astc_done'
        self.write(self.game / 'common.src', 'msgbox() { :; }\n')
        self.write(self.game / 'libs/Celeste.exe.config', 'synthetic config')
        self.write(self.game / 'utils/fixture', '#!/bin/sh\nexit 0\n')
        self.write(self.game / 'celeste-repacker', '#!/bin/sh\nprintf "repack\\n" >> "$TRACE"\nexit "${REPACK_CODE:-0}"\n')
        self.write(self.game / 'progressor', '#!/bin/sh\nfor last do :; done\n"$last"\n')
        source = self.patched if patched else SOURCE
        self.write(self.game / 'repack.src', (source / 'ports/celeste/celeste/repack.src').read_text())
        self.write(self.home_dir / 'mono/bin/mono', '#!/bin/sh\nprintf "game\\n" >> "$TRACE"\nexit "${GAME_CODE:-0}"\n')
        self.write(self.bin / 'mono', '#!/bin/sh\nexit 0\n')
        self.write(self.bin / 'touch', '#!/bin/sh\n[ "${NO_SPACE:-0}" = 0 ] || exit 1\nexec /usr/bin/touch "$@"\n')
        self.environment = dict(os.environ, gamedir=str(self.game), TRACE=str(self.trace),
            PATH=str(self.bin) + os.pathsep + os.environ['PATH'], PROBE_HOME=str(self.home_dir))

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(0o755)

    def repack(self, *, patched=True, **variables):
        self.fixture(patched)
        self.environment.update({k: str(v) for k, v in variables.items()})
        return subprocess.run(['bash', str(self.game / 'repack.src')], env=self.environment,
                              capture_output=True, text=True, timeout=5)

    def launcher(self, *, reuse=False, **variables):
        if not reuse: self.fixture()
        source = (self.patched / 'ports/celeste/Celeste.sh').read_text()
        # Only the real patched preparation/game/cleanup body. Absolute device
        # setup is excluded; every side effect below is a local fake helper.
        body = 'mono_mounted=0' + source.split('mono_mounted=0', 1)[1]
        body = body.replace('$HOME', '$PROBE_HOME')
        helpers = r'''
ESUDO=
TASKSET=
PM_CAN_MOUNT=Y
controlfolder="$gamedir/fixture-control"
GPTOKEYB=true
mountpoint() { [ -f "${@: -1}/.fixture-mounted" ]; }
mount() {
    printf 'mount\n' >> "$TRACE"
    [ "${MOUNT_CODE:-0}" = 0 ] || return "$MOUNT_CODE"
    : > "${@: -1}/.fixture-mounted"
}
umount() {
    printf 'unmount:%s\n' "$1" >> "$TRACE"
    [ "${UMOUNT_CODE:-0}" = 0 ] || return "$UMOUNT_CODE"
    rm -f "$1/.fixture-mounted"
}
bind_directories() {
    printf 'bind\n' >> "$TRACE"
    if [ "${BIND_PARTIAL:-0}" != 0 ]; then
        mkdir -p "$1"
        : > "$1/.fixture-mounted"
        return 9
    fi
    [ "${BIND_CODE:-0}" = 0 ] || return "$BIND_CODE"
    mkdir -p "$1"
    : > "$1/.fixture-mounted"
}
pm_finish() { printf 'finish\n' >> "$TRACE"; }
cd "$gamedir/gamedata" || exit 1
'''
        self.environment.update({k: str(v) for k, v in variables.items()})
        return subprocess.run(['bash', '-c', helpers + body], env=self.environment,
                              capture_output=True, text=True, timeout=5)

    def test_pinned_repacker_failure_is_reproduced_as_false_success(self):
        result = self.repack(patched=False, REPACK_CODE=23)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.marker.exists())

    def test_actual_repacker_failure_returns_original_status_and_no_marker(self):
        result = self.repack(REPACK_CODE=23)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertFalse(self.marker.exists())
        self.assertIn('Failure repacking', result.stdout)

    def test_successful_repack_records_completion(self):
        result = self.repack()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.marker.exists())

    def test_full_or_readonly_completion_write_is_failure(self):
        result = self.repack(NO_SPACE=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_failed_repack_can_be_retried_without_false_completion(self):
        self.repack(REPACK_CODE=23)
        self.environment['REPACK_CODE'] = '0'
        result = subprocess.run(['bash', str(self.game / 'repack.src')], env=self.environment,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.marker.exists())

    def test_launcher_mount_failure_never_runs_repack_or_game(self):
        result = self.launcher(MOUNT_CODE=32)
        self.assertNotEqual(result.returncode, 0)
        trace = self.trace.read_text().splitlines()
        self.assertNotIn('game', trace)
        self.assertNotIn('repack', trace)
        self.assertNotIn('finish', trace, 'An early failure must not clean up another game controller')
        self.assertFalse(any(s.startswith('unmount:') for s in trace))

    def test_failed_save_bind_cleans_only_its_mono_mount(self):
        result = self.launcher(BIND_CODE=9)
        self.assertNotEqual(result.returncode, 0)
        trace = self.trace.read_text()
        self.assertIn('unmount:' + str(self.home_dir / 'mono'), trace)
        self.assertNotIn('unmount:' + str(self.home_dir / '.local/share/Celeste'), trace)
        self.assertFalse(self.marker.exists())

    def test_launcher_repack_failure_is_nonzero_and_cleans_both_mounts(self):
        result = self.launcher(REPACK_CODE=23)
        self.assertEqual(result.returncode, 23, result.stderr)
        trace = self.trace.read_text().splitlines()
        self.assertNotIn('game', trace)
        self.assertEqual(len([s for s in trace if s.startswith('unmount:')]), 2)
        self.assertFalse(self.marker.exists())

    def test_bind_that_mounts_then_fails_still_releases_its_mount(self):
        result = self.launcher(BIND_PARTIAL=1)
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertEqual(len([s for s in self.trace.read_text().splitlines() if s.startswith('unmount:')]), 2)
        self.assertNotIn('finish', self.trace.read_text().splitlines())

    def test_launcher_full_disk_never_launches_game(self):
        result = self.launcher(NO_SPACE=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('game', self.trace.read_text().splitlines())
        self.assertFalse(self.marker.exists())

    def test_successful_launch_and_second_launch_reuse_completed_preparation(self):
        first = self.launcher()
        second = self.launcher(reuse=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        trace = self.trace.read_text().splitlines()
        self.assertEqual(trace.count('repack'), 1)
        self.assertEqual(trace.count('game'), 2)
        self.assertFalse((self.home_dir / 'mono/.fixture-mounted').exists())

    def test_game_failure_survives_tee_and_cleanup(self):
        result = self.launcher(GAME_CODE=17)
        self.assertEqual(result.returncode, 17, result.stderr)

    def test_busy_mount_is_not_unmounted_or_reused(self):
        self.fixture()
        (self.home_dir / 'mono/.fixture-mounted').touch()
        result = self.launcher(reuse=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.home_dir / 'mono/.fixture-mounted').exists())
        self.assertFalse(any(s.startswith('unmount:') for s in self.trace.read_text().splitlines()))

    def test_cleanup_failure_is_not_success(self):
        result = self.launcher(UMOUNT_CODE=1)
        self.assertNotEqual(result.returncode, 0)

    def test_preview_never_selects_this_upstream_patch(self):
        self.assertFalse(self.lock['selected_for_device'])
        descriptor = json.loads((PROJECT / 'packaging/current-release.json').read_text())
        self.assertEqual(descriptor['selected_upstream_patches'], [])
