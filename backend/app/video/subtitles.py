"""Estimated phrase timing; replace with forced alignment in Day 2."""
import re
from app.core.languages import language_info,text_units
from app.video.fonts import resolve_font

def subtitle_cues(script, duration, max_words=7, language='en-US'):
    chinese=language_info(language).code=='zh-CN'
    tokenize=lambda value: text_units(value,language)
    words = tokenize(script)
    chunks = []
    for sentence in re.findall(r'[^.!?。！？؟۔]+[.!?。！？؟۔]*',script):
        sentence_words=tokenize(sentence)
        chunks.extend(sentence_words[i:i+max_words] for i in range(0,len(sentence_words),max_words))
    elapsed = 0
    cues=[]
    for chunk in chunks:
        end = elapsed + duration * len(chunk)/max(1,len(words))
        cues.append((elapsed,end,('' if chinese else ' ').join(chunk)))
        elapsed=end
    return cues

def stamp(seconds, srt=False):
    milliseconds = round(seconds * 1000)
    h, milliseconds = divmod(milliseconds,3600000)
    m, milliseconds = divmod(milliseconds,60000)
    s, milliseconds = divmod(milliseconds,1000)
    return f'{h:02}:{m:02}:{s:02},{milliseconds:03}' if srt else f'{h}:{m:02}:{s:02}.{milliseconds//10:02}'

def write_subtitles(script, duration, ass_path, srt_path, preset=None):
    preset=preset or {}
    language=language_info(preset.get('language','en-US'))
    face=resolve_font(language.code,script)
    timing=preset.get('narration_timing')
    if timing:
        from app.video.alignment import aligned_cues
        cues=aligned_cues(script,duration,timing,preset.get('max_words',6),preset.get('documentary',False),preset.get('scene_boundaries',()))
    else:cues = subtitle_cues(script,duration,preset.get('max_words',6),language.code)
    header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,58,&H00FFFFFF,&H00FFFFFF,&H00101C2A,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,110,110,310,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    size=preset.get('font_size',58)
    margin=820 if preset.get('caption_position')=='center' else (260 if preset.get('documentary') else 350)
    header=header.replace('Default,Arial,58,',f'Default,{face.family},{size},').replace('110,110,310,1',f'120,140,{margin},1')
    lines=[]
    srt=[]
    for i,(start,end,text) in enumerate(cues):
        safe = re.sub(r'[{}\\]', '', text).replace('\n',' ')
        if preset.get('documentary') and not language.rtl and len(safe)>29:
            words=safe.split()
            if len(words)>1:
                split=min(range(1,len(words)),key=lambda i:abs(len(' '.join(words[:i]))-len(' '.join(words[i:]))))
                safe=' '.join(words[:split])+r'\N'+' '.join(words[split:])
        # Unicode bidi embeddings preserve logical letter order and mixed-direction names.
        if language.rtl:
            safe='\u202b'+safe+'\u202c'
        if preset.get('subtitle_mode')=='word-highlight' and not timing:
            color=preset.get('highlight_color','#61e8b6').lstrip('#')
            bgr=color[4:6]+color[2:4]+color[0:2]
            words=list(safe) if language.code=='zh-CN' else safe.split()
            chunk_duration=(end-start)/max(1,len(words))
            for index,word in enumerate(words):
                highlighted=('' if language.code=='zh-CN' else ' ').join((r'{\c&H'+bgr+r'&}'+w+r'{\c&HFFFFFF&}') if i==index else w for i,w in enumerate(words))
                lines.append(f'Dialogue: 0,{stamp(start+index*chunk_duration)},{stamp(start+(index+1)*chunk_duration)},Default,,0,0,0,,{highlighted}\n')
        else:
            lines.append(f'Dialogue: 0,{stamp(start)},{stamp(end)},Default,,0,0,0,,{safe}\n')
        srt.append(f'{i+1}\n{stamp(start,True)} --> {stamp(end,True)}\n{text}\n\n')
    if preset.get('illustration_intervals'):
        disclosure=f'Style: Disclosure,{face.family},38,&H00FFFFFF,&H00FFFFFF,&H00101C2A,&H80000000,0,0,0,0,100,100,0,0,1,3,1,8,120,120,140,1\n'
        header=header.replace('[Events]',disclosure+'[Events]')
        for start,end in preset['illustration_intervals']:
            lines.append(f'Dialogue: 1,{stamp(start)},{stamp(end)},Disclosure,,0,0,0,,AI illustration\n')
    ass_path.parent.mkdir(parents=True,exist_ok=True)
    srt_path.parent.mkdir(parents=True,exist_ok=True)
    ass_path.write_text(header+''.join(lines),encoding='utf-8')
    srt_path.write_text(''.join(srt),encoding='utf-8')
