import copy,hashlib,json
from pathlib import Path
from app.database.session import SessionLocal
from app.models import TitleShortDraft
from app.services.assets.policy import license_allowed,photo_supported
folder=Path('../generated/super-bowl-script');assets=json.loads((folder/'curated-assets.json').read_text());manifest=json.loads((folder/'curated-photo-manifest.json').read_text())
assert len(assets)==3 and len({a['hash'] for a in assets})==3
for a,item in zip(assets,manifest):
 assert license_allowed(a['license'],a['license_url'],a['creator']) and photo_supported(item)
 assert hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()==a['hash']
 if item.get('expected_sha1'):
  p=a['provenance'];key=hashlib.sha256((p['download_url']+p['license']+(p.get('sha1') or '')).encode()).hexdigest();raw=folder.parent/'cache'/'photos'/(key+'.bin')
  assert hashlib.sha1(raw.read_bytes()).hexdigest()==item['expected_sha1']
with SessionLocal() as db:
 d=db.get(TitleShortDraft,'83aed818-f7ff-489f-80fc-4573f844d628')
 if d.revision!=14 or d.status!='failed':raise RuntimeError('Draft changed; refusing to overwrite')
 data=json.loads(d.data);before=copy.deepcopy(data)
 data.setdefault('visual_history',[]).append({'revision':d.revision,'assets':data.get('assets',[]),'plan':copy.deepcopy(data['plan'])})
 data['assets']=assets
 for s,a in zip(data['plan']['scenes'],assets):
  s['visual_description']=a['note'];s['image_query']=a['provenance']['title']
 data['scope'].pop('accepted_fingerprint',None);data['scope'].pop('accepted_by',None);data['scope'].pop('accepted_at',None)
 assert data['sources']==before['sources'] and [s['narration'] for s in data['plan']['scenes']]==[s['narration'] for s in before['plan']['scenes']]
 changed=db.query(TitleShortDraft).filter_by(id=d.id,revision=14,status='failed').update({'revision':15,'status':'script_review','error_message':None,'data':json.dumps(data,ensure_ascii=False)},synchronize_session=False)
 if changed!=1:db.rollback();raise RuntimeError('Concurrent edit')
 db.commit()
 print(json.dumps({'revision':15,'status':'script_review','licensed_unique_photos':3,'narration_unchanged':True,'photo_sha1_checks_passed':True}))
