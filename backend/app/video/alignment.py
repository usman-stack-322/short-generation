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


def _word_phonetic_weight(token: str) -> float:
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', token)
    vowels = len(re.findall(r'[aeiouyAEIOUY]+', cleaned))
    base = max(0.9, vowels * 0.95 + len(cleaned) * 0.14) if cleaned else max(0.8, len(token) * 0.4)
    if re.search(r'[.!?؟。！？]["\'\)]*$', token):
        base += 1.4
    elif re.search(r'[,;:–—]["\'\)]*$', token):
        base += 0.75
    return base


def write_acoustic_word_boundaries(audio, text: str, provider: str = 'Gemini Studio TTS'):
    """Align spoken words to real WAV speech energy islands and pause valleys."""
    import array
    import math
    import wave

    path = Path(audio)
    with wave.open(str(path), 'rb') as wf:
        sr = wf.getframerate()
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
    duration = nframes / max(1, sr)
    matches = list(re.finditer(r'\S+', text))
    if not matches or duration <= 0 or sampwidth != 2:
        raise ValueError('Cannot align empty script or unsupported WAV format')

    samples = array.array('h')
    samples.frombytes(raw)
    if channels > 1:
        samples = array.array('h', samples[::channels])

    win = max(1, sr // 100)  # 10ms analysis frame
    rms = []
    for i in range(0, len(samples), win):
        block = samples[i:i + win]
        if not block:
            break
        rms.append(math.sqrt(sum(s * s for s in block) / len(block)))

    peak = max(rms) if rms else 0.0
    thresh = max(160.0, peak * 0.045)
    active = [v >= thresh for v in rms]
    # Bridge micro-dips (< 80ms = 8 frames) inside continuous words while preserving sentence pauses
    gap = 0
    for idx in range(len(active)):
        if not active[idx]:
            gap += 1
        else:
            if 0 < gap <= 8 and idx - gap > 0:
                for k in range(idx - gap, idx):
                    active[k] = True
            gap = 0

    islands = []
    in_seg = False
    seg_start = 0
    for idx, flag in enumerate(active):
        if flag and not in_seg:
            seg_start = idx * 0.01
            in_seg = True
        elif not flag and in_seg:
            seg_end = min(duration, idx * 0.01)
            if seg_end - seg_start >= 0.05:
                islands.append((seg_start, seg_end))
            in_seg = False
    if in_seg:
        seg_end = duration
        if seg_end - seg_start >= 0.05:
            islands.append((seg_start, seg_end))

    if not islands:
        islands = [(0.0, duration)]

    total_speech = sum(b - a for a, b in islands)
    weights = [_word_phonetic_weight(m.group()) for m in matches]
    total_weight = sum(weights) or 1.0

    # Map normalized weight progress [0..1] monotonically onto real speech islands
    cum_w = []
    acc = 0.0
    for w in weights:
        cum_w.append((acc / total_weight, (acc + w) / total_weight))
        acc += w

    def map_pos(frac: float) -> float:
        target = max(0.0, min(1.0, frac)) * total_speech
        pos = 0.0
        for a, b in islands:
            span = b - a
            if pos + span >= target - 1e-9:
                return round(min(duration, a + (target - pos)), 4)
            pos += span
        return round(islands[-1][1], 4)

    words = []
    prev_start = 0.0
    for m, (wf0, wf1) in zip(matches, cum_w):
        w_start = max(prev_start, map_pos(wf0))
        w_end = max(w_start, min(duration, map_pos(wf1)))
        prev_start = w_start
        words.append({
            'char': m.start(),
            'length': m.end() - m.start(),
            'start': round(w_start, 4),
            'end': round(w_end, 4),
            'text': m.group(),
        })

    data = {
        'provider': provider,
        'script_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'audio_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'duration': round(duration, 4),
        'words': words,
    }
    path.with_suffix('.words.json').write_text(json.dumps(data, indent=2), encoding='utf8')
    if not load_boundaries(path, text):
        raise ValueError('Incomplete acoustic narration alignment')
    return data
