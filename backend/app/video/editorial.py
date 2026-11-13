"""Map picture changes to complete narration sentences and clauses."""
import re


def narration_beats(script, timing, count, duration):
    spans = [(m.start(), m.end()) for m in re.finditer(r'\S[^.!?]*[.!?]*(?:\s+|$)', script)]
    if not spans or not timing or count < 1:
        return None
    while len(spans) < count:
        candidate = max(range(len(spans)), key=lambda i: len(script[spans[i][0]:spans[i][1]].split()))
        a, b = spans[candidate]
        words = list(re.finditer(r'\S+', script[a:b]))
        if len(words) < 4:
            return None
        commas = [a+m.end() for m in re.finditer(r',\s+', script[a:b])
                  if a+words[1].end() < a+m.end() < a+words[-2].start()]
        split = min(commas, key=lambda c: abs(c-(a+b)/2)) if commas else a+words[len(words)//2].start()
        spans[candidate:candidate+1] = [(a, split), (split, b)]
    while len(spans) > count:
        i = min(range(len(spans)-1), key=lambda i: spans[i+1][1]-spans[i][0])
        spans[i:i+2] = [(spans[i][0], spans[i+1][1])]
    starts = [0.0]
    for a, b in spans[1:]:
        first = next((w for w in timing['words'] if w['char']+w['length'] > a), None)
        if not first:
            return None
        starts.append(float(first['start']))
    if any(b-a < .6 for a, b in zip(starts, starts[1:]+[duration])):
        return None
    return [{'start': starts[i], 'end': starts[i+1] if i+1<count else duration,
             'narration': script[a:b].strip()} for i, (a, b) in enumerate(spans)]


def edit_timeline(duration, count, scenes=None, timing=None, script='', transitions=True, manual=False, scene_plan=None):
    beats = None
    if scene_plan and timing:
        cursor=0;starts=[]
        for plan in scene_plan:
            text=plan['text'].strip();at=script.find(text,cursor)
            if at<0 or script[cursor:at].strip():raise ValueError('Scene text must cover the unchanged script in order')
            first=next((w for w in timing['words'] if w['char']+w['length']>at),None)
            if first is None:raise ValueError('Scene lacks aligned speech')
            starts.append(float(first['start']));cursor=at+len(text)
        if script[cursor:].strip():raise ValueError('Scene plan omits script ending')
        starts[0]=0.
        beats=[{'start':a,'end':b,'narration':plan['text']} for a,b,plan in zip(starts,starts[1:]+[duration],scene_plan)]
        if any(b['end']-b['start']<.6 for b in beats):raise ValueError('Narrated scene is too short')
    elif timing and not manual:
        beats = narration_beats(script, timing, count, duration)
    if beats is None:
        if scenes and len(scenes)==count and scenes[-1].end_time>0:
            factor = duration/scenes[-1].end_time
            beats = [{'start': s.start_time*factor, 'end': s.end_time*factor} for s in scenes]
        else:
            beats = [{'start': i*duration/count, 'end': (i+1)*duration/count} for i in range(count)]
    changes = []
    for i, beat in enumerate(beats[1:], 1):
        t_style = scene_plan[i].get('transition_in', 'dissolve') if scene_plan else ('dissolve' if i % 2 == 1 else 'cut')
        dissolve = bool(transitions and t_style in {'dissolve', 'crossfade', 'slide', 'wipe', 'flash', 'zoomin', 'smoothleft', 'radial'})
        overlap = .45 if dissolve else 0.0
        overlap = min(overlap, (beat['end']-beat['start'])/3,
                      (beats[i-1]['end']-beats[i-1]['start'])/3)
        changes.append({'at': beat['start'], 'offset': max(0, beat['start']-overlap/2),
                        'duration': overlap, 'type': 'dissolve' if dissolve else 'cut', 'transition': t_style})
    visual_starts = [0]+[c['offset'] for c in changes]
    segments = [(changes[i]['offset']+changes[i]['duration'] if i<len(changes) else duration)-start
                for i, start in enumerate(visual_starts)]
    return beats, changes, segments
