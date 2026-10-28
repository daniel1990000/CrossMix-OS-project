#!/usr/bin/env python3
# Import actual native point samples; no inferred frame/audio/device observations.
import sys,json,statistics,shutil,datetime
from pathlib import Path
sys.path.insert(0,'/workspace/TrimUi/project')
from tools.gameplay_benchmark import record,compare,validate_run
from import_config import ROOT,CONTROLLED,sha,write,identity
DEST=Path('/workspace/TrimUi/project/evidence/iso-continuation-20261026/measurements')
DEST.mkdir(parents=True,exist_ok=True)
def collect(folder,pair,arm,seconds,soak=False):
 receipt=json.loads((folder/'receipt.json').read_text());summary=json.loads((folder/'observation.json').read_text())
 assert receipt['exit_code']==0 and receipt['observation_complete']
 expected={p.name:sha(p) for p in (CONTROLLED/f'template-{arm}').glob('*.ini')}
 assert receipt['configuration_before']==expected,('Template identity mismatch',folder)
 assert sha(folder/'observation.raw.jsonl')==summary['raw_sha256']
 assert receipt['binary_sha256']==summary['binary_sha256']==identity(arm,soak)['emulator']['binary_sha256']
 rows=[json.loads(line) for line in (folder/'observation.raw.jsonl').read_text().splitlines()]
 status=[r for r in rows if r['message'].get('ticket')=='status-start'][0]
 finish=[r for r in rows if r['message'].get('ticket')=='status-end'][0]
 assert status['message']['game']['id']==finish['message']['game']['id']=='ULUS10160'
 assert not status['message']['paused'] and not finish['message']['paused']
 origin=status['elapsed_seconds'];all_samples=[r for r in rows if r['message'].get('event')=='gpu.stats.get']
 samples=[r for r in all_samples if 0<=r['elapsed_seconds']-origin<seconds]
 assert samples and summary['observed_seconds']>=seconds
 rid=folder.name if not soak else 'soak-1x'
 raw=DEST/'raw'/f'{rid}.jsonl';raw.parent.mkdir(exist_ok=True);shutil.copyfile(folder/'observation.raw.jsonl',raw)
 evidence=str(raw.relative_to(Path('/workspace/TrimUi')))
 fps=statistics.mean(r['message']['fps']['actual'] for r in samples)
 speed=statistics.mean(100*r['message']['vblanksPerSecond']['actual']/r['message']['vblanksPerSecond']['target'] for r in samples)
 def obs(v,unit):return {'value':v,'unit':unit,'method':'native-counter','evidence_file':evidence,'evidence_sha256':sha(raw),'start_seconds':0,'end_seconds':seconds}
 observations={'native_fps':obs(fps,'fps'),'native_speed_percent':obs(speed,'percent'),'frame_time_p95_ms':None,'audio_faults':None,'load_time_ms':None,'input_latency_ms':None,'battery_energy_wh':None}
 manifest={'identity':identity(arm,soak),'run_id':rid,'pair_id':f'pair-{pair}' if not soak else 'standalone-stationary-soak','duration_seconds':seconds,'sustained':soak,'demanding_profile':False}
 out=DEST/'runs'/f'{rid}.json';out.parent.mkdir(exist_ok=True)
 result=record(manifest,observations,out)
 result['analysis']={'window':'nominal analysis window [0,duration) anchored to retained status-start acknowledgement; measurement loop begins a few unrecorded Python instructions later','sampling':'Native counter point samples, not continuous frame accounting; each native counter itself covers its preceding update interval.','acquisition_observed_seconds':summary['observed_seconds'],'native_process_start_utc':receipt['start_utc'],'native_process_end_utc':receipt['end_utc'],'total_counter_responses':len(all_samples),'included_counter_responses':len(samples),'excluded_responses':[{'ticket':r['message']['ticket'],'elapsed_from_status_start':r['elapsed_seconds']-origin} for r in all_samples if r not in samples],'native_exit_code':receipt['exit_code'],'raw_unchanged_sha256':sha(raw),'native_fps_semantics':'PPSSPP CalculateFPS reports flips since its previous update once elapsed>=1s; not divided by actual elapsed. Quantization can produce30 vs31. VPS is normalized.','frame_audio_quality_reviewed':False,'shared_host_contention':soak,'native_configuration_before':receipt['configuration_before'],'native_configuration_after':receipt['configuration_after']}
 if pair==4:result['analysis']['replacement']='Repeated after all other native validation and soak; original pair4 overlapped short probes and is excluded.'
 write(out,result);validate_run(result,verify_files=True);return result
if __name__=='__main__':
 pairs=[]
 for pair in range(1,6):
  runs=[]
  for arm in (1,2):
   parent=ROOT/'rerun-pair4' if pair==4 else CONTROLLED
   folder=parent/f'pair-{pair}-{arm}x'
   runs.append(collect(folder,pair,arm,30))
  pairs.append(runs)
 comparison=compare([r[0] for r in pairs],[r[1] for r in pairs],metrics=['native_fps','native_speed_percent'],comparison='setting')
 comparison['interpretation']='Descriptive stationary desktop counters only. No preregistered numerical performance budget; no preset acceptance or speed-improvement claim. Other scenes and device demanding-profile tests remain unrun.'
 write(DEST/'comparison.json',comparison)
 soak=collect(CONTROLLED/'soak-1x',0,1,1800,True)
 for f in ('environment-pairs.json','environment-soak.json'):shutil.copyfile(ROOT/f,DEST/f)
 shutil.copyfile(CONTROLLED/'scene.json',DEST/'scene.json')
 for p in (ROOT/'native_stats_observer.py',ROOT/'run_controlled.py',ROOT/'run_pair4.py',ROOT/'import_config.py',Path(__file__),ROOT/'instance_namespace.c'):
  if p.exists():shutil.copyfile(p,DEST/p.name)
 excluded=DEST/'excluded';excluded.mkdir(exist_ok=True)
 for arm in (1,2):
  f=CONTROLLED/f'pair-4-{arm}x';shutil.copyfile(f/'observation.raw.jsonl',excluded/f'pair-4-{arm}x.jsonl');shutil.copyfile(f/'observation.json',excluded/f'pair-4-{arm}x-summary.json')
 write(excluded/'reason.json',{'reason':'Native negative probes overlapped original pair4-2x; both arms retained and replaced. Interval reconstruction approximate from experiment mtime minus monotonic duration.','overlap_utc':['2026-10-26T19:06:38.477Z','2026-10-26T19:07:00.276Z'],'probe_cases':['wrong-slot','truncated-matching-hash','replay-session-first-attempt']})
 print(json.dumps({'pairs':5,'soak_seconds':soak['duration_seconds'],'metrics':comparison['metrics']},indent=2))
 import subprocess
 subprocess.run(['python',str(ROOT/'audio_inventory.py')],check=True)
 shutil.copyfile(ROOT/'audio_inventory.py',DEST/'audio_inventory.py')
