"""Isolated regressions for the three pinned spruce patches.

Only individual parsed functions run. Device services, networking, extraction,
display, shutdown and MainUI handoff are replaced with temporary fake programs.
Set SPRUCE_SOURCE_ROOT to an untouched spruce v4.5.4 checkout.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('SPRUCE_SOURCE_ROOT', '/workspace/spruce-base'))
PYUI = 'App/PyUI/main-ui/devices/miyoo_trim_common.py'
OTA = 'App/-OTA/downloader.sh'
HELPER = 'spruce/scripts/helperFunctions.sh'


def shell_function(source, name):
    found = re.search(r'^' + re.escape(name) + r'\(\)\s*\{.*?^\}', source, re.M | re.S)
    if not found:
        raise AssertionError(name)
    return found.group(0)


def game_command(source, launch_folder, rom_path):
    method = next(n for n in ast.walk(ast.parse(source))
                  if isinstance(n, ast.FunctionDef) and n.name == 'run_game')
    method.decorator_list = []
    commands = []
    no_op = lambda *args: None
    device = SimpleNamespace(fix_sleep_sound_bug=no_op, exit_pyui=no_op)
    namespace = {
        'Theme': SimpleNamespace(check_and_create_ra_assets=no_op),
        'Device': SimpleNamespace(get_device=lambda: device),
        'Display': SimpleNamespace(deinit_display=no_op),
        'MiyooTrimCommon': SimpleNamespace(write_cmd_to_run=commands.append),
        'RomInfo': object, 'subprocess': subprocess, 'os': os, 're': re, 'shlex': shlex,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
                 '<isolated run_game>', 'exec'), namespace)
    config = SimpleNamespace(get_emu_folder=lambda: str(launch_folder),
                             get_launch=lambda: '../../spruce/scripts/emu/standard_launch.sh')
    rom = SimpleNamespace(rom_file_path=str(rom_path),
                          game_system=SimpleNamespace(game_system_config=config))
    namespace['run_game'](None, rom, run_prefix='env PROBE_MODE=kept ')
    return commands[0]


class UpstreamReliability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (SOURCE / PYUI).is_file():
            raise unittest.SkipTest('Untouched pinned spruce source not available; set SPRUCE_SOURCE_ROOT')
        cls.temp = tempfile.TemporaryDirectory()
        cls.patched_root = Path(cls.temp.name)
        manifest = json.loads((PROJECT / 'patches/manifest.json').read_text())
        for item in manifest['patches']:
            original = SOURCE / item['path']
            if hashlib.sha256(original.read_bytes()).hexdigest() != item['base_sha256']:
                raise AssertionError(f'Unexpected upstream bytes: {item["path"]}')
            target = cls.patched_root / item['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            patch = PROJECT / 'patches' / item['patch']
            subprocess.run(['git', 'apply', '--check', str(patch)], cwd=cls.patched_root,
                           check=True, capture_output=True, text=True)
            subprocess.run(['git', 'apply', str(patch)], cwd=cls.patched_root,
                           check=True, capture_output=True, text=True)
            if hashlib.sha256(target.read_bytes()).hexdigest() != item['patched_sha256']:
                raise AssertionError(f'Unexpected patched bytes: {item["path"]}')

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'temp'):
            cls.temp.cleanup()

    def game_probe(self, patched):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            system = root / 'Emu/SYS$(touch PWNED)'
            system.mkdir(parents=True)
            launcher = root / 'spruce/scripts/emu/standard_launch.sh'
            launcher.parent.mkdir(parents=True)
            launcher.write_text('#!/bin/sh\nprintf "%s" "$0" > "$REPORT0"\n'
                                'printf "%s" "$1" > "$REPORT1"\n'
                                'printf "%s" "$PROBE_MODE" > "$REPORT2"\n')
            launcher.chmod(0o755)
            rom = root / 'Roms/SYS/a";$(touch ROM_PWNED)`x`$x\\\n雪.iso'
            source = (self.patched_root if patched else SOURCE) / PYUI
            command = game_command(source.read_text(), system, rom)
            env = dict(os.environ, REPORT0=str(root / 'zero'),
                       REPORT1=str(root / 'one'), REPORT2=str(root / 'two'))
            result = subprocess.run(['sh', '-c', command], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=5)
            if patched:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((root / 'one').read_text(), str(rom))
                self.assertEqual((root / 'two').read_text(), 'kept')
                self.assertIn('/Emu/SYS$(touch PWNED)/../../spruce/', (root / 'zero').read_text())
                self.assertFalse((root / 'PWNED').exists())
                self.assertFalse((root / 'ROM_PWNED').exists())
            else:
                self.assertTrue((root / 'PWNED').exists(), 'Pinned defect was not reproduced')

    def test_baseline_launcher_folder_expands_shell_substitution(self):
        self.game_probe(False)

    def test_patch_quotes_paths_and_preserves_lexical_system_id_and_prefix(self):
        self.game_probe(True)

    def tls_probe(self, patched, fail=True):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = ((self.patched_root if patched else SOURCE) / OTA).read_text()
            function = shell_function(source, 'download_release_info')
            script = r'''
log_message() { printf '%s\n' "$*"; }
curl() {
  printf '%s\n' "$*" >> "$PROBE_ROOT/calls"
  insecure=0
  case " $* " in *" -k "*) insecure=1 ;; esac
  while [ "$#" -gt 0 ]; do
    case "$1" in -o) shift; output=$1 ;; esac
    shift
  done
  if [ "$PROBE_FAIL" = 1 ] && [ "$insecure" = 0 ]; then
    printf partial > "$output"
    return 60
  fi
  printf 'RELEASE_VERSION=4.5.4\n' > "$output"
  return 0
}
''' + function + '\ndownload_release_info https://example.invalid/release "$PROBE_ROOT/output" "$PROBE_ROOT"\n'
            env = dict(os.environ, PROBE_ROOT=str(root), PROBE_FAIL='1' if fail else '0')
            result = subprocess.run(['sh', '-c', script], env=env, text=True,
                                    capture_output=True, timeout=5)
            calls = (root / 'calls').read_text().splitlines()
            return result, calls, (root / 'output').exists()

    def test_baseline_tls_failure_retries_without_identity_check(self):
        result, calls, _ = self.tls_probe(False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(calls), 2)
        self.assertIn('-k', calls[1])

    def test_patch_tls_failure_is_truthful_and_removes_partial_metadata(self):
        result, calls, exists = self.tls_probe(True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertFalse(exists)
        self.assertIn('device date, CA bundle or connection', result.stdout)

    def test_patch_preserves_verified_online_download(self):
        result, calls, exists = self.tls_probe(True, fail=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(exists)
        self.assertIn("--proto =https", calls[0])

    def extraction_probe(self, patched, code=2):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = ((self.patched_root if patched else SOURCE) / HELPER).read_text()
            function = shell_function(source, 'extract_7z_with_progress')
            script = r'''
log_update_message() { printf '%s\n' "$*"; }
display_image_and_text() { :; }
sleep() { :; }
''' + function + '\nextract_7z_with_progress fake.7z "$PROBE_ROOT/out" "$PROBE_ROOT/log" test\n'
            binary = root / '7zr'
            binary.write_text('#!/bin/sh\ncase "$1" in\n'
                              'l) printf "2026-10-22 0 0 0 item\\n"; exit 0 ;;\n'
                              'x) printf "%s\\n" "- item"; exit "$PROBE_EXIT" ;;\n'
                              'esac\n')
            binary.chmod(0o755)
            env = dict(os.environ, PROBE_ROOT=str(root), PROBE_EXIT=str(code),
                       SPRUCE_SUPPRESS_EXTRACT_PROGRESS_UI='1', TMPDIR=str(root),
                       PATH=str(root) + os.pathsep + os.environ.get('PATH', ''))
            return subprocess.run(['sh', '-c', script], env=env, text=True,
                                  capture_output=True, timeout=5)

    def test_baseline_extractor_failure_is_hidden_by_progress_reader(self):
        result = self.extraction_probe(False)
        self.assertEqual(result.returncode, 0)
        self.assertIn('completed successfully', result.stdout)

    def test_patch_returns_actual_extractor_error(self):
        result = self.extraction_probe(True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn('completed successfully', result.stdout)

    def test_patch_preserves_successful_extraction(self):
        result = self.extraction_probe(True, code=0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('completed successfully', result.stdout)


if __name__ == '__main__':
    unittest.main()
