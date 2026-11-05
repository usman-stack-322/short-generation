import json,re
from pathlib import Path
root=Path(__file__).resolve().parents[2]
rows=json.loads((root/'generated/fresh-verification/results.json').read_text())
for r in rows:
 j=r['job'];print(r['subject'],j['status'],j.get('script_provider'),j.get('voice_provider'))
 if j.get('script'):print(j['script']['full_script'])
 if 'probe' not in r:continue
 p=json.loads(r['probe']['stdout']);print('streams',[(s['codec_type'],s.get('width'),s.get('height')) for s in p['streams']],'duration',p['format']['duration'])
 print('decode',r['decode']['exit'],'audio',re.findall(r'(?:mean_volume|max_volume):[^\n]+',r['signal']['stderr']))
 print('blackdetect',re.findall(r'black_start:[^\n]+',r['blank_frames']['stderr']))
 print('download',r['download'],'anonymous',r['anonymous_status'],'range',r['http_range'])
 print('verification',j['verification']);print('caption end',r['subtitles'][-200:])
