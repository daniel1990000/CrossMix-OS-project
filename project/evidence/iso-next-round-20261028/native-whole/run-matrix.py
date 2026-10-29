from pathlib import Path
import json,subprocess,sys
base=Path(__file__).parent;out=base/'matrix';out.mkdir()
points=('state-before-rename','snapshot-partial-write','snapshot-before-fsync','snapshot-after-fsync','result-partial-write','result-before-rename','completion-before-rename','completion-after-rename')
common=[sys.executable,str(base/'run-v4-frozen.py'),'--engine','/workspace/trimui-audit/native/candidate-0006/PPSSPPSDL','--iso','/workspace/trimui-audit/private-inputs/Grand Theft Auto - Vice City Stories (USA) (PSP) (PSN).iso']
for point in points:
 with (out/(point+'.log')).open('wb') as log:r=subprocess.run(common+['--output',str(out/point),'--point',point],stdout=log,stderr=subprocess.STDOUT)
 print(json.dumps({'point':point,'returncode':r.returncode}),flush=True)
 if r.returncode:raise SystemExit(r.returncode)
report=json.loads((out/'result-before-rename/report.json').read_text())
with (out/'fresh-load.log').open('wb') as log:r=subprocess.run(common+['--output',str(out/'fresh-load'),'--point','fresh-load','--resume',report['previous_state_path']],stdout=log,stderr=subprocess.STDOUT)
print(json.dumps({'point':'fresh-load','returncode':r.returncode}),flush=True)
raise SystemExit(r.returncode)
