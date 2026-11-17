import array
import gc
import json
import os
import subprocess
import shutil
import sys
import wave
import math
import time
from pathlib import Path
from app.core.config import settings
from app.core.languages import language_info
from app.video.subtitles import CAPTION_STYLES, write_subtitles
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
        if isinstance(exc, subprocess.CalledProcessError):
            detail = (exc.stderr or '').strip()[-1800:] or f'FFmpeg exited with code {exc.returncode}'
        else:
            detail = str(exc)
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
    samples=array.array('h')
    samples.frombytes(pcm[:len(pcm)-(len(pcm)%2)])
    del pcm
    if sys.byteorder!='little':
        samples.byteswap()
    n=len(samples)
    if not n:
        raise ValueError('Narration is silent or inaudible; regenerate the voice before rendering')
    mean=sum(samples)/n
    if math.sqrt(sum((x-mean)**2 for x in samples)/n)<8:
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


VIDEO_EXTS = {'.mp4', '.mov', '.webm', '.mkv', '.m4v'}


def _is_constrained_env() -> bool:
    """Detect low-memory Docker containers (e.g. Render 512 MB free tier) to prevent FFmpeg OOM kills."""
    if os.environ.get('RENDER_LOW_MEMORY', '').strip() == '1':
        return True
    if os.environ.get('RENDER', '').strip().lower() == 'true':
        return True
    for cgroup_file in ('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory/memory.limit_in_bytes'):
        try:
            raw = Path(cgroup_file).read_text(encoding='utf8').strip()
            if raw.isdigit() and int(raw) <= 1_600_000_000:
                return True
        except OSError:
            continue
    return False


def _video_clip_duration(path: Path) -> float:
    """Inspect a local/vault clip with ffprobe, ensuring a video stream exists and returning safe playable duration."""
    result = subprocess.run(
        [
            settings.ffprobe_path,
            '-v', 'error',
            '-protocol_whitelist', 'file,pipe',
            '-show_streams',
            '-show_format',
            '-of', 'json',
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    info = json.loads(result.stdout or '{}')
    v_streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'video']
    if not v_streams:
        raise ValueError(f'Clip {path.name} has no readable video stream; replace it with another clip.')
    v_stream = v_streams[0]
    candidates: list[float] = []
    start_time = max(0.0, float(v_stream.get('start_time') or 0.0))
    for raw in (v_stream.get('duration'), (info.get('format') or {}).get('duration')):
        try:
            val = float(raw) - start_time
            if math.isfinite(val) and val > 0:
                candidates.append(val)
        except (TypeError, ValueError):
            pass
    if not candidates and v_stream.get('nb_frames') and v_stream.get('avg_frame_rate'):
        try:
            num, den = str(v_stream['avg_frame_rate']).split('/')
            fps = float(num) / max(1.0, float(den))
            val = float(v_stream['nb_frames']) / max(1.0, fps)
            if math.isfinite(val) and val > 0:
                candidates.append(val)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    return min(candidates) if candidates else 0.0


def _prepare_constrained_clip(src: Path, dest: Path, segment: float, clip_dur: float, cwd: Path | None = None):
    """Normalize a single video clip sequentially to 1080x1920 30fps so Render 512MB RAM never decodes all clips at once."""
    loop_args = ['-stream_loop', '-1'] if (clip_dur <= 0 or clip_dur <= segment + 0.5) else []
    fg = (
        f'[0:v]setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p,split=2[bg][fg];'
        f'[bg]scale=270:480:force_original_aspect_ratio=increase:flags=fast_bilinear,'
        f'crop=270:480,boxblur=8:2,eq=brightness=-0.16:saturation=0.65,scale=1080:1920:flags=bilinear[b];'
        f'[fg]scale=1040:1480:force_original_aspect_ratio=decrease:flags=bicubic[f];'
        f'[b][f]overlay=(W-w)/2:(H-h)/2,tpad=stop_mode=clone:stop_duration=1,'
        f'trim=duration={segment:.6f},setpts=PTS-STARTPTS,settb=1/30,fps=30,setsar=1,format=yuv420p[outv]'
    )
    cmd = [
        settings.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
        '-filter_complex_threads', '1',
        '-protocol_whitelist', 'file,pipe',
        '-threads', '1',
        *loop_args, '-an', '-sn', '-i', str(src),
        '-t', f'{segment:.6f}',
        '-filter_complex', fg, '-map', '[outv]',
        '-c:v', 'libx264', '-threads', '2', '-preset', 'ultrafast', '-crf', '18', '-r', '30',
        str(dest),
    ]
    run(cmd, cwd=cwd)


def _prepare_constrained_photo(
    src: Path,
    dest: Path,
    segment: float,
    frames: int,
    z: str,
    x: str,
    y: str,
    cwd: Path | None = None,
):
    """Pre-render a single photo's zoompan motion sequentially so 512MB containers never stack zoompan filters."""
    vf = (
        f"[0:v]zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s=1080x1920:fps=30,"
        f"trim=duration={segment:.6f},setpts=PTS-STARTPTS,settb=1/30,fps=30,setsar=1,format=yuv420p[outv]"
    )
    cmd = [
        settings.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
        '-filter_complex_threads', '1',
        '-protocol_whitelist', 'file,pipe',
        '-threads', '1',
        '-framerate', '30', '-t', f'{segment:.6f}', '-i', str(src),
        '-filter_complex', vf, '-map', '[outv]',
        '-c:v', 'libx264', '-threads', '2', '-preset', 'ultrafast', '-crf', '18', '-r', '30',
        str(dest),
    ]
    run(cmd, cwd=cwd)


def _run_low_memory_concat_fallback(
    prepared_sources: list[Path],
    audio_path: Path,
    music_path: Path | None,
    duration: float,
    temporary: Path,
    cwd: Path,
):
    """Ultra-low-memory concat demuxer fallback (1 decoder at a time) if multi-input xfade OOMs on 512MB tier."""
    concat_file = cwd / 'concat.txt'
    lines = []
    for src in prepared_sources:
        rel = src.relative_to(cwd).as_posix() if src.is_relative_to(cwd) else str(src).replace('\\', '/')
        escaped = rel.replace("'", "'\\''")
        lines.append(f"file '{escaped}'\n")
    concat_file.write_text(''.join(lines), encoding='utf8')
    graph = [
        '[0:v]setpts=PTS-STARTPTS,settb=1/30,fps=30,setsar=1,'
        'tpad=stop_mode=clone:stop_duration=1,'
        'ass=captions.ass:fontsdir=fonts:shaping=complex,format=yuv420p[outv]',
        f'[1:a]alimiter=limit=0.84:level=0:latency=1,aresample=48000,apad,atrim=duration={duration}[speech]',
    ]
    audio_label = 'speech'
    if music_path:
        graph += [
            '[speech]asplit=2[narration][sidechain]',
            f'[2:a]volume=0.1,atrim=duration={duration}[music]',
            '[music][sidechain]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=250[ducked]',
            '[narration][ducked]amix=inputs=2:duration=first:normalize=0[mix]',
        ]
        audio_label = 'mix'
    cmd = [
        settings.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
        '-filter_complex_threads', '1',
        '-protocol_whitelist', 'file,pipe',
        '-threads', '1',
        '-f', 'concat', '-safe', '0', '-i', str(concat_file),
        '-i', str(audio_path),
        *(['-stream_loop', '-1', '-i', str(music_path)] if music_path else []),
        '-filter_complex', ';'.join(graph),
        '-map', '[outv]', '-map', f'[{audio_label}]',
        '-t', str(duration),
        '-c:v', 'libx264', '-threads', '1', '-preset', 'ultrafast', '-crf', '21', '-r', '30',
        '-x264-params', 'rc-lookahead=0:sync-lookahead=0:ref=1:bframes=0',
        '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
        '-c:a', 'aac', '-ar', '48000', '-b:a', '128k', '-movflags', '+faststart',
        str(temporary),
    ]
    run(cmd, cwd=cwd)


def cover_image(path,job_dir):
    if path.suffix.lower() not in VIDEO_EXTS:return path
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
    lang_cfg=language_info(language)
    face=resolve_font(language,script)
    fonts_dir=job_dir/'fonts';fonts_dir.mkdir(exist_ok=True)
    shutil.copyfile(face.path,fonts_dir/face.path.name)
    pref_fonts = CAPTION_STYLES.get((subtitle_preset or {}).get('caption_style') or '', {}).get('preferred_fonts', ()) if not lang_cfg.rtl else ()
    if pref_fonts:
        try:
            style_face = resolve_font(language, script, preferred_fonts=pref_fonts)
            if style_face.path.is_file() and not (fonts_dir / style_face.path.name).exists():
                shutil.copyfile(style_face.path, fonts_dir / style_face.path.name)
        except Exception:
            pass
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
    constrained = _is_constrained_env()
    filter_threads = '1' if constrained else '0'
    enc_threads = '2' if constrained else '0'
    command=[settings.ffmpeg_path,'-y','-hide_banner','-loglevel','error','-filter_complex_threads',filter_threads]
    manifest=[]
    prepared_clips: set[int] = set()
    prepared_sources: list[Path] = []
    for i,(slide,segment) in enumerate(zip(slides,segments)):
        focal=focal_positions[i] if focal_positions and i<len(focal_positions) else (.5,.45)
        is_video = slide.suffix.lower() in VIDEO_EXTS; loop_args = []
        if is_video:
            clip_dur = _video_clip_duration(slide)
            if constrained:
                prep_path = job_dir / f'prepared-clip-{i+1}.mp4'
                _prepare_constrained_clip(slide, prep_path, segment, clip_dur, cwd=job_dir)
                source = prep_path
                prepared_clips.add(i)
                prepared_sources.append(prep_path)
            else:
                if clip_dur <= 0 or clip_dur <= segment + 0.5:
                    loop_args = ['-stream_loop', '-1']
                source = slide
            info={'treatment':'same-video blurred background with fitted foreground','source':str(slide)}
        else:
            comp_path=job_dir/f'composition-{i+1}.png'
            info=compose_photo(slide,comp_path,focal,protect_top=not manual_timing,
                native_limit=bool(scene_plan),max_zoom=1+float(scene_plan[i]['motion'].get('amount',.06)) if scene_plan else 1.13,
                canvas_size=(1080,1920) if constrained else (2160,3840))
            if constrained:
                photo_focal = info.get('focal', focal)
                frames = max(1, math.ceil(segment * 30) + 1)
                z, x, y, movement = planned_motion(frames, photo_focal, scene_plan[i]) if scene_plan else motion_expression(i, frames, photo_focal)
                prep_path = job_dir / f'prepared-photo-{i+1}.mp4'
                _prepare_constrained_photo(comp_path, prep_path, segment, frames, z, x, y, cwd=job_dir)
                comp_path.unlink(missing_ok=True)
                gc.collect()
                source = prep_path
                prepared_clips.add(i)
                prepared_sources.append(prep_path)
                info['movement'] = movement
                info['still_decode'] = 'one source frame expanded by zoompan'
            else:
                source = comp_path
        info.update(scene=i+1,visual_duration=segment)
        if scene_plan:info['scene_plan']=scene_plan[i]
        manifest.append(info)
        is_video_input = is_video or (i in prepared_clips)
        in_limit = [] if is_video_input else ['-t', f'{segment:.6f}']
        command+=['-protocol_whitelist','file,pipe']+loop_args+(['-an','-sn'] if is_video_input else ['-framerate','30'])+in_limit+['-i',str(source)]
    audio_index=len(slides);command+=['-i',str(audio_path)]
    if music_path:command+=['-stream_loop','-1','-i',str(music_path)]
    graph=[]
    for i,segment in enumerate(segments):
        focal=focal_positions[i] if focal_positions and i<len(focal_positions) else (.5,.45)
        focal=manifest[i].get('focal',focal)
        if i in prepared_clips:
            graph.append(f'[{i}:v]trim=duration={segment:.6f},setpts=PTS-STARTPTS,settb=1/30,fps=30,setsar=1,format=yuv420p[m{i}]')
            manifest[i].setdefault('movement', 'original clip speed; clip audio excluded')
        elif slides[i].suffix.lower() in VIDEO_EXTS:
            graph.append(f'[{i}:v]setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p,split=2[bg{i}][fg{i}]')
            graph.append(f'[bg{i}]scale=270:480:force_original_aspect_ratio=increase:flags=fast_bilinear,crop=270:480,boxblur=8:2,eq=brightness=-0.16:saturation=0.65,scale=1080:1920:flags=bilinear[b{i}]')
            graph.append(f'[fg{i}]scale=1040:1480:force_original_aspect_ratio=decrease:flags=bicubic[f{i}]')
            graph.append(f'[b{i}][f{i}]overlay=(W-w)/2:(H-h)/2,tpad=stop_mode=clone:stop_duration=1,trim=duration={segment:.6f},setpts=PTS-STARTPTS,settb=1/30,fps=30,setsar=1,format=yuv420p[m{i}]')
            manifest[i]['movement']='original clip speed; clip audio excluded'
        else:
            frames=max(1,math.ceil(segment*30)+1)
            z,x,y,movement=planned_motion(frames,focal,scene_plan[i]) if scene_plan else motion_expression(i,frames,focal)
            # Decode each still once; zoompan generates its timed frame sequence.
            graph.append(f"[{i}:v]zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s=1080x1920:fps=30,trim=duration={segment:.6f},setpts=PTS-STARTPTS,settb=1/30,fps=30,setsar=1,format=yuv420p[m{i}]")
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
            graph.append(f"[{previous}][v{i}]xfade=transition={xfade_name}:duration={change['duration']:.6f}:offset={change['offset']:.6f},settb=1/30[{label}]")
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
    x264_mem_args = ['-x264-params', 'rc-lookahead=10:sync-lookahead=0'] if constrained else []
    command+=['-filter_complex',';'.join(graph),'-map','[outv]','-map',f'[{audio_label}]','-t',str(duration),
              '-c:v','libx264','-threads',enc_threads,'-preset','veryfast','-crf','20','-r','30',
              *x264_mem_args,
              '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',
              '-c:a','aac','-ar','48000','-b:a','160k','-movflags','+faststart',str(temporary)]
    if constrained:
        gc.collect()
    try:
        run(command,cwd=job_dir)
    except RuntimeError:
        if constrained and len(prepared_sources) == len(slides) and all(p.is_file() for p in prepared_sources):
            temporary.unlink(missing_ok=True)
            _run_low_memory_concat_fallback(prepared_sources, audio_path, music_path, duration, temporary, cwd=job_dir)
        else:
            raise
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
