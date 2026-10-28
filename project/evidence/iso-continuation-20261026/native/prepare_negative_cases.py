import hashlib,json,os,secrets,sys
from pathlib import Path
sys.path.insert(0,'/workspace/TrimUi/project')
from psp_shell.state_evidence import encode_packet
root=Path('/workspace/trimui-audit/native/runtime')
base=json.loads((root/'playable-resume2/probe.json').read_text())
source=(root/'bootstrap/patched-playable.ppst').read_bytes()
for case in ['wrong-engine','wrong-game','mutated-state','truncated-state','corrupt-state','interrupted-result','malformed-packet','insecure-mode']:
 d=root/case;d.mkdir(mode=0o700)
 state=d/'input.ppst';state.write_bytes(source)
 r=list(base['fields']);r[:3]=[secrets.token_hex(16) for _ in range(3)];r[9]=str(d);r[11]=str(state)
 if case=='corrupt-state':state.write_bytes(b'corrupt-not-a-ppsspp-state\n')
 r[12]=hashlib.sha256(state.read_bytes()).hexdigest()
 if case=='wrong-engine':r[8]='0'*64
 if case=='wrong-game':r[7]='0'*64
 packet=encode_packet(b'TPSE1Q\n',r)
 if case=='malformed-packet':packet+=b'unexpected-trailer'
 (d/'request').write_bytes(packet);os.chmod(d/'request',0o644 if case=='insecure-mode' else 0o600)
 if case=='mutated-state':
  b=bytearray(source);b[len(b)//2]^=1;state.write_bytes(b)
 if case=='truncated-state':state.write_bytes(source[:256])
 if case=='interrupted-result':(d/'result').mkdir(mode=0o700)
 meta=dict(base,fields=r,request_sha256=hashlib.sha256(packet).hexdigest(),state_sha256=r[12],negative_case=case)
 (d/'probe.json').write_text(json.dumps(meta,indent=2)+'\n')
 print(case)
