"""Import real user-provided images; never replace generation with stock search."""
import json,hashlib
from pathlib import Path
from PIL import Image
from app.video.scene_motion import validate_scene_plan
from app.services.assets.policy import license_allowed

def load_scene_assets(path, workspace):
    workspace=Path(workspace).resolve();data=json.loads(Path(path).read_text(encoding='utf8'))
    scenes=validate_scene_plan(data['scenes'],len(data['scenes']))
    paths=[]
    for scene in scenes:
        source=Path(scene['asset_path']).resolve()
        if workspace not in source.parents or not source.is_file():
            raise ValueError('Copy imported media into the workspace first')
        if source.stat().st_size>30*1024*1024:raise ValueError('Imported still exceeds size limit')
        if scene['visual_type']=='licensed_clip':
            if source.suffix.lower()!='.mp4':raise ValueError('A clip must be a genuine MP4')
        else:
            with Image.open(source) as im:
                if min(im.size)<400 or im.width*im.height>40_000_000:raise ValueError('Image resolution is unsuitable')
                im.verify()
        if scene['visual_type']!='ai_illustration':
            if not all(scene.get(k) for k in ('source_url','license','creator')):
                raise ValueError('Real media requires source and rights records')
            if not license_allowed(scene['license'],scene.get('license_url',''),scene['creator']):
                raise ValueError('Imported real media fails the existing license policy')
        elif scene.get('rights_confirmed') is not True or not scene.get('rights_basis'):
            raise ValueError('Imported generated media needs explicit rights confirmation and terms basis')
        scene['asset_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        paths.append(source)
    return data,paths
