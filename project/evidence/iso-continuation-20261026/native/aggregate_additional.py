import datetime,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,'/workspace/TrimUi/project')
from psp_shell.state_evidence import _decode_packet
root=Path('/workspace/trimui-audit/native/runtime')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
for name in ['wrong-slot','truncated-matching-hash','replay-session']:
 d=root/name;meta=json.loads((d/'probe.json').read_text());e=json.loads((d/'experiment.json').read_text());o=json.loads((d/'observations.json').read_text());r=_decode_packet((d/'result').read_bytes(),b'TPSE1R\n',27)
 assert tuple(meta['fields'][:6])==r[:6] and sha(d/'request')==meta['request_sha256']
 row={'case':name,'exit_code':e['exit_code'],'pid':e['events'][0]['pid'],'request_sha256':sha(d/'request'),'request_slot':meta['fields'][14],'input_basename':Path(meta['fields'][11]).name,'input_bytes':Path(meta['fields'][11]).stat().st_size,'input_sha256':sha(Path(meta['fields'][11])),'observations':o,'experiment_sha256':sha(d/'experiment.json'),'native_log_sha256':sha(d/'native.log'),'display':':100','remote_debugger_on_startup':False}
 assert e['exit_code']==0
 if name=='wrong-slot':
  assert r[8]=='success' and r[21]=='1' and Path(r[20]).name.endswith('_0.ppst')
  row['outcome']='Native accepts trusted caller slot metadata 1 for a file named slot 0; no filename-to-slot binding or authenticated frontend rejection demonstrated.'
 elif name=='truncated-matching-hash':
  assert r[8]=='failure' and not any(r[10:]) and row['input_bytes']==256 and row['input_sha256']==meta['fields'][12]
  row['outcome']='Matching-hash 256-byte truncated real state reaches native loader and fails; no positive completion.'
 else:
  first=json.loads((d/'first-run/experiment.json').read_text());r1=_decode_packet((d/'first-run/result').read_bytes(),b'TPSE1R\n',27)
  assert r==r1 and r[8]=='success' and r[7]=='1' and first['events'][0]['pid']!=row['pid']
  row.update(first_pid=first['events'][0]['pid'],first_result_sha256=sha(d/'first-run/result'),second_result_sha256=sha(d/'result'),second_run_interval=json.loads((d/'second-run-interval.json').read_text()),native_results_byte_identical=True)
  row['outcome']='Same private raw request reused in a fresh process succeeds again at sequence 1; native itself does not enforce one-time session consumption. Production retained context/sequence checks are separate.'
 if name!='replay-session':
  end=(d/'experiment.json').stat().st_mtime;row['approximate_utc_interval']={'start':datetime.datetime.fromtimestamp(end-e['elapsed_seconds'],datetime.timezone.utc).isoformat(),'end':datetime.datetime.fromtimestamp(end,datetime.timezone.utc).isoformat(),'method':'experiment file mtime minus monotonic duration; approximate reconstruction, not directly captured start UTC'}
 rows.append(row)
report={'schema':1,'baseline_report':'protocol-report.json','scope':'Additional real native raw-session observations after independent review','g04_status':'partial against complete authenticated roadmap acceptance','hardware_qualified':False,'qualified_profile_created':False,'authenticated_frontend_transfer_tested':False,'cases':rows,'independent_boundary_review':'slot-replay-boundary-review.json','contention':'Three initial launches overlapped controlled performance pair4-2x19:06:38–19:07:00UTC. Parent will exclude/repeat impacted measurements. Actual replay happened after soak START; native debugger disabled. These probes provide no isolated FPS evidence.','remaining_limits':['Wrong-slot and replay are accepted at the native trusted-caller boundary; do not label these as successful native rejection tests.','Independent envelope checks reject changed session context or stale sequence; full qualified consumer not exercised.','Publication failure remains pathname obstruction, not process-death or physical power-loss test.','No physical device acceptance or authenticated checkpoint promotion.']}
out=Path('/workspace/trimui-audit/native/additional-protocol-report.json');out.write_text(json.dumps(report,indent=2)+'\n');print(out,sha(out))
