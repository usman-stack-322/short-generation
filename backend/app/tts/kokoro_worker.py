"""Isolated, free CPU synthesis. No cloud fallback, downloads or emotion tags."""
import sys,json,time,re,hashlib,wave,difflib
from pathlib import Path

def main():
    data=json.loads(sys.stdin.read())
    runtime=Path(data['runtime']).resolve();sys.path.insert(0,str(runtime/'python'))
    import numpy as np
    import soundfile as sf
    from kokoro_onnx import Kokoro
    started=time.perf_counter()
    import onnxruntime as rt
    options=rt.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    options.add_session_config_entry('session.intra_op.allow_spinning','0')
    session=rt.InferenceSession(str(runtime/'models/kokoro-v1.0.int8.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    k=Kokoro.from_session(session,str(runtime/'models/voices-v1.0.bin'))
    loaded=time.perf_counter()-started
    if data.get('voice') not in {'bm_george','bf_emma','am_michael'}:
        raise ValueError('Select a reviewed generic local narrator')
    text=data['text'];lang='en-gb' if data['voice'].startswith('b') else 'en-us'
    controls={'voice':data['voice'],'speed':float(data.get('speed',1)), 'lang':lang,
              'sentence_pause':.22,'clause_pause':.10,'continuous':True}
    if not .94<=controls['speed']<=1.06:raise ValueError('Use restrained native model pace')
    def phonemize(value):
        result=k.tokenizer.phonemize(value.replace('PFA','P F A'),lang)
        for spelling,ipa in [('Thierry','tjˈɛɹi'),('Henry','ˈɒnɹi')]:
            result=result.replace(k.tokenizer.phonemize(spelling,lang),ipa)
        return result
    phonemes=phonemize(text)
    controls['is_phonemes']=True
    t=time.perf_counter();audio,rate,timings=k.create_timed(phonemes,**controls)
    elapsed=time.perf_counter()-t
    if not timings or not np.isfinite(audio).all() or np.max(np.abs(audio))<.001:
        raise ValueError('Complete non-silent audio and model durations are required')
    output=Path(data['output']);output.parent.mkdir(parents=True,exist_ok=True)
    sf.write(output,audio,rate,subtype='PCM_16')
    preliminary={'provider':'kokoro-onnx','runtime_version':'0.6.1','model':'Kokoro-82M v1.0 INT8',
                 'engine_controls':controls,'load_seconds':loaded,'generation_seconds':elapsed,
                 'audio_seconds':len(audio)/rate,'real_time_factor':elapsed/(len(audio)/rate),
                 'cost':'local CPU; no API calls','emotion_controls_supported':False,'direct_listening':False,
                 'pronunciation_handling':'PFA expanded to letters; Thierry/Henry English-IPA approximation; listening approval pending'}
    output.with_suffix('.generation.json').write_text(json.dumps(preliminary,indent=2))
    output.with_suffix('.phonemes.json').write_text(json.dumps([{'phoneme':t.phoneme,'start':t.start,'end':t.end} for t in timings],indent=2))
    if not data.get('alignment_required',True):
        print(json.dumps(preliminary),flush=True);return
    # Match word G2P spans to the actual full-script phonemes. Timings come from
    # model duration output, never from equal spacing or another narrator.
    actual=''.join(t.phoneme for t in timings)
    expected='';spans=[]
    for m in re.finditer(r'\S+',text):
        ph=phonemize(m.group())
        if expected:expected+=' '
        a=len(expected);expected+=ph;spans.append((m,a,len(expected)))
    matcher=difflib.SequenceMatcher(None,expected,actual,autojunk=False)
    mapping={a+i:b+i for a,b,n in matcher.get_matching_blocks() for i in range(n)}
    if matcher.ratio()<.82:raise ValueError('G2P spans do not align reliably to model phonemes')
    words=[]
    for m,a,b in spans:
        matches=[mapping[i] for i in range(a,b) if i in mapping and expected[i].isalnum()]
        coverage=len(matches)/max(1,sum(c.isalnum() for c in expected[a:b]))
        contextual=False
        if not matches or coverage<.6:
            # eSpeak reduces unstressed function words in a sentence (a -> ə).
            # Bound that changed phoneme span by its matched neighbours; do not
            # accept an unmatched name or number through this narrow case.
            if m.group().strip('.,?!').lower() not in {'a','an','the','of','to','and','or','for','in','was','his'}:
                raise ValueError('Low phoneme alignment coverage: '+m.group())
            left=max((i for i in mapping if i<a),default=None)
            right=min((i for i in mapping if i>=b),default=None)
            if left is None or right is None:raise ValueError('Unbounded contextual phoneme')
            matches=[i for i in range(mapping[left]+1,mapping[right]) if actual[i].isalnum()]
            if not matches or len(matches)>8:raise ValueError('Ambiguous contextual phoneme')
            contextual=True
        words.append({'char':m.start(),'length':len(m.group()),'text':m.group(),
                      'start':timings[min(matches)].start,'end':timings[max(matches)].end,
                      'phoneme_match_coverage':coverage,'contextual_function_word':contextual})
    duration=len(audio)/rate
    alignment={'provider':'Kokoro native phoneme durations; G2P word-span matching (not ASR)',
               'script_sha256':hashlib.sha256(text.encode()).hexdigest(),
               'audio_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
               'duration':duration,'words':words,'phoneme_alignment_ratio':matcher.ratio()}
    output.with_suffix('.words.json').write_text(json.dumps(alignment,indent=2))
    report={'provider':'kokoro-onnx','runtime_version':'0.6.1','model':'Kokoro-82M v1.0 INT8',
            'model_sha256':hashlib.sha256((runtime/'models/kokoro-v1.0.int8.onnx').read_bytes()).hexdigest(),
            'engine_controls':controls,'load_seconds':loaded,'generation_seconds':elapsed,
            'audio_seconds':duration,'real_time_factor':elapsed/duration,'cost':'local CPU; no API calls',
            'emotion_controls_supported':False,'direct_listening':False,'phoneme_alignment_ratio':matcher.ratio()}
    output.with_suffix('.generation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)

if __name__=='__main__':main()
