"""Private native-only deterministic process interruption; no qualified profile."""
import argparse, hashlib, json, os, secrets, shutil, signal, subprocess, sys, time
from pathlib import Path
sys.path.insert(0,'/workspace/TrimUi/project')
from psp_shell.state_evidence import encode_packet, _decode_packet, PrivateStateSession, StateEvidenceError
from types import SimpleNamespace
p=argparse.ArgumentParser();p.add_argument('--engine',required=True,type=Path);p.add_argument('--iso',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--point',required=True);p.add_argument('--resume',type=Path);a=p.parse_args()
base=Path(__file__).parent;engine=a.engine.resolve(strict=True);iso=a.iso.resolve(strict=True);out=a.output.resolve();out.mkdir(mode=0o700)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
engine_sha=sha(engine);assert engine_sha=='a9ab92b11c0ae64654fc884d125caa435d6a3f5805a52def07e7de2db883b9c2'
assert iso.stat().st_size==1696006144 and sha(iso)=='e7d26d0efb2fb7a37bb73c51bddae9baffa39feab7d76e30299b4c9e5d6fc80a'
config=out/'config';system=config/'ppsspp/PSP/SYSTEM';system.mkdir(parents=True)
(system/'ppsspp.ini').write_text('[General]\nFirstRun = False\nEnableCheats = False\nEnablePlugins = False\nAutoLoadSaveState = 0\nStateSlot = 0\n[Graphics]\nInternalResolution = 1\nFrameSkip = 0\nAutoFrameSkip = False\n[Sound]\nEnable = True\n')
(system/'controls.ini').write_text('[ControlMapping]\nSave State = 1-132\nPause = 1-111\n')
root=(config/'ppsspp/PSP/PPSSPP_STATE').resolve();root.mkdir()
state=a.resume.resolve(strict=True) if a.resume else None
if state: root=state.parent.parent
session=out/'session';session.mkdir(mode=0o700)
fields=(secrets.token_hex(16),secrets.token_hex(16),secrets.token_hex(16),Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'1','native-only:ULUS10160',str(iso),'e7d26d0efb2fb7a37bb73c51bddae9baffa39feab7d76e30299b4c9e5d6fc80a',engine_sha,str(root),'resume' if state else 'save',str(state) if state else '',sha(state) if state else '','ppsspp:d357e6a32934800d3d80b49f910a603e1b069751:chunk5-savestart3','0')
request=session/'request';request.write_bytes(encode_packet(b'TPSE1Q\n',fields));request.chmod(0o600)
cmd=[str(engine),'--graphics=opengl','--escape-exit','--log='+str(out/'native.log'),'--project-state-session='+str(request)]
if state:cmd+=['--state='+str(state)]
cmd+=[str(iso)]
overrides=dict(DISPLAY=':102',XDG_CONFIG_HOME=str(config),SDL_AUDIODRIVER='dummy',SDL_VIDEODRIVER='x11',LIBGL_ALWAYS_SOFTWARE='1',LD_LIBRARY_PATH='/workspace/trimui-audit/host-libs/usr/lib/x86_64-linux-gnu',DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent',LD_PRELOAD=str(base/'interruption-hook.so'),TRIMUI_INTERRUPT_EXECUTABLE=str(engine),TRIMUI_INTERRUPT_COMMAND=str(out/'command'),TRIMUI_INTERRUPT_MARKER=str(out/'marker.json'),TRIMUI_INTERRUPT_SESSION=str(session))
env=dict(os.environ,**overrides)
inner=out/'inner.py';inner.write_text('import json,os,pathlib\np=pathlib.Path('+repr(str(out))+')\np.joinpath("process.json").write_text(json.dumps({"pid":os.getpid(),"start_ticks":int(pathlib.Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19])}))\nos.execve('+repr(str(engine))+','+repr(cmd)+',dict(os.environ,**'+repr(overrides)+'))\n')
# Runtime credentials are inherited at exec; the helper serializes only the
# explicitly selected nonsecret test overrides, never the process environment.
inner.chmod(0o600)
supervisor=out/'supervise.py';supervisor.write_text('import json,sys,os\nfrom pathlib import Path\nsys.path.insert(0,"/workspace/TrimUi/project")\nfrom bridge.principal import run_owned_tree\nos.chdir('+repr(str(engine.parent))+')\nr=run_owned_tree([sys.executable,'+repr(str(inner))+'])\nPath('+repr(str(out/'supervision.json'))+').write_text(json.dumps({"root_pid":r.root_pid,"exit_status":r.exit_status,"children_reaped":r.children_reaped}))\n')
log=(out/'stdout.log').open('wb');parent=subprocess.Popen([sys.executable,str(supervisor)],stdout=log,stderr=subprocess.STDOUT)
xd='/workspace/trimui-audit/host-libs/usr/bin/xdotool';xenv=dict(os.environ,DISPLAY=':102',LD_LIBRARY_PATH=env['LD_LIBRARY_PATH']);events=[];started=time.monotonic_ns();pid=None
report=dict(kind='actual-whole-native-interruption',profile_created=False,consumer_scope='real transport/envelope/sequence with explicit refusal stub; no qualified profile validation',engine_sha256=engine_sha,shim_sha256=sha(base/'interruption-hook.so'),shim_source_sha256=sha(base/'interruption-hook.c'),iso_sha256=fields[7],iso_size=iso.stat().st_size,point=a.point,request_sha256=sha(request),frozen_initial_config_sha256=sha(system/'ppsspp.ini'),frozen_controls_sha256=sha(system/'controls.ini'),argv=cmd)
def event(name,**kw):
 row=dict(event=name,elapsed_ns=time.monotonic_ns()-started,**kw);events.append(row);(out/'events.jsonl').open('a').write(json.dumps(row)+'\n')
def ensure_owned():
 assert pid is not None and Path('/proc/'+str(pid)+'/exe').resolve()==engine
 assert int(Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19])==identity['start_ticks']
def key(name):
 ensure_owned();ids=subprocess.check_output([xd,'search','--onlyvisible','--pid',str(pid)],env=xenv,text=True).splitlines();wid=ids[-1]
 subprocess.run([xd,'windowfocus','--sync',wid],env=xenv,check=True)
 subprocess.run([xd,'keydown',name],env=xenv,check=True);time.sleep(.2);subprocess.run([xd,'keyup',name],env=xenv,check=True);event('key',key=name,window_id=wid)
def wait_for_result(sequence,timeout=120):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  if (session/'result').is_file():
   try:
    result=_decode_packet((session/'result').read_bytes(),b'TPSE1R\n',27)
    if int(result[7])>=sequence:return result
   except Exception:pass
  if parent.poll() is not None:raise RuntimeError('native exited early '+str(parent.returncode))
  time.sleep(.1)
 raise TimeoutError('missing native result')
try:
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  if (out/'process.json').is_file():
   identity=json.loads((out/'process.json').read_text());pid=identity['pid']
   try:ensure_owned();break
   except (AssertionError,FileNotFoundError):pass
  time.sleep(.1)
 else:raise TimeoutError('native process identity unavailable')
 report.update(pid=pid,start_ticks=identity['start_ticks']);event('launched',pid=pid)
 if not state:time.sleep(20);key('F2')
 first=wait_for_result(1);assert first[8]=='success',first
 event('first_completed',operation=first[6],sequence=first[7],state_sha256=first[16])
 for name in ['result','save-completed','load-completed']:
  if (session/name).is_file():shutil.copy2(session/name,out/('previous-'+name))
 prior_state=Path(first[20]);assert sha(prior_state)==first[16]
 report['previous_state_path']=str(prior_state);report['previous_state_sha256']=first[16]
 if state:
  assert first[6]=='load' and first[16]==fields[12] and first[20]==fields[11] and first[21]==fields[14]
  key('Escape');parent.wait(timeout=40);assert json.loads((out/'supervision.json').read_text())['exit_status']==0;report['normal_fresh_process_load']=True
 else:
  (out/'command').write_text(a.point+'\n');event('armed',point=a.point)
  key('F2')
  deadline=time.monotonic()+120
  while time.monotonic()<deadline and not (out/'marker.json').exists():
   if parent.poll() is not None:raise RuntimeError('native exited before interruption')
   time.sleep(.02)
  assert (out/'marker.json').is_file(),'interruption not reached'
  marker=json.loads((out/'marker.json').read_text());assert marker['pid']==pid and marker['point']==a.point
  deadline=time.monotonic()+2
  while time.monotonic()<deadline and '\nState:\tT' not in Path('/proc/'+str(pid)+'/status').read_text():time.sleep(.005)
  assert '\nState:\tT' in Path('/proc/'+str(pid)+'/status').read_text()
  ensure_owned();os.kill(pid,signal.SIGKILL);event('killed_owned_stopped_native',marker=marker)
  parent.wait(timeout=40)
  latest=_decode_packet((session/'result').read_bytes(),b'TPSE1R\n',27)
  completion=_decode_packet((session/'save-completed').read_bytes(),b'TPSE1R\n',27)
  assert sha(prior_state)==first[16]
  assert int(completion[7])<=int(latest[7])
  if a.point=='result-partial-write':assert (session/'result.tmp').stat().st_size==9
  if a.point=='result-before-rename':assert _decode_packet((session/'result.tmp').read_bytes(),b'TPSE1R\n',27)[7]=='2'
  if a.point=='completion-before-rename':assert _decode_packet((session/'save-completed.tmp').read_bytes(),b'TPSE1R\n',27)[7]=='2'
  if a.point=='state-before-rename':assert list(root.glob('*.ppst.tmp'))
  if a.point.startswith('snapshot-'):
   copies=[p for p in (root/'.trimui-state-snapshots').iterdir() if p!=prior_state]
   assert len(copies)==1
   if a.point=='snapshot-partial-write':assert copies[0].stat().st_size==9
   else:assert sha(copies[0])==sha(next(root.glob('ULUS10160_1.03_0.ppst')))
  assert latest[7]==('2' if a.point in ('completion-before-rename','completion-after-rename') else '1'), ('unexpected publication progress',latest[7],a.point)
  assert completion[7]==('2' if a.point=='completion-after-rename' else '1')
  if latest[7]==completion[7]:assert latest==completion
  assert sha(Path(completion[20]))==completion[16]
  transport=SimpleNamespace(_directory=os.open(session,os.O_RDONLY|os.O_DIRECTORY),_fields=fields)
  transport._read_result=lambda name='result':PrivateStateSession._read_result(transport,name)
  transport._validate_result_envelope=lambda result,minimum_sequence=1:PrivateStateSession._validate_result_envelope(transport,result,minimum_sequence)
  reached=[]
  def unqualified(*args):
   reached.append(args[-1]);raise StateEvidenceError('STATE_PROFILE_UNQUALIFIED','No qualified profile supplied')
  transport._consume_result=unqualified
  try:
   values,error=PrivateStateSession.consume_completed(transport,None,None)
   assert values==() and error=='STATE_PROFILE_UNQUALIFIED' and reached==[completion]
  finally:os.close(transport._directory)
  report.update(prior_snapshot_preserved=True,final_sequence=latest[7],completion_sequence=completion[7],bounded_valid_completion=True,qualification_gate='STATE_PROFILE_UNQUALIFIED')
 report['supervision']=json.loads((out/'supervision.json').read_text());report['passed']=True
except BaseException as error:
 report.update(passed=False,error=type(error).__name__+': '+str(error));event('failure',error=report['error'])
finally:
 if parent.poll() is None:
  try:
   if pid:ensure_owned();os.kill(pid,signal.SIGCONT);key('Escape');parent.wait(timeout=20)
  except Exception:
   if pid:
    try:ensure_owned();os.kill(pid,signal.SIGKILL)
    except Exception:pass
   parent.wait(timeout=30)
 log.close();report.update(elapsed_ns=time.monotonic_ns()-started,events=events)
 # Drop runtime credentials after execution. No environment-bearing inner script
 # is retained as reviewable evidence; retain only generic script/hash identities.
 inner.unlink(missing_ok=True)
 report['runner_sha256']=sha(Path(__file__))
 report['artifacts']={str(path.relative_to(out)):{'sha256':sha(path),'size':path.stat().st_size} for path in sorted(out.rglob('*')) if path.is_file()}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('events','artifacts','argv')},indent=2),flush=True)
if not report.get('passed'):raise SystemExit(1)
