#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
from pathlib import Path
import sys
import hashlib,json,tarfile,re,struct
r=Path(sys.argv[1]); out=Path(sys.argv[2]); out.mkdir(parents=True,exist_ok=True)
old=json.load(open(Path(__file__).resolve().parents[1]/'completion-20261023/native-rights-review.json'))
expected={'ppsspp-source':'2575f85be69acab16a6e4b015dda72f3e13b355b3609894fc3d58b059ae18556','ra-source':'61e03dde636297a5dc6556464513c6d22a063113e4327be82637aa755c9b2f36'}
texts=[];rows=[];cache={}
def sha(b):return hashlib.sha256(b).hexdigest()
def add(aid,path,data,start=0,end=None,kind='exact-source-text'):
 end=len(data) if end is None else end;body=data[start:end]
 if not body.strip():return
 row={'archive_id':aid,'path':path,'source_file_sha256':sha(data),'source_file_size_bytes':len(data),'offset_bytes':start,'length_bytes':len(body),'notice_sha256':sha(body),'kind':kind}
 rows.append(row);texts.append(('\n'+'='*72+'\n'+aid+': '+path+'\n'+'SHA-256: '+sha(data)+'\n'+'Exact bytes '+str(start)+'..'+str(end)+' (end exclusive)\n'+'='*72+'\n').encode()+body+b'\n')
for aid,digest in expected.items():
 p=r/(aid+'.tar.gz');assert sha(p.read_bytes())==digest
 with tarfile.open(p) as t:
  members={m.name:m for m in t if m.isfile()}
  names=set(members)
  full={x['path'] for x in old['native_source_notice_inventories'][aid]['named_notice_candidates'] if x['size_bytes'] and x['path'].startswith(('ppsspp/ext/','ppsspp/ffmpeg/','modified/deps/')) and not any(s in x['path'] for s in ['/OpenXR-SDK/','/tests/','/test/','/discord-rpc/','/libgo2/','/libvita2d/','/libShake/','/Pigs-In-A-Blanket/','/bearssl-0.6/','/wayland-protocols/'])}
  full|=({'ppsspp/LICENSE.TXT','ppsspp/assets/debugger/static/js/main.fe87e942.js.LICENSE.txt','build/project-notices/PPSSPP-PROJECT-NOTICE.md','build/project-notices/PPSSPP-GPL-AND-PSPSDK.txt'} if aid=='ppsspp-source' else {'modified/COPYING','project/retroarch/NOTICE.md'})
  if aid=='ppsspp-source':
   inline=['ppsspp/ext/libkirk/kirk_engine.c','ppsspp/ext/libzip/zip.h','ppsspp/ext/lua/lua.h','ppsspp/ext/xxhash.h','ppsspp/ext/libpng17/png.h','ppsspp/ext/minimp3/minimp3.h','ppsspp/ext/minimp3/minimp3_ex.h','ppsspp/ext/sfmt19937/SFMT.h']
   inline += sorted(n for n in names if n.startswith('ppsspp/ext/at3_standalone/') and n.endswith(('.c','.cpp','.h')))
  else:
   inline=sorted(n for n in names if n.startswith(('modified/gfx/video_filters/','modified/libretro-common/audio/dsp_filters/')) and n.endswith(('.c','.h')))
   inline+=['modified/deps/mbedtls/aes.c','modified/deps/glslang/glslang/glslang/Include/BaseTypes.h']
  for n in sorted(full):
   if n not in members:continue
   b=t.extractfile(members[n]).read();add(aid,n,b)
  for n in sorted(set(inline)):
   b=t.extractfile(members[n]).read()
   if n.endswith('lua.h'):
    start=b.rfind(b'/*');end=b.find(b'*/',start)+2
   else:
    comments=list(re.finditer(rb'/\*.*?\*/',b,re.S)); comments=[m for m in comments if m.start()<1500 and re.search(rb'copyright|licen[sc]e|public domain',m.group(),re.I)]
    if not comments:continue
    start=comments[0].start();end=comments[-1].end()
    if n.endswith('/png.h'):end=list(re.finditer(rb'/\*.*?\*/',b,re.S))[1].end()
   add(aid,n,b,start,end,'exact-inline-notice')
  if aid=='ppsspp-source':
   for n in ['ppsspp/ext/vma/vk_mem_alloc.h','ppsspp/ext/basis_universal/basisu_transcoder.cpp','ppsspp/ext/xbrz/xbrz.h']:
    b=t.extractfile(members[n]).read();end=b.find(b'\n\n');add(aid,n,b,0,end,'exact-inline-notice')
   n='ppsspp/ext/imgui/imgui.cpp';b=t.extractfile(members[n]).read();start=b.index(b'// Copyright');end=b.index(b'// This library',start);add(aid,n,b,start,end,'exact-inline-notice')
   font_rows=[]
   for n in sorted(names):
    if n.startswith('ppsspp/assets/') and n.endswith('.ttf'):
     b=t.extractfile(members[n]).read();num=struct.unpack_from('>H',b,4)[0];nt=None
     for i in range(num):
      tag,_,offset,length=struct.unpack_from('>4sIII',b,12+16*i)
      if tag==b'name':nt=b[offset:offset+length]
     assert nt is not None
     _,count,base=struct.unpack_from('>HHH',nt);recs=set()
     for i in range(count):
      platform,encoding,language,nid,length,offset=struct.unpack_from('>HHHHHH',nt,6+12*i)
      if nid not in (0,13,14):continue
      raw=nt[base+offset:base+offset+length];text=raw.decode('utf-16-be' if platform in (0,3) else 'mac-roman',errors='replace');recs.add((nid,text))
     font_rows.append({'path':n,'sha256':sha(b),'size_bytes':len(b),'embedded_name_records':[{'name_id':i,'text':s} for i,s in sorted(recs)]})
   (out/'native-font-notices.json').write_text(json.dumps(font_rows,indent=2)+'\n')
for name,digest in [('imgui-LICENSE.txt','0ebf8feb061536bdebd7c6a365b64808ae3479048b1c44113e19037680c5f2be'),('sfmt-LICENSE.txt','9d6db9b6702bf80c926b36d61f6282bf48d0a9a8044db2bd31e524aa08ccac0f'),('glibc-COPYING.LIB','dc626520dcd53a22f727af3ee42c770e56c97a64fe3adb063799d8ab032fe551')]:
 b=(r/name).read_bytes();assert sha(b)==digest;add('supplemental-primary',name,b,kind='supplemental-not-in-R04-archive')
b=(Path(__file__).resolve().parents[2]/'assets/fonts/OFL.txt').read_bytes()
start=b.index(b'SIL OPEN FONT LICENSE');add('project-reference','project/assets/fonts/OFL.txt',b,start,kind='full-standard-OFL-text; actual-native-font-copyrights-in-native-font-notices.json')
header=b'''Selected native notice review packet, 23 October 2026\n\nExact retained native source notice material; no executable or private recipe\nsource is included. This is a reusable review supplement, not native distribution\nclearance or a claim that every required notice or incorporated source is covered.\nSource-tree dependency notices may be overinclusive. The scope and unresolved\nitems are recorded in nondevice-distribution-2026-10-23.md and review.json.\n\nFuture native combined-license route: GPL-3.0-or-later where applicable.\nSeparate original Python and PyUI sources retain their own terms.\n\n'''
packet=header+b''.join(texts);(out/'selected-native-notices.txt').write_bytes(packet)
manifest={'schema':1,'kind':'exact-selected-native-notice-packet','archive_inputs':expected,'notices':rows,'packet_sha256':sha(packet),'packet_size_bytes':len(packet),'entries':len(rows),'complete_native_notice_packet':False,'distribution_cleared':False}
(out/'notice-packet-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Packet',len(rows),len(packet),sha(packet))
