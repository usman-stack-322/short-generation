"""Isolated, free CPU synthesis. No cloud fallback, downloads or emotion tags."""
import sys,json,os,time,re,hashlib,difflib
from pathlib import Path

FP32_BYTES=325505369
FP32_SHA256='beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a'
INT8_SHA256='ae315a79b623f244700e4afb9246c46a26066782e049ba174bf3ba433970ee9c'

def resolve_model(runtime:Path):
    models=runtime/'models'
    fp32=models/'kokoro-v1.0.onnx'
    fp32_marker=models/'verified-fp32.json'
    if fp32.is_file() and fp32.stat().st_size==FP32_BYTES:
        if fp32_marker.is_file():
            return fp32,'Kokoro-82M v1.0 FP32',FP32_SHA256
        h=hashlib.sha256()
        with fp32.open('rb') as f:
            for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
        digest=h.hexdigest()
        if digest==FP32_SHA256:
            fp32_marker.write_text(json.dumps({'bytes':FP32_BYTES,'digest':digest},indent=2))
            return fp32,'Kokoro-82M v1.0 FP32',digest
    return models/'kokoro-v1.0.int8.onnx','Kokoro-82M v1.0 INT8',INT8_SHA256

def load_kokoro(runtime:Path):
    sys.path.insert(0,str(runtime/'python'))
    import onnxruntime as rt
    from kokoro_onnx import Kokoro
    model_path,model_label,model_sha=resolve_model(runtime)
    started=time.perf_counter()
    options=rt.SessionOptions()
    options.intra_op_num_threads=max(4,min(8,int(os.environ.get('KOKORO_THREADS',os.cpu_count() or 4))))
    options.inter_op_num_threads=1
    options.execution_mode=rt.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level=rt.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.add_session_config_entry('session.intra_op.allow_spinning','1')
    session=rt.InferenceSession(str(model_path),sess_options=options,providers=['CPUExecutionProvider'])
    k=Kokoro.from_session(session,str(runtime/'models/voices-v1.0.bin'))
    return k,model_path,model_label,model_sha,time.perf_counter()-started

def synthesize_one(k,model_label,model_sha,loaded,data):
    import numpy as np
    import soundfile as sf
    voice=data.get('voice','')
    if voice not in k.voices or not voice.startswith(('af_','am_','bf_','bm_')):
        raise ValueError('Select a reviewed generic local narrator')
    text=data['text'];lang='en-gb' if voice.startswith('b') else 'en-us'
    # continuous=False splits cleanly at punctuation without 1.4x-1.8x sliding-window overlap while preserving phoneme timings.
    controls={'voice':voice,'speed':float(data.get('speed',1)), 'lang':lang,
              'sentence_pause':.22,'clause_pause':.10,'continuous':False}
    if not .94<=controls['speed']<=1.06:raise ValueError('Use restrained native model pace')
    ph_cache={}
    def phonemize(value):
        cached=ph_cache.get(value)
        if cached is not None:return cached
        result=k.tokenizer.phonemize(value.replace('PFA','P F A'),lang)
        for spelling,ipa in [('Thierry','tjˈɛɹi'),('Henry','ˈɒnɹi')]:
            result=result.replace(k.tokenizer.phonemize(spelling,lang),ipa)
        ph_cache[value]=result
        return result
    phonemes=phonemize(text)
    controls['is_phonemes']=True
    t=time.perf_counter();audio,rate,timings=k.create_timed(phonemes,**controls)
    elapsed=time.perf_counter()-t
    if not timings or not np.isfinite(audio).all() or np.max(np.abs(audio))<.001:
        raise ValueError('Complete non-silent audio and model durations are required')
    output=Path(data['output']);output.parent.mkdir(parents=True,exist_ok=True)
    sf.write(output,audio,rate,subtype='PCM_16')
    duration=len(audio)/rate
    preliminary={'provider':'kokoro-onnx','runtime_version':'0.6.1','model':model_label,
                 'engine_controls':controls,'load_seconds':loaded,'generation_seconds':elapsed,
                 'audio_seconds':duration,'real_time_factor':elapsed/duration,
                 'cost':'local CPU; no API calls','emotion_controls_supported':False,'direct_listening':False,
                 'pronunciation_handling':'PFA expanded to letters; Thierry/Henry English-IPA approximation; listening approval pending'}
    output.with_suffix('.generation.json').write_text(json.dumps(preliminary,indent=2))
    output.with_suffix('.phonemes.json').write_text(json.dumps([{'phoneme':t.phoneme,'start':t.start,'end':t.end} for t in timings],indent=2))
    if not data.get('alignment_required',True):
        return preliminary
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
    alignment={'provider':'Kokoro native phoneme durations; G2P word-span matching (not ASR)',
               'script_sha256':hashlib.sha256(text.encode()).hexdigest(),
               'audio_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
               'duration':duration,'words':words,'phoneme_alignment_ratio':matcher.ratio()}
    output.with_suffix('.words.json').write_text(json.dumps(alignment,indent=2))
    report={'provider':'kokoro-onnx','runtime_version':'0.6.1','model':model_label,
            'model_sha256':model_sha,
            'engine_controls':controls,'load_seconds':loaded,'generation_seconds':elapsed,
            'audio_seconds':duration,'real_time_factor':elapsed/duration,'cost':'local CPU; no API calls',
            'emotion_controls_supported':False,'direct_listening':False,'phoneme_alignment_ratio':matcher.ratio()}
    output.with_suffix('.generation.json').write_text(json.dumps(report,indent=2))
    return report

def serve(runtime:Path):
    k,model_path,model_label,model_sha,loaded=load_kokoro(runtime)
    print(json.dumps({'ready':True,'model':model_label,'load_seconds':loaded}),flush=True)
    for raw in sys.stdin:
        line=raw.strip()
        if not line:continue
        try:
            data=json.loads(line)
            best_path,_,_=resolve_model(runtime)
            if best_path!=model_path:
                k,model_path,model_label,model_sha,loaded=load_kokoro(runtime)
            else:
                loaded_for_req=0.0
            report=synthesize_one(k,model_label,model_sha,loaded if best_path!=model_path else loaded_for_req,data)
            print(json.dumps({'ok':True,'report':report}),flush=True)
        except Exception as exc:
            print(json.dumps({'ok':False,'error':str(exc)}),flush=True)

def main():
    if len(sys.argv)>=3 and sys.argv[1]=='--serve':
        serve(Path(sys.argv[2]).resolve());return
    data=json.loads(sys.stdin.read())
    runtime=Path(data['runtime']).resolve()
    k,_,model_label,model_sha,loaded=load_kokoro(runtime)
    report=synthesize_one(k,model_label,model_sha,loaded,data)
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
