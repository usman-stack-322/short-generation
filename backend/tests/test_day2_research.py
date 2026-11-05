from datetime import datetime,timedelta,timezone
import json
from app.research.live import assess,similar
from app.services.scene_planner import plan_scenes
from app.video.subtitles import write_subtitles
from app.ai.scripts import GeminiProvider
import pytest


def story(title='Ronaldo scores twice in international match',source='bbc.com',hours=1):
    return {'title':title,'summary':'A report about Ronaldo and the match.',
            'source_name':source,'source_domain':source,'source_url':'https://'+source+'/report',
            'published_at':(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat(),'reliability_score':.9}


def test_ranking_requires_corroboration_and_rejects_stale_rumors_duplicates():
    rows=[story(),story(source='espn.com')]
    rows[1]['title']='International match: Ronaldo scores twice'
    ranked=assess(rows,'Ronaldo',[],[])
    assert all(r['status']=='verified' for r in ranked)
    assert .8<ranked[0]['overall_score']<=1
    assert json.dumps(ranked)
    assert assess([story()],'Ronaldo',[],[])[0]['status']=='verification_required'
    assert assess([story(hours=100)],'Ronaldo',[],[])[0]['status']=='rejected'
    assert assess([story('Ronaldo reportedly may join a club')],'Ronaldo',[],[])[0]['status']=='rejected'
    assert assess(rows,'Ronaldo',[],[rows[0]['title']])[0]['status']=='rejected'
    assert similar('Ronaldo scores twice in international match','Ronaldo scores twice in international match - BBC')


@pytest.mark.parametrize('claim',['Ronaldo suffers injury','Ronaldo arrested','Ronaldo transfer agreed','Ronaldo died','Ronaldo medical update','Ronaldo let the team down'])
def test_sensitive_claims_always_require_source_review(claim):
    rows=[story(claim),story(claim,source='espn.com')]
    assert all(row['status']=='verification_required' for row in assess(rows,'Ronaldo',[],[]))


def test_scene_plan_covers_narration_and_timing():
    text=' '.join(f'word{i}' for i in range(100))
    scenes=plan_scenes(text,45,'Ronaldo')
    assert 6<=len(scenes)<=12
    assert scenes[0]['start_time']==0 and scenes[-1]['end_time']==45
    assert ' '.join(scene['narration'] for scene in scenes)==text
    assert all(a['end_time']==b['start_time'] for a,b in zip(scenes,scenes[1:]))


def test_highlight_subtitle_preset(tmp_path):
    ass,srt=tmp_path/'test.ass',tmp_path/'test.srt'
    write_subtitles('Short captions remain readable',5,ass,srt,{'subtitle_mode':'word-highlight','font_size':60,'max_words':4,'highlight_color':'#61e8b6'})
    text=ass.read_text()
    assert 'Arial,60' in text and r'\c&Hb6e861&' in text
    assert text.count('Dialogue:')==4
    assert '00:00:05,000' in srt.read_text()


def test_gemini_malformed_response_retries_are_bounded(monkeypatch):
    calls=[]
    def malformed(self,prompt): calls.append(prompt);raise ValueError('bad JSON')
    monkeypatch.setattr(GeminiProvider,'_request',malformed)
    from app.ai.reliability import GeminiGenerationError
    with pytest.raises(GeminiGenerationError,match='invalid structured output'): GeminiProvider().generate('test prompt')
    assert len(calls)==2
