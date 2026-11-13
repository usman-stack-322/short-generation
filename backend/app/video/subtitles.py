"""Estimated phrase timing; replace with forced alignment in Day 2."""
import re
from app.core.languages import language_info, text_units
from app.video.fonts import resolve_font


CAPTION_STYLES = {
    'viral_gold': {
        'preferred_fonts': ('ariblk.ttf', 'seguibl.ttf', 'impact.ttf', 'segoeuib.ttf'),
        'font_size': 82,
        'max_words': 3,
        'outline': 6,
        'shadow': 3,
        'outline_colour': '&H00080C14',
        'back_colour': '&H99000000',
        'highlight_color': '#FFE600',
        'active_scale': 112,
        'margin_v': 430,
        'margin_l': 75,
        'margin_r': 75,
        'subtitle_mode': 'word-highlight',
    },
    'cyan_pop': {
        'preferred_fonts': ('ariblk.ttf', 'seguibl.ttf', 'impact.ttf', 'segoeuib.ttf'),
        'font_size': 82,
        'max_words': 3,
        'outline': 6,
        'shadow': 3,
        'outline_colour': '&H00120A06',
        'back_colour': '&H99000000',
        'highlight_color': '#00E5FF',
        'active_scale': 112,
        'margin_v': 430,
        'margin_l': 75,
        'margin_r': 75,
        'subtitle_mode': 'word-highlight',
    },
    'clean_broadcast': {
        'preferred_fonts': ('segoeuib.ttf', 'ariblk.ttf', 'calibrib.ttf'),
        'font_size': 70,
        'max_words': 4,
        'outline': 5,
        'shadow': 2,
        'outline_colour': '&H000A0A0A',
        'back_colour': '&H90000000',
        'highlight_color': '#FF8C00',
        'active_scale': 106,
        'margin_v': 390,
        'margin_l': 85,
        'margin_r': 85,
        'subtitle_mode': 'word-highlight',
    },
    'classic': {
        'preferred_fonts': (),
        'font_size': 60,
        'max_words': 5,
        'outline': 3,
        'shadow': 1,
        'outline_colour': '&H00101C2A',
        'back_colour': '&H80000000',
        'highlight_color': '#FFFFFF',
        'active_scale': 100,
        'margin_v': 320,
        'margin_l': 110,
        'margin_r': 110,
        'subtitle_mode': None,
    },
}


def subtitle_cues(script, duration, max_words=7, language='en-US'):
    chinese = language_info(language).code == 'zh-CN'
    tokenize = lambda value: text_units(value, language)
    words = tokenize(script)
    chunks = []
    for sentence in re.findall(r'[^.!?。！？؟۔]+[.!?。！？؟۔]*', script):
        sentence_words = tokenize(sentence)
        chunks.extend(sentence_words[i:i + max_words] for i in range(0, len(sentence_words), max_words))
    elapsed = 0
    cues = []
    for chunk in chunks:
        end = elapsed + duration * len(chunk) / max(1, len(words))
        cues.append((elapsed, end, ('' if chinese else ' ').join(chunk)))
        elapsed = end
    return cues


def stamp(seconds, srt=False):
    milliseconds = round(seconds * 1000)
    h, milliseconds = divmod(milliseconds, 3600000)
    m, milliseconds = divmod(milliseconds, 60000)
    s, milliseconds = divmod(milliseconds, 1000)
    return f'{h:02}:{m:02}:{s:02},{milliseconds:03}' if srt else f'{h}:{m:02}:{s:02}.{milliseconds // 10:02}'


def _word_intervals_for_cue(cue_start, cue_end, duration, words, timing, search_from):
    """Map real narration word timestamps into [cue_start, cue_end] for exact spoken highlights."""
    if not words:
        return [], search_from
    count = len(words)
    if not timing or not timing.get('words') or count == 1:
        step = (cue_end - cue_start) / max(1, count)
        advance = min(len(timing.get('words', [])), search_from + count) if timing else search_from
        return [(cue_start + i * step, cue_start + (i + 1) * step) for i in range(count)], advance

    t_words = timing['words']
    total_dur = float(timing.get('duration') or 0)
    scale = (float(duration) / total_dur) if total_dur > 0 else 1.0
    matched_starts = []
    cursor = search_from
    for w in words:
        clean_w = w.strip()
        found_idx = None
        for idx in range(cursor, min(len(t_words), cursor + 8)):
            tw_text = t_words[idx].get('text')
            if tw_text is None or tw_text == clean_w or clean_w in tw_text or tw_text in clean_w:
                found_idx = idx
                break
        if found_idx is None and cursor < len(t_words):
            found_idx = cursor
        if found_idx is not None:
            matched_starts.append(float(t_words[found_idx]['start']) * scale)
            cursor = found_idx + 1
        else:
            matched_starts.append(None)

    rel_starts = [cue_start]
    for idx in range(1, count):
        est = matched_starts[idx]
        if est is None:
            est = cue_start + (cue_end - cue_start) * idx / count
        min_t = rel_starts[-1] + 0.03
        max_t = cue_end - 0.03 * (count - idx)
        rel_starts.append(max(min_t, min(max_t, est)))

    intervals = []
    for idx in range(count):
        s_t = rel_starts[idx]
        e_t = rel_starts[idx + 1] if idx + 1 < count else cue_end
        intervals.append((s_t, max(s_t + 0.02, e_t)))
    return intervals, cursor


def write_subtitles(script, duration, ass_path, srt_path, preset=None):
    preset = preset or {}
    style_cfg = CAPTION_STYLES.get(preset.get('caption_style') or '', {})
    merged = {**style_cfg, **preset}
    language = language_info(merged.get('language', 'en-US'))
    pref_fonts = merged.get('preferred_fonts', ()) if not language.rtl else ()
    face = resolve_font(language.code, script, preferred_fonts=pref_fonts)
    timing = merged.get('narration_timing')
    max_words = merged.get('max_words', 6)
    if timing:
        from app.video.alignment import aligned_cues
        cues = aligned_cues(script, duration, timing, max_words, merged.get('documentary', False), merged.get('scene_boundaries', ()))
    else:
        cues = subtitle_cues(script, duration, max_words, language.code)

    size = merged.get('font_size', 58)
    outline = merged.get('outline', 3)
    shadow = merged.get('shadow', 1)
    outline_col = merged.get('outline_colour', '&H00101C2A')
    back_col = merged.get('back_colour', '&H80000000')
    margin = merged.get('margin_v') or (820 if merged.get('caption_position') == 'center' else (260 if merged.get('documentary') else 350))
    margin_l = merged.get('margin_l', 120)
    margin_r = merged.get('margin_r', 140)
    header = (
        '[Script Info]\n'
        'ScriptType: v4.00+\n'
        'PlayResX: 1080\n'
        'PlayResY: 1920\n'
        'WrapStyle: 0\n'
        '[V4+ Styles]\n'
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
        'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, '
        'Alignment, MarginL, MarginR, MarginV, Encoding\n'
        f'Style: Default,{face.family},{size},&H00FFFFFF,&H00FFFFFF,{outline_col},{back_col},-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,{margin_l},{margin_r},{margin},1\n'
        '[Events]\n'
        'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    )

    lines = []
    srt = []
    word_cursor = 0
    sub_mode = merged.get('subtitle_mode')
    active_scale = int(merged.get('active_scale', 100))
    use_timed_highlight = bool(sub_mode == 'word-highlight' and (not timing or style_cfg))

    for i, (start, end, text) in enumerate(cues):
        safe = re.sub(r'[{}\\]', '', text).replace('\n', ' ')
        if merged.get('documentary') and not language.rtl and len(safe) > 29:
            words_doc = safe.split()
            if len(words_doc) > 1:
                split = min(range(1, len(words_doc)), key=lambda idx: abs(len(' '.join(words_doc[:idx])) - len(' '.join(words_doc[idx:]))))
                safe = ' '.join(words_doc[:split]) + r'\N' + ' '.join(words_doc[split:])
        # Unicode bidi embeddings preserve logical letter order and mixed-direction names.
        if language.rtl:
            safe = '\u202b' + safe + '\u202c'

        if use_timed_highlight and not language.rtl:
            color = (merged.get('highlight_color') or '#61e8b6').lstrip('#')
            bgr = color[4:6] + color[2:4] + color[0:2]
            words = list(safe) if language.code == 'zh-CN' else safe.split()
            if timing:
                intervals, word_cursor = _word_intervals_for_cue(start, end, duration, words, timing, word_cursor)
            else:
                chunk_duration = (end - start) / max(1, len(words))
                intervals = [(start + idx * chunk_duration, start + (idx + 1) * chunk_duration) for idx in range(len(words))]
            active_tag = r'{\c&H' + bgr + r'&' + (rf'\fscx{active_scale}\fscy{active_scale}' if active_scale > 100 else '') + '}'
            reset_tag = r'{\c&HFFFFFF&' + (r'\fscx100\fscy100' if active_scale > 100 else '') + '}'
            for index, (ws, we) in enumerate(intervals):
                highlighted = ('' if language.code == 'zh-CN' else ' ').join(
                    (active_tag + w + reset_tag) if j == index else w
                    for j, w in enumerate(words)
                )
                lines.append(f'Dialogue: 0,{stamp(ws)},{stamp(we)},Default,,0,0,0,,{highlighted}\n')
        else:
            lines.append(f'Dialogue: 0,{stamp(start)},{stamp(end)},Default,,0,0,0,,{safe}\n')
        srt.append(f'{i + 1}\n{stamp(start, True)} --> {stamp(end, True)}\n{text}\n\n')
    if merged.get('illustration_intervals'):
        disclosure = f'Style: Disclosure,{face.family},38,&H00FFFFFF,&H00FFFFFF,&H00101C2A,&H80000000,0,0,0,0,100,100,0,0,1,3,1,8,120,120,140,1\n'
        header = header.replace('[Events]', disclosure + '[Events]')
        for start, end in merged['illustration_intervals']:
            lines.append(f'Dialogue: 1,{stamp(start)},{stamp(end)},Disclosure,,0,0,0,,AI illustration\n')
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path.write_text(header + ''.join(lines), encoding='utf-8')
    srt_path.write_text(''.join(srt), encoding='utf-8')
