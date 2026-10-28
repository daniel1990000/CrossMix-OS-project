"""Prepare an explicit native-only transport probe; never grant a qualified profile."""
import argparse, hashlib, json, os, secrets, sys
from pathlib import Path
sys.path.insert(0, '/workspace/TrimUi/project')
from psp_shell.state_evidence import encode_packet, _decode_packet
p=argparse.ArgumentParser()
p.add_argument('--engine',required=True,type=Path);p.add_argument('--rom',required=True,type=Path)
p.add_argument('--session',required=True,type=Path);p.add_argument('--state-root',required=True,type=Path)
p.add_argument('--mode',choices=('save','resume'),default='save');p.add_argument('--state',type=Path)
p.add_argument('--slot',default='0');p.add_argument('--wrong-game-hash',action='store_true');p.add_argument('--wrong-engine-hash',action='store_true')
a=p.parse_args()
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
rom=a.rom.resolve(strict=True);engine=a.engine.resolve(strict=True);state=a.state.resolve(strict=True) if a.state else None
if (a.mode=='resume') != bool(state):raise SystemExit('Resume requires state, save forbids it')
a.session.mkdir(mode=0o700);os.chmod(a.session,0o700)
a.state_root.mkdir(parents=True,exist_ok=True)
fields=(secrets.token_hex(16),secrets.token_hex(16),secrets.token_hex(16),Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'1','native-only:ULUS10160',str(rom),'0'*64 if a.wrong_game_hash else sha(rom),'0'*64 if a.wrong_engine_hash else sha(engine),str(a.state_root.resolve()),a.mode,str(state) if state else '',sha(state) if state else '','ppsspp:d357e6a32934800d3d80b49f910a603e1b069751:chunk5-savestart3',a.slot)
with os.fdopen(os.open(a.session/'request',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:f.write(encode_packet(b'TPSE1Q\n',fields));f.flush();os.fsync(f.fileno())
meta={'kind':'native-only-raw-protocol-probe','does_not_create_qualified_profile':True,'mode':a.mode,'request_sha256':sha(a.session/'request'),'engine_sha256':sha(engine),'rom_sha256':sha(rom),'state_sha256':sha(state) if state else None,'fields':fields}
(a.session/'probe.json').write_text(json.dumps(meta,indent=2)+'\n');os.chmod(a.session/'probe.json',0o600)
print(str(a.session/'request'))
