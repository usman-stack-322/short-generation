"""Use synthesis word boundaries only when bound to the exact script and WAV."""
import hashlib,json,re
from pathlib import Path

def load_boundaries(audio,script):
    try:
        path=Path(audio);data=json.loads(path.with_suffix('.words.json').read_text(encoding='utf8'))
        if data['audio_sha256']!=hashlib.sha256(path.read_bytes()).hexdigest() or data['script_sha256']!=hashlib.sha256(script.encode()).hexdigest():return None
        words=data['words'];duration=float(data['duration'])
        if not words or duration<=0:return None
        previous=-1
        for word in words:
            start=float(word['start']);char=int(word['char']);length=int(word['length'])
            if not 0<=start<=duration or start<previous or not 0<=char<char+length<=len(script):return None
            previous=start
        if any(not any(w['char']<=m.start()<w['char']+w['length'] for w in words) for m in re.finditer(r'\w+',script)):return None
        return data
    except (OSError,ValueError,KeyError,TypeError):return None

def aligned_cues(script,duration,timing,max_words=6,sentence_aware=False,scene_boundaries=()):
    tokens=list(re.finditer(r'\S+',script));scale=duration/timing['duration'];groups=[];group=[]
    def token_time(token):
        return min(w['start'] for w in timing['words'] if w['char']<token.end() and w['char']+w['length']>token.start())*scale
    if not sentence_aware:
        groups=[tokens[i:i+max_words] for i in range(0,len(tokens),max_words)]
    else:
        # Group by sentence and picture beat before balancing 3-6 word phrases.
        for token in tokens:
            if group and any(token_time(group[0])<at<=token_time(token)+.001 for at in scene_boundaries):
                groups.append(group);group=[]
            group.append(token)
            if re.search(r'[.!?؟。！？]$',token.group()):groups.append(group);group=[]
        if group:groups.append(group)
        balanced=[]
        import math
        for group in groups:
            count=max(1,math.ceil(len(group)/max_words))
            for i in range(count):
                balanced.append(group[round(i*len(group)/count):round((i+1)*len(group)/count)])
        groups=balanced
    cues=[]
    for chunk in groups:
        start=token_time(chunk[0]);text=' '.join(m.group() for m in chunk)
        cues.append((start,duration,text))
    return [(start,cues[i+1][0] if i+1<len(cues) else duration,text)
            for i,(start,_,text) in enumerate(cues)]


def write_character_boundaries(audio,text,alignment,provider):
    """Bind provider character timing to original display text and decoded WAV."""
    import wave,math
    path=Path(audio)
    chars=alignment.get('characters',[])
    starts=alignment.get('character_start_times_seconds',[])
    ends=alignment.get('character_end_times_seconds',[])
    if ''.join(chars)!=text or len(starts)!=len(text) or len(ends)!=len(text):
        raise ValueError('Provider alignment does not cover the unchanged script')
    with wave.open(str(path)) as w:duration=w.getnframes()/w.getframerate()
    previous=-1
    for start,end in zip(starts,ends):
        if not math.isfinite(start) or not math.isfinite(end) or not 0<=start<=end<=duration+.01 or start<previous:
            raise ValueError('Provider returned invalid narration timestamps')
        previous=start
    words=[{'char':m.start(),'length':m.end()-m.start(),'start':starts[m.start()],
            'end':ends[m.end()-1],'text':m.group()} for m in re.finditer(r'\S+',text)]
    data={'provider':provider,'script_sha256':hashlib.sha256(text.encode()).hexdigest(),
          'audio_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'duration':duration,'words':words}
    path.with_suffix('.words.json').write_text(json.dumps(data,indent=2),encoding='utf8')
    if not load_boundaries(path,text):raise ValueError('Incomplete narration alignment')
    return data
