import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,'/workspace/TrimUi/project')
from psp_shell.state_evidence import _decode_packet
root=Path(sys.argv[1]);meta=json.loads((root/'probe.json').read_text());out={'kind':'native-only-result-observation','does_not_grant_foreground_or_device_authority':True,'results':{}}
for name in ['result','save-completed','load-completed']:
 p=root/name
 if not p.is_file():continue
 b=p.read_bytes();r=_decode_packet(b,b'TPSE1R\n',27)
 assert r[:6]==tuple(meta['fields'][:6])
 out['results'][name]={'packet_sha256':hashlib.sha256(b).hexdigest(),'operation':r[6],'sequence':int(r[7]),'status':r[8],'message':r[9], 'disc_id':r[10],'disc_version':r[11],'prefix':r[12],'engine_sha256':r[14],'game_sha256':r[15],'state_sha256':r[16],'state_size':r[19],'state_path':r[20],'slot':r[21],'upstream_commit':r[22],'extension':r[23],'architecture':r[25]}
 if r[8]=='success':
  assert r[14]==meta['engine_sha256'] and r[15]==meta['rom_sha256']
  pstate=Path(r[20]);h=hashlib.sha256(pstate.read_bytes()).hexdigest()
  out['results'][name]['current_state_matches']=h==r[16]
print(json.dumps(out,indent=2))
