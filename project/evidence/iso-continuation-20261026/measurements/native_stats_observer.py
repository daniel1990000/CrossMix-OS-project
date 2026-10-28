#!/usr/bin/env python3
"""Private read-only PPSSPP observer. Requires independently reviewed corrected binary."""
import argparse,asyncio,datetime,hashlib,json,math,pathlib,statistics,time
import websockets

p=argparse.ArgumentParser()
p.add_argument('--port',type=int,required=True)
p.add_argument('--binary',type=pathlib.Path,required=True)
p.add_argument('--binary-sha256',required=True)
p.add_argument('--reviewed-corrected-build',action='store_true',required=True)
p.add_argument('--seconds',type=float,default=30)
p.add_argument('--interval',type=float,default=1)
p.add_argument('--output',type=pathlib.Path,required=True)
a=p.parse_args()
if not(1<=a.port<=65535 and 1<=a.seconds<=3600 and .25<=a.interval<=10):p.error('Invalid port/duration/interval')
digest=hashlib.sha256(a.binary.read_bytes()).hexdigest()
if digest!=a.binary_sha256:p.error('Executable hash mismatch')
if a.output.exists():p.error('Output already exists')
a.output.parent.mkdir(parents=True,exist_ok=True)
raw=a.output.with_suffix('.raw.jsonl')
if raw.exists():p.error('Raw output exists')

async def run():
 rows=[];messages=[];start=time.monotonic();run_id=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with raw.open('x') as stream:
  def retain(message):
   row={'elapsed_seconds':time.monotonic()-start,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'message':message}
   stream.write(json.dumps(row,allow_nan=False)+'\n');stream.flush();messages.append(row);return row
  async with websockets.connect(f'ws://127.0.0.1:{a.port}/debugger',subprotocols=['debugger.ppsspp.org'],proxy=None,compression=None,max_size=1048576) as ws:
   async def request(event,ticket,**kw):
    await ws.send(json.dumps({'event':event,'ticket':ticket,**kw}))
    deadline=time.monotonic()+10
    while True:
     msg=json.loads(await asyncio.wait_for(ws.recv(),max(.01,deadline-time.monotonic())))
     row=retain(msg)
     if msg.get('ticket')==ticket:
      if msg.get('event')=='error':raise RuntimeError(msg)
      return row
   version=await request('version','version',name='trimui-private-host-observer',version='1')
   status=await request('game.status','status-start')
   if status['message'].get('game',{}).get('id')!='ULUS10160' or status['message'].get('paused'):raise RuntimeError('Wrong game or paused')
   measure_start=time.monotonic();i=0
   while time.monotonic()-measure_start<a.seconds:
    row=await request('gpu.stats.get',f'sample-{i}');m=row['message']
    for key in ['fps','vblanksPerSecond']:
     for field in ['actual','target']:
      v=m[key][field]
      if not isinstance(v,(float,int)) or not math.isfinite(v) or v<0:raise RuntimeError('Invalid native value')
    if m['vblanksPerSecond']['target']<=0:raise RuntimeError('Invalid speed denominator')
    rows.append(row);i+=1
    await asyncio.sleep(max(0,min(a.interval,a.seconds-(time.monotonic()-measure_start))))
   final=await request('game.status','status-end')
   if final['message'].get('game',{}).get('id')!='ULUS10160' or final['message'].get('paused'):raise RuntimeError('Game changed or paused')
   measured=time.monotonic()-measure_start
 speeds=[r['message']['vblanksPerSecond']['actual']/r['message']['vblanksPerSecond']['target']*100 for r in rows]
 fps=[r['message']['fps']['actual'] for r in rows]
 summary={'kind':'private-host-native-counter-observation','run_id':run_id,'evidence_class':'host','binary_sha256':digest,'source_endpoint':'gpu.stats.get','version':version['message'],'samples':len(rows),'requested_seconds':a.seconds,'observed_seconds':measured,'interval_seconds':a.interval,'native_fps':{'mean':statistics.mean(fps),'median':statistics.median(fps),'minimum':min(fps),'maximum':max(fps)},'native_speed_percent':{'mean':statistics.mean(speeds),'median':statistics.median(speeds),'minimum':min(speeds),'maximum':max(speeds),'formula':'100 * vblanksPerSecond.actual / vblanksPerSecond.target; intended display refresh must be 60Hz'},'raw_path':str(raw),'raw_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'frame_time_p95_ms':None,'audio_faults':None,'hardware_qualified':False,'limits':['Counter sampling is native emulator evidence, not panel FPS or physical latency.','Frame histories not aggregated: circular histories overlap and need separately validated deduplication.','No audio quality or real-device inference.','Reviewed source-to-binary correspondence is a prerequisite external to this observer.']}
 a.output.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
asyncio.run(run())
