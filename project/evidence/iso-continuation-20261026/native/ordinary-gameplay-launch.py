import datetime,hashlib,json,os,subprocess,sys,time
from pathlib import Path
root=Path('/workspace/trimui-audit/gameplay');run=root/sys.argv[1];run.mkdir(mode=0o700)
engine=Path('/workspace/trimui-audit/native/patched-build/PPSSPPSDL');rom=Path('/workspace/trimui-audit/private-inputs/Grand Theft Auto - Vice City Stories (USA) (PSP) (PSN).iso')
cmd=[str(engine),'--graphics=opengl','--escape-exit','--log='+str(run/'native.log')]
if len(sys.argv)>2:cmd+=['--state='+sys.argv[2]]
cmd+=[str(rom)]
env=dict(os.environ,DISPLAY=':100',XDG_CONFIG_HOME=str(root/'config'),SDL_AUDIODRIVER='dummy',SDL_VIDEODRIVER='x11',LIBGL_ALWAYS_SOFTWARE='1',LD_LIBRARY_PATH='/workspace/trimui-audit/host-libs/usr/lib/x86_64-linux-gnu',DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent')
meta={'kind':'ordinary-gameplay-host-native','argv':cmd,'display':':100','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'started_monotonic':time.monotonic(),'engine_sha256':hashlib.sha256(engine.read_bytes()).hexdigest(),'initial_state':sys.argv[2] if len(sys.argv)>2 else None,'hardware_qualified':False,'cheats_or_game_modifications':False}
with (run/'stdout.log').open('wb') as f:
 p=subprocess.Popen(cmd,cwd=str(engine.parent),env=env,stdout=f,stderr=subprocess.STDOUT);meta['pid']=p.pid;(root/'active.json').write_text(json.dumps(meta,indent=2));(run/'running.json').write_text(json.dumps(meta,indent=2));code=p.wait()
meta.update(exit_code=code,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),finished_monotonic=time.monotonic());(run/'receipt.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps(meta),flush=True)
