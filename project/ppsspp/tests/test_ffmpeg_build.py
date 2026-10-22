# SPDX-License-Identifier: MIT
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

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

    def resume_fixture(self, name):
        root=self.root/name;root.mkdir()
        source=root/'source';source.mkdir()
        (source/'linux_arm64.sh').write_bytes(self.script.read_bytes())
        (source/'configure').write_bytes(b'configure identity fixture\n')
        build=root/'build';build.mkdir()
        prefix=root/'prefix';(prefix/'include/libavcodec').mkdir(parents=True)
        (prefix/'include/libavcodec/avcodec.h').write_text('header fixture\n')
        (prefix/'lib').mkdir()
        archives=[]
        for component in ffmpeg.COMPONENTS:
            relative='lib/lib'+component+'.a';path=prefix/relative
            path.write_bytes(('archive fixture '+component).encode())
            archives.append({'path':relative,'sha256':ffmpeg.sha(path),'size':path.stat().st_size})
        metadata=root/'metadata';metadata.mkdir()
        commit='a'*40
        inputs={'ffmpeg':{'commit':commit,'configure_sha256':ffmpeg.sha(source/'configure'),
                         'script_path':'linux_arm64.sh','script_sha256':self.pin}}
        _,configuration=ffmpeg.configuration(source/'linux_arm64.sh',self.pin,prefix)
        report={'status':'complete','commit':commit,'configure_args':configuration,'archives':archives,
                'header_inventory':ffmpeg.header_inventory(prefix)}
        (metadata/'manifest.json').write_text(json.dumps(report))
        return source,build,prefix,metadata,inputs,report

    def resume(self, fixture):
        source,build,prefix,metadata,inputs,report=fixture
        original=ffmpeg.subprocess.run
        def run(args, **kwargs):
            if args[0]=='git':
                return SimpleNamespace(stdout=inputs['ffmpeg']['commit']+'\n')
            self.assertNotIn(args[0],('make',str(source/'configure')))
            return original(args,**kwargs)
        with patch.object(ffmpeg.subprocess,'run',side_effect=run):
            return ffmpeg.build(source,build,prefix,metadata,inputs,2)

    def test_completed_source_build_resume_verifies_installed_headers_and_archives(self):
        fixture=self.resume_fixture('matching')
        self.assertEqual(self.resume(fixture),fixture[-1])
        for case in ('changed-header','extra-header','header-symlink','changed-archive','old-metadata'):
            with self.subTest(case=case):
                fixture=self.resume_fixture(case)
                source,build,prefix,metadata,inputs,report=fixture
                if case=='changed-header':
                    (prefix/'include/libavcodec/avcodec.h').write_text('changed\n')
                elif case=='extra-header':
                    (prefix/'include/stale.h').write_text('unexpected\n')
                elif case=='header-symlink':
                    (prefix/'include/libavcodec/avcodec.h').unlink()
                    (prefix/'include/libavcodec/avcodec.h').symlink_to(self.script)
                elif case=='changed-archive':
                    (prefix/'lib/libavutil.a').write_text('changed\n')
                else:
                    del report['header_inventory']
                    (metadata/'manifest.json').write_text(json.dumps(report))
                with self.assertRaises(ValueError):
                    self.resume(fixture)

if __name__=='__main__':unittest.main()
