"""Rendered evidence, rather than filter-string presence, for the quality path."""
import hashlib
import io
import json
import math
import struct
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw
from app.core.config import settings
from app.video.alignment import write_character_boundaries, load_boundaries
from app.video.editorial import edit_timeline
from app.video.photo_framing import compose_photo


def test_retained_original_is_used_instead_of_padded_preview(tmp_path):
    from app.services.assets.licensed import prepare_photo
    body=io.BytesIO();Image.new('RGB',(800,500),'#43965b').save(body,'JPEG')
    preview=tmp_path/'photo.jpg';prepare_photo(body.getvalue(),preview,'Archive photo')
    original=preview.with_name('photo-source.jpg')
    assert Image.open(original).size==(800,500)
    info=compose_photo(preview,tmp_path/'composition.jpg')
    assert info['source']==str(original)
    assert 'blurred' in info['treatment']
    frame=Image.open(tmp_path/'composition.jpg')
    assert frame.size==(2160,3840)
    assert sum(frame.getpixel((0,0)))>30  # The photo, not a black matte, fills the frame.


def test_edit_follows_sentence_beats_and_centers_overlap():
    script='First short sentence. A longer second sentence tells the story.'
    words=[]
    import re
    for i,m in enumerate(re.finditer(r'\S+',script)):
        words.append({'char':m.start(),'length':len(m.group()),'start':i*.5})
    beats,changes,segments=edit_timeline(6,2,timing={'words':words},script=script)
    assert beats[1]['start']==1.5  # Actual second sentence, not halfway through the video.
    change=changes[0]
    assert change['offset']+change['duration']/2==pytest.approx(1.5)
    assert sum(segments)-sum(c['duration'] for c in changes)==pytest.approx(6)


def test_character_alignment_keeps_original_caption_spelling(tmp_path):
    path=tmp_path/'voice.wav';text="2008 Ballon d'Or."
    with wave.open(str(path),'wb') as w:
        w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(b'\x10\x01'*32000)
    alignment={'characters':list(text),'character_start_times_seconds':[i*.06 for i in range(len(text))],
               'character_end_times_seconds':[(i+1)*.06 for i in range(len(text))]}
    write_character_boundaries(path,text,alignment,'Fixture character alignment')
    assert load_boundaries(path,text)
    assert ' '.join(w['text'] for w in load_boundaries(path,text)['words'])==text
    with pytest.raises(ValueError,match='unchanged script'):
        write_character_boundaries(path,'Two thousand eight.',alignment,'Fixture')


def test_silence_edits_preserve_word_events_and_remap_captions():
    import array
    from app.video.final_audio import silence_edits,remap_time
    samples=array.array('h',[1200]*8000+[0]*12800+[1400]*8000+[0]*19200)
    timing={'words':[{'start':.1,'end':.4},{'start':1.4,'end':1.65}]}
    intervals,cuts=silence_edits(samples,16000,1,timing)
    assert len(intervals)==2 and len(cuts)==2
    assert cuts[0]['end']-cuts[0]['start']==pytest.approx(.42)
    assert remap_time(1.4,cuts)==pytest.approx(.98)
    assert remap_time(3,cuts)==pytest.approx(1.52)
    assert not any(c['start']<w['start']<c['end'] for c in cuts for w in timing['words'])


def test_latest_preview_and_download_select_same_immutable_revision(publishable):
    from app.database.session import SessionLocal
    from app.models import VideoJob
    from app.api.media import media_link
    p=publishable
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id']);old=Path(job.video.output_path)
        new=old.parent/'revision-2'/'short.mp4';new.parent.mkdir();new.write_bytes(b'new revision bytes')
        job.content_revision=job.media_revision=job.video.media_revision=2
        job.video.output_path=str(new);job.video.status='ready_for_review';db.commit()
    response=p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()
    assert '/revision-2/short.mp4?' in response['video_url']
    current=p['client'].get(response['video_url']+'&download=true',headers=p['owner'])
    assert current.status_code==200 and current.content==b'new revision bytes'
    assert current.headers['x-content-revision']=='2' and 'no-store' in current.headers['cache-control']
    stale=media_link(old.resolve().relative_to(Path(settings.generated_dir).resolve()).as_posix())+'&revision=2'
    assert p['client'].get(stale,headers=p['owner']).status_code==409
    with SessionLocal() as db:
        job=db.get(VideoJob,p['job_id']);job.media_revision=3;job.video.status='outdated';db.commit()
    assert p['client'].get('/api/videos/'+p['job_id'],headers=p['owner']).json()['video_url'] is None
    assert p['client'].get(response['video_url'],headers=p['owner']).status_code==409


def test_actual_export_has_motion_dissolve_and_consistent_frame(tmp_path):
    from app.video.renderer import render_video
    slides=[]
    for i,color in enumerate(((25,115,40),(25,35,155))):
        im=Image.new('RGB',(720,1280),color);d=ImageDraw.Draw(im)
        for x in range(0,720,90):d.line((x,0,x,1280),fill=(80,80,80),width=3)
        d.ellipse((260,420,460,620),fill=(235,25,25))
        path=tmp_path/f'photo{i}.jpg';im.save(path);slides.append(path)
    voice=tmp_path/'voice.wav'
    with wave.open(str(voice),'wb') as w:
        w.setparams((1,2,16000,0,'NONE','not compressed'))
        w.writeframes(b''.join(struct.pack('<h',int(1200*math.sin(i*2*math.pi*220/16000))) for i in range(48000)))
    output,_,_=render_video('real-motion','Fixture','Fixture','This fixture tests real motion.',voice,30,tmp_path/'output',slides,revision=7)
    assert output.parent.name=='revision-7' and not (output.parent.parent/'short.mp4').exists()
    def frame(t):
        p=subprocess.run([settings.ffmpeg_path,'-v','error','-ss',str(t),'-i',str(output),'-frames:v','1','-f','image2pipe','-vcodec','png','-'],capture_output=True,check=True,timeout=30)
        return Image.open(io.BytesIO(p.stdout)).convert('RGB')
    a,b=frame(.15),frame(1.25)
    def red_width(im):
        mask=Image.new('1',im.size)
        mask.putdata([r>130 and g<70 and b<70 for r,g,b in im.getdata()])
        bounds=mask.getbbox();assert bounds
        return bounds[2]-bounds[0]
    assert red_width(b)>red_width(a)*1.035  # A measured landmark changes size in exported frames.
    timeline=json.loads((output.parent/'render-timeline.json').read_text())
    boundary=timeline['transitions'][0]['at']
    middle=frame(boundary);before=frame(boundary-.3);after=frame(boundary+.3)
    pixel=lambda im:im.getpixel((100,450))
    assert pixel(before)[1]>pixel(before)[2] and pixel(after)[2]>pixel(after)[1]
    assert pixel(middle)[1]>30 and pixel(middle)[2]>30  # Both images contribute at the dissolve.
    assert middle.size==(1080,1920)
    assert sum(middle.getpixel((100,1870)))>60  # No reserved dark caption panel.
    command=json.loads((output.parent/'render-command.json').read_text())
    assert not any('drawtext=' in part or 'drawbox=' in part or 'editorial-scrim' in part for part in command)
    subprocess.run([settings.ffmpeg_path,'-v','error','-i',str(output),'-f','null','-'],check=True,capture_output=True,timeout=60)


@pytest.fixture
def publishable(owner_publishable):
    # Channel access is per-member, so owner-driven flows use a channel owned by the OWNER membership.
    return owner_publishable
