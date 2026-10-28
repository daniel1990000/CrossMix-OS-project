"""Private native SDL protocol experiment; no device/foreground authority is minted."""
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0,'/workspace/TrimUi/project')
from psp_shell.state_evidence import _decode_packet
p=argparse.ArgumentParser();p.add_argument('--session',required=True,type=Path);p.add_argument('--config',required=True,type=Path);p.add_argument('--case',choices=['save','save-failure','resume','resume-save','invalid-engine','interrupted-result'],required=True);p.add_argument('--initial-wait',type=float,default=20)
a=p.parse_args();meta=json.loads((a.session/'probe.json').read_text());fields=meta['fields'];engine=Path('/workspace/trimui-audit/native/patched-build/PPSSPPSDL')
env=dict(os.environ,DISPLAY=':100',XDG_CONFIG_HOME=str(a.config.resolve()),SDL_AUDIODRIVER='dummy',SDL_VIDEODRIVER='x11',LIBGL_ALWAYS_SOFTWARE='1',LD_LIBRARY_PATH='/workspace/trimui-audit/host-libs/usr/lib/x86_64-linux-gnu')
cmd=[str(engine),'--graphics=opengl','--escape-exit','--log='+str(a.session/'native.log'),'--project-state-session='+str(a.session/'request')]
if fields[10]=='resume':cmd+=['--state='+fields[11]]
cmd+=[fields[6]]
xd='/workspace/trimui-audit/host-libs/usr/bin/xdotool';events=[];start=time.monotonic();stdout=(a.session/'stdout.log').open('wb');proc=subprocess.Popen(cmd,cwd=str(engine.parent),env=env,stdout=stdout,stderr=subprocess.STDOUT)
def event(name,**kw):
 events.append(dict(event=name,elapsed=round(time.monotonic()-start,3),**kw));print(json.dumps(events[-1]),flush=True)
def key(name):
 ids=subprocess.check_output([xd,'search','--pid',str(proc.pid)],env=env,text=True).splitlines();wid=ids[-1]
 subprocess.run([xd,'windowfocus','--sync',wid],env=env,check=True)
 subprocess.run([xd,'keydown',name],env=env,check=True);time.sleep(.3);subprocess.run([xd,'keyup',name],env=env,check=True);event('key',key_name=name)
def wait_result(seq,seconds=75):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  q=a.session/'result'
  if q.is_file():
   try:
    r=_decode_packet(q.read_bytes(),b'TPSE1R\n',27)
    if int(r[7])>=seq:event('native_result',sequence=int(r[7]),status=r[8],operation=r[6],message=r[9]);return r
   except Exception:pass
  if proc.poll() is not None:raise RuntimeError('engine exited before result: '+str(proc.returncode))
  time.sleep(.5)
 raise TimeoutError('No native final result for sequence '+str(seq))
result={'case':a.case,'kind':'native-only-protocol-experiment','command':cmd,'evidence_class':'desktop-native','hardware_qualified':False,'profile_created':False}
state_root=Path(fields[9]);mode=state_root.stat().st_mode&0o777
try:
 event('start',pid=proc.pid)
 if a.case=='invalid-engine':
  proc.wait(timeout=20);result['exit_code']=proc.returncode;result['native_result_present']=(a.session/'result').exists()
 else:
  if fields[10]=='save':time.sleep(a.initial_wait);key('F2')
  if a.case=='interrupted-result':
   end=time.monotonic()+75
   while time.monotonic()<end and not (a.session/'load-completed').is_file():time.sleep(.5)
   receipt=a.session/'load-completed'
   if not receipt.is_file():raise TimeoutError('No independent native load completion')
   r=_decode_packet(receipt.read_bytes(),b'TPSE1R\n',27)
   event('independent_native_completion',sequence=int(r[7]),status=r[8],operation=r[6])
   time.sleep(1)
   result['load_completed_status']=r[8]
   result['final_result_regular_file']=(a.session/'result').is_file()
   result['publication_failure_injected']='directory occupying final result pathname'
   key('Escape');proc.wait(timeout=30);result['exit_code']=proc.returncode
  else:
   first=wait_result(1);result['first_operation_status']=first[8]
  for name in ['result','save-completed','load-completed']:
   x=a.session/name
   if x.is_file():(a.session/('first-'+name)).write_bytes(x.read_bytes())
  if a.case=='save-failure':
   if first[8]!='success':raise RuntimeError('initial save did not complete')
   os.chmod(state_root,0o500);event('state_root_readonly');key('F2');second=wait_result(2);result['second_operation_status']=second[8];os.chmod(state_root,mode)
  if a.case=='resume-save':
   if first[8]!='success':raise RuntimeError('initial load did not complete')
   key('F2');second=wait_result(2);result['second_operation_status']=second[8]
  if a.case!='interrupted-result':subprocess.run(['ffmpeg','-nostdin','-y','-f','x11grab','-video_size','960x600','-i',':100','-frames:v','1',str(a.session/'screen.png')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
  if a.case!='interrupted-result':key('Escape');proc.wait(timeout=30);result['exit_code']=proc.returncode
except Exception as e:
 result['error']=str(e);event('failure',message=str(e))
finally:
 os.chmod(state_root,mode)
 if proc.poll() is None:
  try:key('Escape');proc.wait(timeout=15)
  except Exception:proc.terminate();proc.wait(timeout=15);result['forced_termination']=True
 stdout.close();result['elapsed_seconds']=round(time.monotonic()-start,3);result['events']=events
 (a.session/'experiment.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2),flush=True)
 if 'error'in result:sys.exit(1)
