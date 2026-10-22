# SPDX-License-Identifier: MIT
"""Compile the actual GPL post-recipe callback with pinned PPSSPP statuses.

This source acceptance checks the completion condition. It executes no signal,
emulator or device service and does not establish successful poweroff.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest

from test_native_menu_patch import block, checked

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


class SaveQuitOverrideMetadataTests(unittest.TestCase):
    def test_post_recipe_patch_has_separate_locked_source_and_no_device_claim(self):
        lock = json.loads((ROOT / 'recipe-overrides.lock.json').read_text())
        native = json.loads((ROOT / 'source-lock.json').read_text())
        inputs = json.loads((ROOT / 'build-inputs.lock.json').read_text())
        self.assertEqual(lock['upstream_commit'], native['upstream']['commit'])
        self.assertEqual(lock['recipe_commit'], inputs['recipe_commit'])
        self.assertFalse(lock['qualification']['device_tested'])
        self.assertNotIn(lock['patches'][0]['path'], [item['path'] for item in native['patches']])
        for item in lock['patches']:
            self.assertEqual(hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest(), item['sha256'])
            self.assertEqual(item['license'], 'GPL-2.0-or-later')


class SaveQuitOverrideSourceTests(unittest.TestCase):
    def test_both_real_callbacks_allow_quit_only_after_successful_completion(self):
        source = os.environ.get('PPSSPP_SOURCE_ROOT')
        if not source:
            self.skipTest('Set PPSSPP_SOURCE_ROOT to the pinned v1.20.3 checkout')
        header = Path(source) / 'Core/SaveState.h'
        evidence = json.loads((ROOT / 'state-evidence.lock.json').read_text())
        identity = next(item['sha256'] for item in evidence['source_files'] if item['path'] == 'Core/SaveState.h')
        self.assertEqual(hashlib.sha256(header.read_bytes()).hexdigest(), identity)
        status = block(header.read_text(), 'enum class Status', semicolon=True)
        lock = json.loads((ROOT / 'recipe-overrides.lock.json').read_text())
        patch = (ROOT / lock['patches'][0]['path']).read_text()
        self.assertIn('+static std::atomic<bool> g_QuitRequested{false};', patch)
        added = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
        marker = '[](SaveState::Status status, std::string_view)'
        callbacks = [block(added[position:], marker) for position in
                     [match.start() for match in re.finditer(re.escape(marker), added)]]
        self.assertEqual(len(callbacks), 2)
        self.assertEqual(callbacks[0], callbacks[1])
        code = ('// SPDX-License-Identifier: GPL-2.0-or-later\n'
                '#include <atomic>\n#include <cassert>\n#include <functional>\n#include <string_view>\n'
                'namespace SaveState {\n' + status + '\n}\n'
                'static std::atomic<bool> g_QuitRequested{false};\nint main() {\n'
                'std::function<void(SaveState::Status,std::string_view)> callback = ' + callbacks[0] + ';\n'
                'callback(SaveState::Status::FAILURE,"write or final rename failed"); assert(!g_QuitRequested);\n'
                'callback(SaveState::Status::WARNING,"not fully successful"); assert(!g_QuitRequested);\n'
                'callback(SaveState::Status::SUCCESS,"completed"); assert(g_QuitRequested);\n}\n')
        with tempfile.TemporaryDirectory(prefix='ppsspp-save-quit-acceptance-') as name:
            root = Path(name)
            cpp, binary = root / 'acceptance.cpp', root / 'acceptance'
            cpp.write_text(code)
            checked(['g++', '-std=c++17', '-Wall', '-Wextra', str(cpp), '-o', str(binary)], cwd=root)
            checked([str(binary)], cwd=root)


if __name__ == '__main__':
    unittest.main()
