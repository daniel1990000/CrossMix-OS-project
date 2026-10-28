import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,'/workspace/TrimUi/project')
from psp_shell.state_evidence import _decode_packet
root=Path('/workspace/trimui-audit/native');run=root/'runtime'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
for name in ['save0','save1','resume1','playable-resume1','playable-resume2','playable-resume3','wrong-engine','malformed-packet','insecure-mode','wrong-game','mutated-state','truncated-state','corrupt-state','interrupted-result']:
 d=run/name;meta=json.loads((d/'probe.json').read_text());ex=json.loads((d/'experiment.json').read_text()) if (d/'experiment.json').exists() else None
 row={'case':name,'request_sha256':sha(d/'request'),'native_packets':{},'private_files':{},'experiment':ex}
 assert row['request_sha256']==meta['request_sha256']
 for f in ['result','save-completed','load-completed']:
  p=d/f
  if not p.is_file():continue
  r=_decode_packet(p.read_bytes(),b'TPSE1R\n',27);assert tuple(meta['fields'][:6])==r[:6]
  row['native_packets'][f]={'sha256':sha(p),'operation':r[6],'sequence':int(r[7]),'status':r[8],'message':r[9],'state_sha256':r[16],'state_size':r[19]}
  if r[8]=='success':assert r[14]==meta['engine_sha256'] and r[15]==meta['rom_sha256'] and r[22]=='d357e6a32934800d3d80b49f910a603e1b069751' and r[25]=='x86_64'
  else:assert not any(r[10:])
 for f in ['probe.json','experiment.json','observations.json','stdout.log','native.log','screen.png','driver.log']:
  if (d/f).is_file():row['private_files'][f]=sha(d/f)
 if name in ['wrong-engine','malformed-packet','insecure-mode']:
  assert ex['exit_code']==2 and not row['native_packets'];row['outcome']='passed expected startup rejection'
 elif name in ['wrong-game','mutated-state','truncated-state','corrupt-state']:
  assert ex['exit_code']==0 and set(row['native_packets'])=={'result'} and row['native_packets']['result']['status']=='failure';row['outcome']='passed expected native failure without positive receipt'
 elif name=='interrupted-result':
  assert ex['exit_code']==0 and (d/'result').is_dir() and set(row['native_packets'])=={'load-completed'};row['outcome']='passed native publication-failure injection; independent completion is not a final receipt'
 elif name=='save0':row['outcome']='retained harness setup failure: native default controls lacked F2 binding'
 elif name=='save1':
  assert ex['exit_code']==0 and row['native_packets']['result']['status']=='failure' and row['native_packets']['save-completed']['sequence']==1;row['outcome']='passed real save then failed write; completed original retained'
 else:
  assert row['native_packets']['result']['status']=='success';row['outcome']=('passed native load-only callback; no qualified profile granted' if name in ['playable-resume2','playable-resume3'] else 'passed native load then save callbacks; no qualified profile granted')
 rows.append(row)
report={'schema':1,'scope':'actual full x86_64 SDL native game/state protocol using private ISO and real native SaveSlot/Load callbacks','hardware_qualified':False,'authenticated_frontend_resume_completed':False,'qualified_profile_created':False,'upstream_commit':'d357e6a32934800d3d80b49f910a603e1b069751','engine_sha256':json.loads((root/'build-report.json').read_text())['executable_sha256'],'rom_sha256':meta['rom_sha256'],'cases':rows,'preserved_states':{p.name:{'sha256':sha(p),'size':p.stat().st_size} for p in (run/'bootstrap').glob('*.ppst')},'kernel_boundary_report':'../frontend/g05-native-boundary.json','kernel_boundary_entry':'clean run with root_pid 24006; private source receipt g05-owned-native-clean.json','limitations':['Desktop native evidence does not qualify TrimUI device compatibility, GPU/FPS, suspend or shell Resume.','Raw native packets do not create QualifiedStateProfile, Spruce foreground authority, writer capability or promoted SaveRef.','Fresh resume followed by save replaces state bytes; older load receipt then correctly names old bytes, while current save receipt names new bytes.','Publication-failure injection obstructed final result pathname; it did not simulate a power cut or claim production promotion.','Wrong-slot/replay/owner/session capability proofs remain production authority checks; no fabricated authority was constructed.','Host build uses pinned FFmpeg prebuilt x86_64 static archives, not reconstructed FFmpeg source.'],'retained_probe_scripts':{p.name:sha(p) for p in root.glob('*protocol*.py')}}
(root/'protocol-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'report':str(root/'protocol-report.json'),'sha256':sha(root/'protocol-report.json'),'cases':len(rows),'setup_failures':1,'native_observation_checks_passed':13},indent=2))
