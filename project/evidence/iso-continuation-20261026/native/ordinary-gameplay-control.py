import datetime,json,os,subprocess,sys,time
from pathlib import Path
root=Path('/workspace/trimui-audit/gameplay');active=json.loads((root/'active.json').read_text());env=dict(os.environ,DISPLAY=':100',LD_LIBRARY_PATH='/workspace/trimui-audit/host-libs/usr/lib/x86_64-linux-gnu');xd='/workspace/trimui-audit/host-libs/usr/bin/xdotool';start=time.monotonic();utc=datetime.datetime.now(datetime.timezone.utc).isoformat();action=sys.argv[1]
if action=='key':
 keys=sys.argv[2].split('+');duration=float(sys.argv[3]) if len(sys.argv)>3 else .3
 wins=subprocess.check_output([xd,'search','--pid',str(active['pid'])],env=env,text=True).splitlines();subprocess.run([xd,'windowfocus','--sync',wins[-1]],env=env,check=True)
 subprocess.run([xd,'keydown',*keys],env=env,check=True)
 try:time.sleep(duration)
 finally:subprocess.run([xd,'keyup',*keys],env=env,check=True)
elif action=='shot':
 out=root/'screens'/sys.argv[2];out.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run(['ffmpeg','-nostdin','-y','-f','x11grab','-video_size','960x600','-i',':100','-frames:v','1',str(out)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
else:raise ValueError(action)
with (root/'actions.jsonl').open('a') as f:f.write(json.dumps({'argv':sys.argv[1:],'utc':utc,'monotonic_start':start,'monotonic_end':time.monotonic(),'pid':active['pid']})+'\n')
