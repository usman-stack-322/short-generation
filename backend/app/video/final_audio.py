"""Conservative silence editing and measured two-pass normalization.

Speech samples are never time-stretched. Every removed interval is recorded and
native text timing is mapped onto the edited PCM before captions are generated.
"""
import array
import hashlib
import json
import math
import re
import subprocess
import wave
from pathlib import Path
from app.core.config import settings
from app.video.alignment import load_boundaries


def silence_edits(samples, rate, channels, timing=None):
    window=max(1,round(rate*.02))*channels
    duration=len(samples)/(rate*channels)
    threshold=32768*10**(-42/20)
    intervals=[];start=None
    for offset in range(0,len(samples),window):
        chunk=samples[offset:offset+window]
        quiet=math.sqrt(sum(v*v for v in chunk)/max(1,len(chunk)))<threshold
        at=offset/(rate*channels)
        if quiet and start is None:start=at
        if not quiet and start is not None:
            if at-start>=.3:intervals.append((start,at))
            start=None
    if start is not None and duration-start>=.3:intervals.append((start,duration))
    cuts=[]
    for start,end in intervals:
        if start==0:
            begin,finish,kind=0,max(0,end-.06),'leading silence'
        elif end>=duration-.001:
            begin,finish,kind=min(end,start+.14),end,'trailing silence'
        elif timing and end-start>.58:
            begin,finish,kind=start+.19,end-.19,'long quiet pause'
        else:continue
        # Word events protect quiet/unvoiced syllables from being removed.
        if timing and any(begin-.025<=w['start']<=finish+.025 or
                          w.get('end') is not None and w['start']<finish and w['end']>begin
                          for w in timing['words']):continue
        if finish-begin>.02:cuts.append({'start':begin,'end':finish,'reason':kind})
    return intervals,cuts


def remap_time(at,cuts):
    return at-sum(max(0,min(at,c['end'])-c['start']) for c in cuts if at>c['start'])


def parse_loudness(stderr):
    matches=re.findall(r'\{\s*"input_i".*?\}',stderr,re.S)
    if not matches:raise ValueError('FFmpeg did not return measured narration loudness')
    data=json.loads(matches[-1])
    if any(not math.isfinite(float(data[k])) for k in ('input_i','input_tp','input_lra','input_thresh','target_offset')):
        raise ValueError('Narration normalization failed: nonfinite audio measurements')
    return data


def finalize_narration(source, script, folder):
    source=Path(source);folder=Path(folder)
    timing=load_boundaries(source,script)
    if source.with_suffix('.words.json').is_file() and not timing:
        raise ValueError('Narration timing is stale or incomplete; regenerate narration')
    with wave.open(str(source),'rb') as wav:
        params=wav.getparams();pcm=wav.readframes(wav.getnframes())
    if params.sampwidth!=2:raise ValueError('Narration requires 16-bit PCM')
    samples=array.array('h');samples.frombytes(pcm)
    intervals,cuts=silence_edits(samples,params.framerate,params.nchannels,timing)
    edited=array.array('h');cursor=0
    for cut in cuts:
        begin=round(cut['start']*params.framerate)*params.nchannels
        end=round(cut['end']*params.framerate)*params.nchannels
        edited.extend(samples[cursor:begin]);cursor=end
    edited.extend(samples[cursor:])
    trimmed=folder/'narration-trimmed.wav'
    with wave.open(str(trimmed),'wb') as wav:
        wav.setparams(params);wav.writeframes(edited.tobytes())
    target='I=-15:TP=-1.5:LRA=9'
    # Reduce isolated high peaks before measuring; gain alone cannot meet the
    # loudness target when the source already peaks close to full scale.
    compressor='acompressor=threshold=0.08:ratio=4:attack=5:release=100:knee=2.5:makeup=1'
    first=subprocess.run([settings.ffmpeg_path,'-hide_banner','-i',str(trimmed),'-af',
        compressor+',loudnorm='+target+':print_format=json','-f','null','-'],capture_output=True,text=True,check=True,timeout=60)
    measured=parse_loudness(first.stderr)
    filters=(compressor+',loudnorm='+target+f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        +f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        +f":offset={measured['target_offset']}:linear=true:print_format=json,"
        +'alimiter=limit=0.841395:level=0:latency=1,aresample=48000')
    output=folder/'narration.wav'
    second=subprocess.run([settings.ffmpeg_path,'-y','-hide_banner','-i',str(trimmed),'-af',filters,
        '-c:a','pcm_s16le',str(output)],capture_output=True,text=True,check=True,timeout=60)
    normalized=parse_loudness(second.stderr)
    # Measure the delivered PCM: loudnorm can miss its target on peaky SAPI speech.
    # Correct gain against that measurement, preserving samples in time and peak headroom.
    delivery_measurements=[]
    for attempt in range(3):
        probe=subprocess.run([settings.ffmpeg_path,'-hide_banner','-i',str(output),'-af',
            'loudnorm='+target+':print_format=json','-f','null','-'],capture_output=True,text=True,check=True,timeout=60)
        actual=parse_loudness(probe.stderr);delivery_measurements.append(actual)
        correction=-15-float(actual['input_i'])
        if abs(correction)<=.35 or attempt==2:break
        adjusted=folder/'narration-level-adjusted.wav'
        subprocess.run([settings.ffmpeg_path,'-y','-hide_banner','-i',str(output),'-af',
            f'volume={max(-4,min(4,correction)):.3f}dB,alimiter=limit=0.841395:level=0:latency=1',
            '-c:a','pcm_s16le',str(adjusted)],capture_output=True,text=True,check=True,timeout=60)
        adjusted.replace(output)
    with wave.open(str(output),'rb') as wav:duration=wav.getnframes()/wav.getframerate()
    expected=len(edited)/(params.framerate*params.nchannels)
    if abs(duration-expected)>.03:raise ValueError('Audio processing changed speech duration unexpectedly')
    if timing:
        timing={**timing,'provider':timing['provider']+'; silence mapped and two-pass normalized',
                'duration':duration,'audio_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                'words':[{**w,'start':remap_time(w['start'],cuts),
                    **({'end':remap_time(w['end'],cuts)} if 'end' in w else {})} for w in timing['words']]}
        output.with_suffix('.words.json').write_text(json.dumps(timing,indent=2),encoding='utf8')
        if not load_boundaries(output,script):raise ValueError('Edited narration lost complete caption timing')
    report={'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_duration':len(samples)/(params.framerate*params.nchannels),'detected_quiet_intervals':intervals,
        'removed_intervals':cuts,'removed_seconds':sum(c['end']-c['start'] for c in cuts),
        'finished_audio_duration':duration,'speech_speed_changed':False,'target_LUFS':-15,'target_true_peak_dBTP':-1.5,
        'peak_management':compressor,
        'first_pass':measured,'second_pass':normalized,'delivered_pcm_measurements':delivery_measurements,'direct_listening':False}
    (folder/'audio-processing.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return output,timing,report
