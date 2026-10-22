# SPDX-License-Identifier: MIT
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sdk_search',ROOT/'sdk_search.py')
search=importlib.util.module_from_spec(spec);spec.loader.exec_module(search)
spec=importlib.util.spec_from_file_location('ffmpeg_builder',ROOT/'ffmpeg_build.py')
ffmpeg=importlib.util.module_from_spec(spec)
with patch.dict(sys.modules,{'sdk_search':search}):spec.loader.exec_module(ffmpeg)

class FFmpegRecipeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.script=self.root/'recipe.sh'
        self.script.write_text('''#!/bin/bash
set -e
CODECS="--enable-decoder=atrac3p --enable-encoder=pcm_s16le"
function build_ARM64
{
./configure --target-os=linux \\
 --prefix=./linux/aarch64 \\
 --extra-cflags=" -O3 -fasm " \\
 --disable-everything ${CODECS}
make clean
make install
}
build_ARM64
exit 41
''')
        self.pin=hashlib.sha256(self.script.read_bytes()).hexdigest()

    def test_exact_shell_argument_expansion_preserves_codec_selection_and_quoted_flags(self):
        prefix=self.root/'output with spaces'
        original,changed=ffmpeg.configuration(self.script,self.pin,prefix)
        self.assertIn('--extra-cflags= -O3 -fasm ',original)
        self.assertEqual([a for a in original if a.startswith(('--enable-','--disable-'))],
                         [a for a in changed if a.startswith(('--enable-','--disable-'))])
        self.assertIn('--prefix='+str(prefix),changed)
        cflags=[a for a in changed if a.startswith('--extra-cflags=')]
        self.assertEqual(len(cflags),1)
        self.assertTrue(cflags[0].startswith('--extra-cflags=-O3 -fasm -nostdinc '))
        self.assertIn('--sysroot=/opt/sysroot',changed)
        self.assertIn('--extra-ldflags=-L/usr/lib/gcc-cross/aarch64-linux-gnu/9 -L/opt/sysroot/lib -L/opt/sysroot/usr/lib',changed)

    def test_changed_script_rejected_before_any_shell_prefix_executes(self):
        marker=self.root/'must-not-exist'
        text=self.script.read_text().replace('set -e','set -e\ntouch '+str(marker))
        self.script.write_text(text)
        with self.assertRaisesRegex(ValueError,'script changed'):
            ffmpeg.configuration(self.script,self.pin,self.root/'out')
        self.assertFalse(marker.exists())

if __name__=='__main__':unittest.main()
