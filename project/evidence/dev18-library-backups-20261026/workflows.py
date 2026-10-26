import os,json,time,tempfile,hashlib
from pathlib import Path
from dataclasses import replace
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
from psp_shell.app import Dispatcher
from psp_shell.demo import DemoBackend
from psp_shell.settings import SettingsStore
from psp_shell.ui.model import NavigationModel
from psp_shell.ui.renderer import Renderer
from psp_shell.backup_catalog import BackupCatalog
from psp_shell.recovery import BackupHistoryAdapter
from tools.recovery_payload import backup
OUT=Path('/tmp/trimui-dev18-renders'); base=Path(tempfile.mkdtemp(prefix='dev18-reviewed-workflows-'))
source=base/'offline-source';source.mkdir();payloads=base/'payloads';payloads.mkdir()
catalog=BackupCatalog(base/'state'/'backups.json',forbidden_roots=(source,))
for index in range(70):
 (source/'memory-card.sav').write_bytes((f'Synthetic saved progress {index}\n'*40).encode())
 path=payloads/f'backup-{index:03d}';backup(source,path,'saves');catalog.register(path,f'Backup {index:03d}',note='Synthetic offline review fixture')
def hashes(root):
 return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
original_source,original_payloads=hashes(source),hashes(payloads)
adapter=BackupHistoryAdapter(catalog.path,forbidden_roots=(source,))
backend=DemoBackend();dispatcher=Dispatcher(backend,SettingsStore(str(base/'preferences')),base/'preferences',backup_adapter=adapter)
model=NavigationModel(demo=True); trace=[];captures=[]
def sync(commands):
 queue=list(commands)
 while queue:
  c=queue.pop(0)
  result=dispatcher.dispatch(c.method,c.params)
  trace.append({'method':c.method,'params':dict(c.params),'state':result.get('state') if isinstance(result,dict) else None})
  queue.extend(model.receive(c,result))
def act(action,text=''):sync(model.handle(action,text))
def choose(label):
 dialog=model.snapshot().dialog
 assert dialog is not None,('No dialog',label)
 for _ in dialog.choices:
  d=model.snapshot().dialog
  if d.choices[d.selected].title==label:
   act('confirm');return
  act('down')
 raise AssertionError(('Missing choice',label,[c.title for c in model.snapshot().dialog.choices]))
def select(identifier):
 for _ in model.snapshot().items:
  if model.snapshot().selected_item.id==identifier:
   act('confirm');return
  act('down')
 raise AssertionError(('Missing item',identifier))
def capture(name):
 with Renderer(software=True) as renderer:
  renderer.render(model.snapshot(display_clock='10/26 12:00'),0);renderer.save_screenshot(OUT/(name+'.png'))
 captures.append({'file':name+'.png','sha256':hashlib.sha256((OUT/(name+'.png')).read_bytes()).hexdigest()})
sync(model.initial_commands())
model.preferences=replace(model.preferences,text_scale=1.75,motion=False)
select('all');act('menu');capture('flow-library-tools')
choose('System: All systems');capture('flow-system-choices');choose('Game Boy Advance')
act('menu');choose('Search this view');act('text','Island');act('submit_text');capture('flow-filtered-search')
assert [i.title for i in model.snapshot().items]==['Small Island']
act('menu');choose('Surprise me');capture('flow-scoped-surprise');act('back');act('back')
select('collections');capture('flow-collections');select('sample:collection:later');capture('flow-collection-games')
act('back');select('manage_collections');capture('flow-native-management-guidance');act('back');act('back')
select('help');capture('flow-controls-help');choose('Text size');capture('flow-text-size-choices');choose('175%');choose('Apply');
act('back') if model.snapshot().dialog else None
# The settings apply is real; force only motion off for deterministic captures.
model.preferences=replace(model.preferences,motion=False)
while model.category!=3:act('right')
select('backup');capture('flow-backup-status');choose('Named backup history');capture('flow-history-first')
for _ in range(3):choose('Next backups')
capture('flow-history-after64');choose('Backup 004');capture('flow-backup-detail')
choose('Back to history');returned=model.snapshot().dialog.choices[model.snapshot().dialog.selected].title
assert returned == 'Backup 004', returned
choose('Backup 004');choose('Rename label');capture('flow-backup-rename')
for _ in range(len(model.snapshot().keyboard.text)):act('delete_text')
act('text','Before update – renamed');act('submit_text');capture('flow-backup-renamed-detail')
assert model.snapshot().dialog.title=='Before update – renamed'
choose('Check backup bytes');capture('flow-backup-check-job')
deadline=time.monotonic()+10
while model._backup_job and time.monotonic()<deadline:
 sync(model.poll_commands(time.monotonic()))
 if adapter._thread:adapter._thread.join(.02)
assert not model._backup_job
capture('flow-backup-checked-detail')
choose('Rename label');act('back')
rename_cancel_dialog=model.snapshot().dialog.title if model.snapshot().dialog else None
assert rename_cancel_dialog == 'Before update – renamed', rename_cancel_dialog
capture('flow-backup-rename-cancelled')
# Independent stale-read reproduction: selecting another game must reject the old details.
late=NavigationModel();late.set_category_items(0,[{'game_id':'a','label':'Game A'},{'game_id':'b','label':'Game B'}]);late._capabilities={'game_information':True}
late.handle('confirm');late.handle('down');pending=late.handle('confirm')[0];late.handle('down')
late.receive(pending,{'game_id':'a','label':'Game A','system_id':'PSP'})
assert late.snapshot().dialog is None

result={'scope':'Actual SDL host captures from real Dispatcher/model/backup catalog responses; synthetic metadata and offline payloads; no emulator game or device evidence',
 'stale_game_info_rejected_after_focus_change':late.snapshot().dialog is None,
 'catalog_entries':len(catalog.read()['entries']),'selected_history_index':65,'history_return_selection':returned,'rename_cancel_dialog':rename_cancel_dialog,
 'source_preserved':hashes(source)==original_source,'payloads_preserved':hashes(payloads)==original_payloads,
 'captures':captures,'commands':trace,'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('project/psp_shell/ui/model.py'),Path('project/psp_shell/ui/renderer.py'),Path('project/psp_shell/demo.py'),Path('project/psp_shell/recovery.py'),Path('project/psp_shell/backup_catalog.py')]}}
assert result['source_preserved'] and result['payloads_preserved']
(OUT/'workflow-review.json').write_text(json.dumps(result,indent=2)+'\n')
adapter.close()
print(json.dumps({k:v for k,v in result.items() if k not in ('commands','captures','source_sha256')},indent=2))
print(len(captures),'actual workflow captures')
