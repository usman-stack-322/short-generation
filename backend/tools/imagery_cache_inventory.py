import json,socket,ssl,time
from pathlib import Path
from app.services.assets.licensed import CommonsAssetProvider
from app.services.assets.policy import license_allowed,photo_supported
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'generated/imagery-continuation'
files=list((ROOT/'generated').glob('**/cache/wikimedia/*.json'));candidates={};entities={};search=[]
for path in files:
 try:data=json.loads(json.loads(path.read_text(encoding='utf8'))['body'])
 except Exception:continue
 for key,value in data.get('entities',{}).items():entities[key]=value
 for page in data.get('query',{}).get('pages',{}).values():
  title=page.get('title','')
  if not any(n in title.casefold() for n in ['ronaldo','messi','henry']):continue
  info=page.get('imageinfo',[{}])[0];meta=info.get('extmetadata',{});camera={v.get('name'):str(v.get('value','')) for v in info.get('metadata',[]) if isinstance(v,dict)}
  get=lambda key:meta.get(key,{}).get('value','')
  from app.services.assets.licensed import plain
  getplain=lambda key:plain(get(key))
  item={'source':'commons','url':info.get('descriptionurl'),'download_url':info.get('thumburl') or info.get('url'),'original_image_url':info.get('url'),'creator':getplain('Artist'),'license':getplain('LicenseShortName'),'license_url':getplain('LicenseUrl'),'title':title,'description':getplain('ImageDescription'),'categories':getplain('Categories'),'date':getplain('DateTimeOriginal'),'original_source':getplain('Credit'),'width':info.get('width'),'height':info.get('height'),'sha1':info.get('sha1'),'media_id':'M'+str(page.get('pageid')),'camera_make':camera.get('Make'),'camera_model':camera.get('Model'),'metadata_cache':str(path)}
  if license_allowed(item['license'],item['license_url'],item['creator']) and photo_supported(item):candidates.setdefault(item['url'],item)
for item in candidates.values():
 entity=entities.get(item['media_id'],{});claims=entity.get('statements',entity.get('claims',{}))
 item['depicts']=[c.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') for c in claims.get('P180',[])]
result={'cache_files':len(files),'candidates':list(candidates.values()),'tls':[]}
for host in ['commons.wikimedia.org','upload.wikimedia.org','www.wikidata.org']:
 entry={'host':host};start=time.monotonic()
 try:
  with socket.create_connection((host,443),timeout=5) as sock:
   entry['tcp_connected']=True
   with ssl.create_default_context().wrap_socket(sock,server_hostname=host) as secured:entry.update(tls_verified=True,version=secured.version())
 except Exception as exc:entry.update(tls_verified=False,error_type=type(exc).__name__,error=str(exc))
 entry['elapsed']=round(time.monotonic()-start,2);result['tls'].append(entry)
(OUT/'cache-inventory.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps({'cache_files':len(files),'tls':result['tls'],'candidates':[{'title':i['title'],'license':i['license'],'depicts':i['depicts'],'url':i['url']} for i in candidates.values()]},indent=2))
