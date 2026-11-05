"""Offline visual-direction evidence using the already approved brief audition.

No provider requests, normal job mutations, uploads or publishing occur here.
This is not the complete Ronaldo pilot.
"""
import json
from pathlib import Path
from app.video.renderer import render_video
from app.video.alignment import write_character_boundaries

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'generated/quality-revision'


def main():
    audition=json.loads((OUT/'audition.json').read_text(encoding='utf8'))
    alignment=json.loads((OUT/'audition-alignment.json').read_text(encoding='utf8'))
    audio=OUT/'george-audition.wav'
    write_character_boundaries(audio,audition['text'],alignment['alignment'],
        'ElevenLabs original character alignment - eleven_multilingual_v2')
    photos=[p for p in json.loads((ROOT/'generated/imagery-continuation/curated-photos.json').read_text(encoding='utf8'))
            if p['subject']=='Ronaldo' and 'error' not in p]
    chosen=[photos[i] for i in (0,2,3)]
    output,_,_=render_video('ronaldo-visual-audition','Ronaldo 2008 award','Cristiano Ronaldo',
        audition['text'],audio,30,OUT/'visual-audition',[Path(p['path']) for p in chosen],
        'VISUAL AUDITION',subtitle_preset={'language':'en-US'},slide_kinds=['archive']*3,
        media_labels=['ARCHIVE '+p['capture_date'][:4]+' - NOT THE AWARD EVENT' for p in chosen],revision=1)
    (OUT/'visual-audition.json').write_text(json.dumps({'mp4_path':str(output),'kind':'short visual audition, not complete pilot',
        'voice':audition['voice'],'text':audition['text'],'photos':chosen,'new_synthesis_requests':0,
        'direct_listening':False,'full_Ronaldo_narration':'pending host approval availability'},indent=2),encoding='utf8')
    print(output,flush=True)


if __name__=='__main__':main()
