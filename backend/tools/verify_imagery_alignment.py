import json,re,hashlib,collections,wave
from pathlib import Path
from app.video.alignment import load_boundaries,aligned_cues
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'generated/imagery-continuation'
before={j['id']:j for j in json.loads((OUT/'investigation.json').read_text())['pilots']}
updates={r['job_id']:r for r in json.loads((OUT/'updated-pilots.json').read_text())}
verified=json.loads((OUT/'verification/results.json').read_text());results=[]
def seconds(value):
 h,m,s=re.split('[:,]',value)[:3];millis=value.split(',')[1]
 return int(h)*3600+int(m)*60+int(s)+int(millis)/1000
for row in verified:
 j=row['job'];jid=j['id'];u=updates[jid];assert j['status']=='ready_for_review'
 audio=ROOT/'generated/audio'/f'{jid}.wav';timing=load_boundaries(audio,j['script']['full_script']);assert timing,'No valid native timing'
 render_timing=row['subtitle_timing'];assert render_timing['word_events']>0
 expected=aligned_cues(j['script']['full_script'],render_timing['rendered_narration_duration'],timing,6)
 blocks=re.findall(r'\d+\n([^\n]+) --> ([^\n]+)\n([^\n]+)',row['subtitles'])
 assert len(blocks)==len(expected)
 errors=[]
 for (start,end,text),(a,b,c) in zip(expected,blocks):
  assert text==c
  errors.extend([abs(start-seconds(a)),abs(end-seconds(b))])
 assert max(errors)<.0011
 assert all(seconds(b)<=seconds(blocks[i+1][0])+.001 for i,(a,b,c) in enumerate(blocks[:-1]))
 assert j['script']==before[jid]['script'] and j['content_revision']>before[jid]['content_revision'] and j['approval_count']==0
 assert row['scene_assets']=={'photo':4,'card':2}
 assert len({a['photo']['sha256'] for a in u['assignments']})==4
 assert all(a['attribution'] in j['seo']['description'] for a in j['assets'] if a['media_type']=='photo')
 new=Path(u['new_mp4_path']);assert hashlib.sha256(new.read_bytes()).hexdigest()==row['sha256'] and row['download']['sha256_matches']
 assert row['decode']['exit']==0 and row['anonymous_status']==401 and row['http_range']['status']==206
 with wave.open(str(audio),'rb') as a:format={'sample_rate':a.getframerate(),'channels':a.getnchannels(),'duration':a.getnframes()/a.getframerate()}
 result={'job_id':jid,'new_mp4_path':str(new),'content_revision':j['content_revision'],'scene_assets':row['scene_assets'],'script_unchanged':True,'stale_approvals':j['approval_count'],'native_provider':timing['provider'],'native_word_events':len(timing['words']),'source_wave':format,'source_audio_sha256':timing['audio_sha256'],'source_script_sha256':timing['script_sha256'],'max_caption_boundary_rounding_seconds':max(errors),'beginning_middle_end_cues':[blocks[i] for i in [0,len(blocks)//2,len(blocks)-1]],'all_script_words_covered':True,'rendered_narration_window':render_timing['rendered_narration_duration'],'listening':'Unverified: no human listening assessment','independent_ASR':'Unverified: constrained acoustic recognition did not produce complete matches','browser':'Unverified: Windows URL-confidence policy blocked local-app navigation; IAB timed out'}
 results.append(result);print(json.dumps(result),flush=True)
(OUT/'alignment-verification.json').write_text(json.dumps(results,indent=2),encoding='utf8')
