from pathlib import Path
import hashlib,json,configparser
ROOT=Path('/workspace/trimui-audit/measurements');CONTROLLED=ROOT/'controlled'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2)+'\n')
def identity(arm,soak=False):
 env=ROOT/('environment-soak.json' if soak else 'environment-pairs.json')
 p=CONTROLLED/f'template-{arm}/ULUS10160_ppsspp.ini';c=configparser.ConfigParser(interpolation=None);c.optionxform=str;c.read(p,encoding='utf-8-sig')
 values={section+'.'+k:v for section in ('CPU','Graphics','Sound','Control','SystemParam') for k,v in c[section].items()}
 return {'system_id':'PSP','game_id':'ULUS10160','game_title':'Grand Theft Auto: Vice City Stories','content_sha256':'e7d26d0efb2fb7a37bb73c51bddae9baffa39feab7d76e30299b4c9e5d6fc80a','scene_id':'soldier-office-bike-stationary-v1','scene_definition_sha256':sha(CONTROLLED/'scene.json'),'device_id':'cloud-x86_64-software-renderer-not-TG5040','environment_sha256':sha(env),'evidence_class':'host','emulator':{'id':'ppsspp-private-sdl-0001-0002-0003-0005','version':'v1.20.3','binary_sha256':'6924b0392831517fb54108b98b9faa743492fe7d2709690098f91226fcdf56de'},'settings':{'sha256':sha(p),'resolution':f'{arm}x','frameskip':'0 (automatic disabled)','values':values},'frontend_id':'direct-native-sdl-no-composed-frontend','intended_speed_percent':100}
if __name__=='__main__':
 host=json.loads((CONTROLLED/'environment.json').read_text());host.pop('measurement_started_utc');host.pop('host_contention')
 host['scope']='Selected isolated matched pairs; original contaminated pair4 retained and excluded. Shared host, not a controlled physical-device benchmark.';write(ROOT/'environment-pairs.json',host)
 host=dict(host,scope='Single stationary host stability run, concurrent independent native gameplay/menu checks. Not comparative or demanding-profile acceptance.');write(ROOT/'environment-soak.json',host)
 write(ROOT/'soak-resource-identity.json',identity(1,True));write(ROOT/'soak-resource-metadata.json',{'physical_device':False,'scope':'20-minute resource observation beginning after the first five minutes of 30-minute native-counter soak; not full-soak coverage','native_pid':31264,'concurrent_native_validation':True,'fps_from_resources':None})
