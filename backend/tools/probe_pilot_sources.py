import json
from pathlib import Path
from types import SimpleNamespace
from app.research.evergreen import research_fetch,ArticleText,load_article,historical_claims
root=Path(__file__).resolve().parents[2];out=[]
urls=[('Cristiano Ronaldo','https://www.skysports.com/football/news/4575921/ronaldo-wins-ballon-dor'),('Cristiano Ronaldo','https://www.theguardian.com/football/2008/dec/02/ronaldo-manchesterunited'),('Thierry Henry','https://www.theguardian.com/football/2014/dec/16/thierry-henry-retires-arsenal-barcelona-france-fact-file-career')]
urls.extend([
 ('Thierry Henry','https://www.uefa.com/uefachampionsleague/news/024a-0e9cde622523-f2e7737dbd44-1000--thierry-henry-rejoins-monaco-why-he-s-a-big-deal/'),
 ('Thierry Henry','https://www.skysports.com/football/news/2297593/pfa-fans-player-of-the-year'),
 ('Thierry Henry','https://www.uefa.com/news-media/news/019c-0f8e9d0ccd0c-19183188d315-1000--henry-honoured-by-peers/'),
 ('Thierry Henry','https://www.theguardian.com/football/2004/apr/26/newsstory.sport5')])
for i,(name,url) in enumerate(urls):
 try:
  body,_=research_fetch(url);p=ArticleText();p.feed(body.decode('utf8',errors='replace'));(root/f'generated/source-probe-{i}.txt').write_text(p.text(),encoding='utf8')
  person=SimpleNamespace(name=name,keywords='[]',category='Football')
  a=load_article({'source_url':url,'title':name},person);claims=historical_claims(a,person,SimpleNamespace(niche='Football history'))
  out.append({'url':url,'claims':claims})
 except Exception as e:out.append({'url':url,'error':str(e)})
 print(out[-1],flush=True)
(root/'generated/pilot-source-probes.json').write_text(json.dumps(out,indent=2))
