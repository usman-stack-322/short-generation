import json
import subprocess
import shutil
import wave
import struct
import math
import time
from app.core.config import settings
from app.video.subtitles import write_subtitles
from app.video.cover import create_cover
from app.video.fonts import resolve_font

def run(command, cwd=None):
    started=time.perf_counter()
    try:
        if cwd:
            (cwd/'render-command.json').write_text(json.dumps(command,indent=2),encoding='utf-8')
        result=subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True, timeout=600)
        if cwd: (cwd/'render.log').write_text(result.stderr or 'Render completed successfully.\n',encoding='utf-8')
        if cwd:(cwd/'render-metrics.json').write_text(json.dumps({'ffmpeg_wall_seconds':time.perf_counter()-started,'exit_code':0},indent=2),encoding='utf8')
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = exc.stderr[-1800:] if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        if cwd: (cwd/'render.log').write_text(detail or 'Render interrupted',encoding='utf-8')
        raise RuntimeError(f'FFmpeg rendering failed: {detail}') from exc

def audio_duration(path):
    result=subprocess.run([settings.ffprobe_path,'-v','error','-protocol_whitelist','file,pipe','-show_entries','format=duration',
                           '-of','json',str(path)],capture_output=True,text=True,check=True,timeout=20)
    return float(json.loads(result.stdout)['format']['duration'])


def validate_narration(path):
    """Reject cached silence too: retries must not bypass synthesis validation."""
    with wave.open(str(path),'rb') as audio:
        if audio.getsampwidth()!=2 or audio.getnframes()<100:
            raise ValueError('Narration must be complete non-silent 16-bit PCM audio')
        pcm=audio.readframes(audio.getnframes())
    samples=struct.unpack('<'+'h'*(len(pcm)//2),pcm)
    mean=sum(samples)/len(samples) if samples else 0
    if not samples or math.sqrt(sum((x-mean)**2 for x in samples)/len(samples))<8:
        raise ValueError('Narration is silent or inaudible; regenerate the voice before rendering')


def validate_music(path):
    result=subprocess.run([settings.ffprobe_path,'-v','error','-protocol_whitelist','file,pipe',
                           '-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=20)
    data=json.loads(result.stdout)
    if not data.get('streams') or any(stream.get('codec_type')!='audio' for stream in data['streams']):
        raise ValueError('A music file must contain only audio streams')
    allowed={'wav','mp3','ogg','mov,mp4,m4a,3gp,3g2,mj2'}
    if data['format'].get('format_name') not in allowed:
        raise ValueError('Unsupported audio container')
    return float(data['format']['duration'])

def tempo_filter(ratio):
    filters=[]
    while ratio > 2:
        filters.append('atempo=2'); ratio/=2
    while ratio < .5:
        filters.append('atempo=0.5'); ratio/=.5
    return ','.join(filters+[f'atempo={ratio:.6f}'])


VIDEO_EXTS = {'.mp4', '.mov', '.webm'}


def cover_image(path,job_dir):
    if path.suffix.lower() not in {'.mp4', '.mov', '.webm'}:return path
    job_dir.mkdir(parents=True,exist_ok=True)
    poster=job_dir/'clip-cover.jpg'
    subprocess.run([settings.ffmpeg_path,'-y','-v','error','-protocol_whitelist','file,pipe','-i',str(path),'-frames:v','1',str(poster)],capture_output=True,check=True,timeout=30)
    return poster

def render_video(job_id, topic, personality, script, audio_path, duration, output_root,
                 slides, cover_text='BEYOND THE HEADLINE', style='Documentary', music_path=None, scenes=None,
                 subtitle_preset=None, voice_speed=1, focal_positions=None, slide_kinds=None,
                 media_labels=None, revision=None, manual_timing=False, scene_plan=None):
    from app.video.photo_framing import compose_photo, motion_expression
    from app.video.scene_motion import validate_scene_plan, planned_motion
    scene_plan=validate_scene_plan(scene_plan,len(slides))
    from app.video.editorial import edit_timeline
    from app.video.alignment import load_boundaries
    from app.video.final_audio import finalize_narration
    for folder in ('audio','images','videos','thumbnails','subtitles'):
        (output_root/folder).mkdir(parents=True,exist_ok=True)
    job_dir=output_root/'videos'/job_id
    if revision is not None:
        job_dir=job_dir/f'revision-{int(revision)}'
    job_dir.mkdir(parents=True,exist_ok=True)
    if not slides or any(k in {'text_card','missing'} for k in (slide_kinds or [])):
        raise ValueError('Missing genuine scene media; standalone text cards are disabled. Upload or replace it.')
    validate_narration(audio_path)
    audio_path,timing,audio_report=finalize_narration(audio_path,script,job_dir)
    narration_duration=audio_duration(audio_path)
    if narration_duration>duration-.1:
        raise ValueError('Complete narration exceeds the configured duration limit; shorten the verified script before rendering')
    duration=min(duration,narration_duration+(.6 if scene_plan else .12))
    language=(subtitle_preset or {}).get('language','en-US')
    face=resolve_font(language,script)
    fonts_dir=job_dir/'fonts';fonts_dir.mkdir(exist_ok=True)
    shutil.copyfile(face.path,fonts_dir/face.path.name)
    ass=job_dir/'captions.ass';srt=output_root/'subtitles'/f'{job_id}.srt'
    beats,changes,segments=edit_timeline(duration,len(slides),scenes,timing,script,
        (subtitle_preset or {}).get('transitions',True),manual_timing,scene_plan)
    preset={**(subtitle_preset or {}),'documentary':True,'narration_timing':timing,'max_words':5,'font_size':64,
            'scene_boundaries':[b['start'] for b in beats[1:]]}
    if scene_plan:
        preset['illustration_intervals']=[(beat['start'],beat['end']) for beat,plan in zip(beats,scene_plan) if plan['visual_type']=='ai_illustration']
    write_subtitles(script,narration_duration,ass,srt,preset)
    timeline={'duration':duration,'scenes':beats,'transitions':changes,
              'timing_method':'narration sentence/clause boundaries' if timing and not manual_timing else 'saved scene timing'}
    (job_dir/'render-timeline.json').write_text(json.dumps(timeline,indent=2),encoding='utf8')
    (job_dir/'subtitle-timing.json').write_text(json.dumps({'output_duration':duration,
        'method':timing['provider'] if timing else 'estimated phrase timing',
        'source_audio_sha256':timing['audio_sha256'] if timing else None,
        'source_script_sha256':timing['script_sha256'] if timing else None,
        'word_events':len(timing['words']) if timing else 0,
        'source_duration':narration_duration,'rendered_narration_duration':narration_duration},indent=2),encoding='utf8')
    command=[settings.ffmpeg_path,'-y','-hide_banner','-loglevel','error','-filter_complex_threads','0']
    manifest=[]
    for i,(slide,segment) in enumerate(zip(slides,segments)):
        focal=focal_positions[i] if focal_positions and i<len(focal_positions) else (.5,.45)
        is_video = slide.suffix.lower() in {'.mp4', '.mov', '.webm'}; loop_args = []
        if is_video:
            if audio_duration(slide)+.05<segment:
                loop_args = ['-stream_loop', '-1']
            source=slide;info={'treatment':'same-video blurred background with fitted foreground','source':str(slide)}
        else:
            source=job_dir/f'composition-{i+1}.png'
            info=compose_photo(slide,source,focal,protect_top=not manual_timing,
                native_limit=bool(scene_plan),max_zoom=1+float(scene_plan[i]['motion'].get('amount',.06)) if scene_plan else 1.13)
        info.update(scene=i+1,visual_duration=segment)
        if scene_plan:info['scene_plan']=scene_plan[i]
        manifest.append(info)
        command+=['-protocol_whitelist','file,pipe']+loop_args+(['-an','-sn'] if is_video else ['-framerate','30'])+['-t',f'{segment:.6f}','-i',str(source)]
    audio_index=len(slides);command+=['-i',str(audio_path)]
    if music_path:command+=['-stream_loop','-1','-i',str(music_path)]
    graph=[]
    for i,segment in enumerate(segments):
        focal=focal_positions[i] if focal_positions and i<len(focal_positions) else (.5,.45)
        focal=manifest[i].get('focal',focal)
        if slides[i].suffix.lower() in VIDEO_EXTS:
            graph.append(f'[{i}:v]fps=30,split=2[bg{i}][fg{i}]')
            graph.append(f'[bg{i}]scale=270:480:force_original_aspect_ratio=increase:flags=fast_bilinear,crop=270:480,boxblur=8:2,eq=brightness=-0.16:saturation=0.65,scale=1080:1920:flags=bilinear[b{i}]')
            graph.append(f'[fg{i}]scale=1040:1480:force_original_aspect_ratio=decrease:flags=bicubic[f{i}]')
            graph.append(f'[b{i}][f{i}]overlay=(W-w)/2:(H-h)/2,trim=duration={segment:.6f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[m{i}]')
            manifest[i]['movement']='original clip speed; clip audio excluded'
        else:
            frames=max(1,math.ceil(segment*30)+1)
            z,x,y,movement=planned_motion(frames,focal,scene_plan[i]) if scene_plan else motion_expression(i,frames,focal)
            # Decode each still once; zoompan generates its timed frame sequence.
            graph.append(f"[{i}:v]zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s=1080x1920:fps=30,trim=duration={segment:.6f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[m{i}]")
            manifest[i]['movement']=movement
            manifest[i]['still_decode']='one source frame expanded by zoompan'
        # Archival context and attribution stay in source/description records.
        # No corner labels, scrim, caption panel, pills or boxes are rendered.
        graph.append(f'[m{i}]null[v{i}]')
    previous='v0'
    for i,change in enumerate(changes,1):
        label=f'x{i}'
        if change['type']=='cut':
            graph.append(f'[{previous}][v{i}]concat=n=2:v=1:a=0[cut{i}]')
            graph.append(f'[cut{i}]settb=1/30,fps=30[{label}]')
        else:
            xfade_name = {
                'dissolve': 'fade',
                'crossfade': 'fade',
                'fade': 'fade',
                'slide': 'slideleft',
                'smoothleft': 'smoothleft',
                'wipe': 'wipeleft',
                'flash': 'fadewhite',
                'zoomin': 'zoomin',
                'radial': 'radial',
            }.get(change.get('transition', 'fade'), 'fade')
            graph.append(f"[{previous}][v{i}]xfade=transition={xfade_name}:duration={change['duration']:.6f}:offset={change['offset']:.6f}[{label}]")
        previous=label
    graph.append(f'[{previous}]ass=captions.ass:fontsdir=fonts:shaping=complex,format=yuv420p[outv]')
    graph.append(f'[{audio_index}:a]alimiter=limit=0.84:level=0:latency=1,aresample=48000,apad,atrim=duration={duration}[speech]')
    audio_label='speech'
    if music_path:
        graph+=['[speech]asplit=2[narration][sidechain]',f'[{audio_index+1}:a]volume=0.1,atrim=duration={duration}[music]',
                '[music][sidechain]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=250[ducked]',
                '[narration][ducked]amix=inputs=2:duration=first:normalize=0[mix]']
        audio_label='mix'
    (job_dir/'media-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    # Publish bytes atomically only after FFmpeg succeeds. Versioned paths avoid stale cache identity.
    output=job_dir/'short.mp4';temporary=job_dir/'rendering.mp4'
    command+=['-filter_complex',';'.join(graph),'-map','[outv]','-map',f'[{audio_label}]','-t',str(duration),
              '-c:v','libx264','-threads','0','-preset','veryfast','-crf','20','-r','30',
              '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',
              '-c:a','aac','-ar','48000','-b:a','160k','-movflags','+faststart',str(temporary)]
    run(command,cwd=job_dir)
    if temporary.is_file():temporary.replace(output)
    if output.is_file():
        subprocess.run([settings.ffmpeg_path,'-y','-v','error','-ss','0.05','-i',str(output),
                        '-frames:v','1',str(job_dir/'poster.jpg')],check=True,capture_output=True,timeout=30)
    cover=output_root/'thumbnails'/f'{job_id}.png'
    if (job_dir/'poster.jpg').is_file():
        from PIL import Image
        Image.open(job_dir/'poster.jpg').save(cover)
    else:
        cover=create_cover(cover_image(slides[0],job_dir),cover_text,cover,language=language)
    return output,cover,slides
