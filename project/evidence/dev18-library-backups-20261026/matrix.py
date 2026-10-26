import os,json,hashlib
from dataclasses import replace
from pathlib import Path
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
from psp_shell.ui.model import NavigationModel,UIItem,Dialog,DialogChoice,Keyboard
from psp_shell.ui.renderer import Renderer
OUT=Path('/tmp/trimui-dev18-renders'); records=[]
for scale in (.75,1,1.15,1.3,1.5,1.75):
 for confirm in ('south','east'):
  for contrast in (False,True):
   model=NavigationModel(demo=True,preferences={'text_scale':scale,'confirm':confirm,'high_contrast':contrast,'motion':False})
   model.set_category_items(0,[UIItem('one','Skyline Circuit: The Complete Championship Edition','Your existing collection',system_id='PSP',favorite=True),UIItem('two','Wind Harbor',system_id='PSP'),UIItem('three','Moonlit Post',system_id='GBA')])
   state=model.snapshot(display_clock='10/26 12:00')
   base=f'{round(scale*100):03d}-{confirm}-'+('contrast' if contrast else 'default')
   surfaces={
    'library':state,
    'dialog':replace(state,dialog=Dialog('Skyline Circuit: The Complete Championship Edition','A warning stays above the details.\n'+'Detailed information. '*35,tuple(DialogChoice(t) for t in ('Start game','Game information','Existing options','History','Back')),system_id='PSP')),
    'empty':replace(state,items=(),selected=0,total=0,empty_message='No games match your search. Edit the search or clear the selected system filter.'),
    'loading':replace(state,items=(),selected=0,total=0,loading=True,empty_message='Loading your collection…'),
    'error':replace(state,dialog=Dialog('Unable to complete that action','The requested backup is unavailable. Recheck its location before trying again.',error=True)),
    'keyboard':replace(state,keyboard=Keyboard('Before the final boss',0,title='Name this backup',submit_label='Save name'))}
   with Renderer(software=True) as renderer:
    for surface,snapshot in surfaces.items():
     name=f'{base}-{surface}.png'
     renderer.render(snapshot,0);renderer.save_screenshot(OUT/name)
     records.append({'file':name,'surface':surface,'text_scale':scale,'confirm':confirm,'high_contrast':contrast,'sha256':hashlib.sha256((OUT/name).read_bytes()).hexdigest()})
sources={name:hashlib.sha256((Path('project/psp_shell/ui')/name).read_bytes()).hexdigest() for name in ('renderer.py','text.py','keyboard.py','model.py')}
(OUT/'render-matrix.json').write_text(json.dumps({'scope':'Actual SDL host renders with synthetic metadata; no device qualification','source_sha256':sources,'count':len(records),'renders':records},indent=2)+'\n')
print(len(records),'host screenshots written')
