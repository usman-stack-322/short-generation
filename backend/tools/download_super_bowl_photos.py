import hashlib,json
from pathlib import Path
from urllib.parse import quote
from types import SimpleNamespace
from app.services.assets.licensed import download_photo,fetch
from app.services.assets.policy import license_allowed,photo_supported
folder=Path('../generated/super-bowl-script');items=json.loads((folder/'curated-photo-manifest.json').read_text());assets=[]
for i,item in enumerate(items):
 name=item['file'];h=hashlib.md5(name.encode()).hexdigest();item['download_url']='https://upload.wikimedia.org/wikipedia/commons/'+h[0]+'/'+h[:2]+'/'+quote(name)
 assert license_allowed(item['license'],item['license_url'],item['creator']) and photo_supported(item)
 asset=download_photo(item,SimpleNamespace(scene_number=i+1),folder/'curated-assets','context')
 original=asset.local_path.with_name(asset.local_path.stem+'-source.jpg')
 assets.append({'path':str(original.resolve()),'hash':hashlib.sha256(original.read_bytes()).hexdigest(),'source_url':item['url'],'creator':item['creator'],'license':item['license'],'license_url':item['license_url'],'credit':asset.provenance['required_credit'],'kind':'licensed_photo','note':item['description'],'provenance':asset.provenance})
 print(json.dumps({'scene':i+1,'path':str(original.resolve()),'license':item['license']}))
 (folder/'curated-assets.json').write_text(json.dumps(assets,indent=2))
