import json
from pathlib import Path
import pytest
from PIL import Image
from app.video.scene_motion import validate_scene_plan,planned_motion
from app.video.photo_framing import compose_photo
from app.tts.scene_direction import narration_plan
from app.video.subtitles import write_subtitles
from app.video.import_scene_plan import load_scene_assets

def scene():
    return {'purpose':'context','visual_type':'archival_photo','motion':{'type':'push_in','amount':.04}}

def test_unsafe_or_undisclosed_generated_assets_fail():
    plan=scene();plan['visual_type']='ai_illustration'
    with pytest.raises(ValueError,match='provenance'):validate_scene_plan([plan],1)
    plan['generation']={'provider':'user supplied','model':'declared-model','prompt':'conceptual empty pitch'}
    with pytest.raises(ValueError,match='disclosure'):validate_scene_plan([plan],1)
    plan['disclosure']='AI illustration';assert validate_scene_plan([plan],1)
    plan['motion']['amount']=float('nan')
    with pytest.raises(ValueError,match='travel'):validate_scene_plan([plan],1)

def test_motion_varies_by_explicit_plan_and_stills_need_reason():
    a=scene();b=scene();b['motion']['type']='pan_left'
    assert planned_motion(150,(.5,.2),a)!=planned_motion(150,(.5,.2),b)
    b['motion']['type']='hold'
    with pytest.raises(ValueError,match='reason'):validate_scene_plan([b],1)

def test_native_detail_is_not_enlarged_in_foreground(tmp_path):
    source=tmp_path/'source.jpg';Image.new('RGB',(800,1200),'red').save(source)
    output=tmp_path/'composition.png';info=compose_photo(source,output,native_limit=True,max_zoom=1.1)
    assert 'fitted foreground' in info['treatment']
    im=Image.open(output);pixels=im.load()
    # Sharp red foreground remains <= native width after 2x working canvas and max zoom.
    y=im.height//2;sharp=[x for x in range(im.width) if pixels[x,y][0]>240 and pixels[x,y][1]<5]
    assert len(sharp)/2*1.1<=801

def test_ai_disclosure_is_scoped_and_does_not_duplicate_captions(tmp_path):
    ass=tmp_path/'captions.ass';srt=tmp_path/'captions.srt'
    write_subtitles('A factual sentence.',4,ass,srt,{'illustration_intervals':[(1,2)]})
    body=ass.read_text();assert '0:00:01.00,0:00:02.00,Disclosure' in body
    assert body.count(',,AI illustration')==1 and 'AI illustration' not in srt.read_text()
    assert 'BorderStyle' in body and 'Default,,0,0,0,,A factual sentence.' in body

def test_voice_intent_never_becomes_claimed_emotion_control():
    plan=narration_plan([{'text':'Two seasons.','purpose':'achievement'}],'bm_george','kokoro_onnx')
    assert 'emotion instructions' in plan['unsupported_controls']
    assert not any(k in plan['engine_controls'] for k in ['emotion','pitch','intensity'])
    assert plan['script']=='Two seasons.' and plan['naturalness_approved'] is False

def test_import_requires_real_files_and_rights_not_placeholder_stock(tmp_path):
    im=tmp_path/'photo.jpg';Image.new('RGB',(600,800),'green').save(im)
    plan=scene();plan['asset_path']=str(im);path=tmp_path/'plan.json';path.write_text(json.dumps({'scenes':[plan]}))
    with pytest.raises(ValueError,match='rights'):load_scene_assets(path,tmp_path)
    plan.update(source_url='https://example.test/photo',license='CC BY 2.0',license_url='https://creativecommons.org/licenses/by/2.0/',creator='Fixture')
    path.write_text(json.dumps({'scenes':[plan]}));data,files=load_scene_assets(path,tmp_path)
    assert len(data['scenes'][0]['asset_sha256'])==64 and files==[im]


def test_explicit_scene_words_anchor_to_native_audio_not_equal_slots():
    from app.video.editorial import edit_timeline
    text='A short opening. A longer closing sentence.'
    words=[{'char':0,'length':1,'start':0}, {'char':2,'length':5,'start':.2},
           {'char':8,'length':8,'start':.5}, {'char':17,'length':1,'start':1.8},
           {'char':19,'length':6,'start':2}, {'char':26,'length':7,'start':2.4},
           {'char':34,'length':9,'start':2.8}]
    plans=[{**scene(),'text':'A short opening.'},{**scene(),'text':'A longer closing sentence.','transition_in':'cut'}]
    beats,changes,_=edit_timeline(4,2,timing={'words':words},script=text,scene_plan=plans)
    assert beats[1]['start']==1.8 and changes[0]['type']=='cut'
    plans[1]['text']='Missing story.'
    with pytest.raises(ValueError,match='unchanged script'):edit_timeline(4,2,timing={'words':words},script=text,scene_plan=plans)
