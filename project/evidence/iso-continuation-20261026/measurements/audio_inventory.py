#!/usr/bin/env python3
# Read-only container/PCM-presence inventory; this is not auditory fault review.
from pathlib import Path
import wave,array,json,hashlib,sys
root=Path('/workspace/trimui-audit/measurements');out=Path('/workspace/TrimUi/project/evidence/iso-continuation-20261026/measurements/audio-inventory.json')
results=[]
for parent in (root/'controlled',root/'rerun-pair4'):
 for run in sorted(parent.glob('pair-*'))+sorted(parent.glob('soak-*')):
  receipt=json.loads((run/'receipt.json').read_text())
  for entry in receipt.get('audio_files',[]):
   p=run/entry['path'];h=hashlib.sha256()
   with p.open('rb') as f:
    for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
   assert h.hexdigest()==entry['sha256']
   record={'run':run.name,'attempt_root':parent.name,'private_relative_path':entry['path'],'size_bytes':entry['size'],'sha256':h.hexdigest(),'quality_reviewed':False}
   try:
    with wave.open(str(p),'rb') as w:
     record.update(channels=w.getnchannels(),sample_width_bytes=w.getsampwidth(),sample_rate_hz=w.getframerate(),frames=w.getnframes(),duration_seconds=w.getnframes()/w.getframerate(),compression=w.getcomptype())
     nonzero=False;read_frames=0
     while True:
      data=w.readframes(65536)
      if not data:break
      read_frames+=len(data)//(w.getnchannels()*w.getsampwidth())
      nonzero=nonzero or any(data)
     record.update(frames_read=read_frames,nonzero_pcm_present=nonzero)
     assert read_frames==record['frames']
   except (wave.Error,EOFError) as error:record['container_error']=str(error)
   results.append(record)
out.write_text(json.dumps({'schema':1,'scope':'Native pre-volume mixed PCM recording container and nonzero-byte checks only; no listening review or speaker/device evidence.','audio_faults':None,'entries':results},indent=2)+'\n')
print(len(results),'WAV inventories; audio quality remains unavailable')
