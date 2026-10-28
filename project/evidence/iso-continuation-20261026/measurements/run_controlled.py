import os,subprocess,time,json,hashlib,shutil,configparser,datetime,platform
from pathlib import Path
ROOT=Path('/workspace/trimui-audit/measurements');OUT=ROOT/'controlled';OUT.mkdir(exist_ok=True)
BIN=Path('/workspace/trimui-audit/native/patched-build/PPSSPPSDL');ISO=Path('/workspace/trimui-audit/private-inputs/Grand Theft Auto - Vice City Stories (USA) (PSP) (PSN).iso');STATE=Path('/workspace/trimui-audit/desktop/scene-start/soldier-bike.ppst')
LIB='/workspace/trimui-audit/host-libs/usr/lib/x86_64-linux-gnu';XD='/workspace/trimui-audit/host-libs/usr/bin/xdotool'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
env=dict(os.environ,DISPLAY=':101',LD_LIBRARY_PATH=LIB,SDL_AUDIODRIVER='dummy',LIBGL_ALWAYS_SOFTWARE='1',LP_NUM_THREADS='2',DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent')
assert digest(BIN)=='6924b0392831517fb54108b98b9faa743492fe7d2709690098f91226fcdf56de'
assert digest(STATE)=='2d7b3d34a4b31c02e855444b1359c85630bf8bb6c34fb012fa4a4c33bb91e7b8'
wins=subprocess.run([XD,'search','--name','Grand Theft Auto'],env=env,text=True,capture_output=True)
if wins.returncode==0:
 w=wins.stdout.strip().splitlines()[-1];subprocess.run([XD,'windowfocus','--sync',w,'key','Escape'],env=env,check=True);time.sleep(3)
write(OUT/'scene.json',{'id':'soldier-office-bike-stationary-v1','state_sha256':digest(STATE),'description':'Outside office at Soldier objective before motorcycle entry; no input after 10-second warmup; fresh native process and identical state each repeat.','demanding_profile':False,'repeats':5,'duration':30,'arms':[1,2],'changed_setting':'Graphics.InternalResolution','frameskip':0,'automatic_frameskip':False,'comparison':'setting','soak':'single 1x stationary 1800-second host observation; not demanding-profile release acceptance','metrics':['native_fps','native_speed_percent'],'unavailable':['panel_frame_pacing','audio_faults','input_latency','battery_energy'],'order':'AB BA AB BA AB','host_only':True})
write(OUT/'environment.json',{'platform':platform.platform(),'machine':platform.machine(),'cpu_quota':Path('/sys/fs/cgroup/cpu.max').read_text().strip(),'renderer':'OpenGL Mesa software; LIBGL_ALWAYS_SOFTWARE=1 LP_NUM_THREADS=2','display':':101 Xvfb 960x600x24','audio':'SDL dummy; native mix-buffer WAV recording','isolation_shim_sha256':digest(ROOT/'instance_namespace-v2.so'),'isolation_scope':'Exact PPSSPP shared instance name remapped; optional discovery registration hostname fails locally; all other calls pass through.','native_binary_sha256':digest(BIN),'source':'d357e6a32934800d3d80b49f910a603e1b069751','device_tested':False,'measurement_started_utc':now(),'host_contention':'Packaging and file verification may overlap; no other native game process intentionally active.'})
for arm in (1,2):
 d=OUT/f'template-{arm}';d.mkdir(exist_ok=True)
 for src in Path('/workspace/trimui-audit/desktop/native-play/config/ppsspp/PSP/SYSTEM').glob('*.ini'):shutil.copy2(src,d/src.name)
 for p in d.glob('*.ini'):
  c=configparser.ConfigParser(interpolation=None,strict=False);c.optionxform=str;c.read(p,encoding='utf-8-sig')
  if p.name=='ppsspp.ini':
   for k,v in {'RemoteDebuggerOnStartup':'True','RemoteISOPort':'19362','RemoteDebuggerLocal':'True','DumpAudio':'True','SaveLoadResetsAVdumping':'True'}.items():c['General'][k]=v
  if p.name=='ULUS10160_ppsspp.ini':
   c['Graphics']['InternalResolution']=str(arm);c['Graphics']['FrameSkip']='0';c['Graphics']['AutoFrameSkip']='False';c['Graphics']['iShowStatusFlags']='6';c['General']['DumpAudio']='True'
  with p.open('w',encoding='utf-8-sig') as f:c.write(f)
order=[(i,a,30) for i in range(1,6) for a in ((1,2) if i%2 else (2,1))]+[(0,1,1800)]
for pair,arm,seconds in order:
 name=f'pair-{pair}-{arm}x' if pair else 'soak-1x';d=OUT/name;d.mkdir();cfg=d/'config';sysdir=cfg/'ppsspp/PSP/SYSTEM';shutil.copytree(OUT/f'template-{arm}',sysdir);state=d/'scene.ppst';shutil.copy2(STATE,state)
 local=dict(env,XDG_CONFIG_HOME=str(cfg),LD_PRELOAD=str(ROOT/'instance_namespace-v2.so'),TRIMUI_TEST_INSTANCE_SHM='/trimui-audit-controlled-'+name)
 cmd=[str(BIN),'--windowed','--xres','960','--yres','544','--graphics=opengl','--escape-exit','--state='+str(state),'--log='+str(d/'native.log'),str(ISO)]
 receipt={'run_id':name,'pair':pair,'resolution':arm,'requested_seconds':seconds,'start_utc':now(),'argv':cmd,'state_sha256':digest(state),'configuration_before':{p.name:digest(p) for p in sysdir.glob('*.ini')},'binary_sha256':digest(BIN),'private_paths':True};write(d/'receipt.json',receipt);print('START',name,now(),flush=True)
 with (d/'stdout.log').open('w') as stream:
  proc=subprocess.Popen(cmd,env=local,cwd=BIN.parent,stdout=stream,stderr=subprocess.STDOUT);receipt['pid']=proc.pid
  try:
   time.sleep(10)
   if proc.poll() is not None:raise RuntimeError('Native process exited before measurement')
   def shot(n):subprocess.run(['ffmpeg','-nostdin','-y','-f','x11grab','-video_size','960x600','-i',':101','-frames:v','1',str(d/n)],env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   shot('start.png');obs=['python',str(ROOT/'native_stats_observer.py'),'--port','19362','--binary',str(BIN),'--binary-sha256',digest(BIN),'--reviewed-corrected-build','--seconds',str(seconds),'--output',str(d/'observation.json')]
   with (d/'observer.log').open('w') as f:subprocess.run(obs,check=True,stdout=f,stderr=subprocess.STDOUT)
   shot('end.png');receipt['observation_complete']=True
  finally:
   if proc.poll() is None:
    w=subprocess.check_output([XD,'search','--name','Grand Theft Auto'],env=env,text=True).strip().splitlines()[-1];subprocess.run([XD,'windowfocus','--sync',w,'key','Escape'],env=env,check=True)
   receipt['exit_code']=proc.wait(timeout=30);receipt['end_utc']=now();receipt['configuration_after']={p.name:digest(p) for p in sysdir.glob('*.ini')};receipt['audio_files']=[{'path':str(p.relative_to(d)),'size':p.stat().st_size,'sha256':digest(p)} for p in cfg.rglob('*.wav')];write(d/'receipt.json',receipt)
  assert receipt['exit_code']==0
 print('DONE',name,now(),flush=True)
print('COMPLETE',now(),flush=True)
