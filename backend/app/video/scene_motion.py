"""Bounded camera plans; no arbitrary filter expressions or invented facial motion."""
import math

def validate_scene_plan(plan, count):
    if plan is None: return None
    if len(plan) != count: raise ValueError('One plan is required per scene')
    for scene in plan:
        kind = scene['visual_type']
        if kind not in {'archival_photo', 'licensed_clip', 'ai_illustration'}:
            raise ValueError('Unsupported visual type')
        if not scene.get('purpose'): raise ValueError('Explain each scene purpose')
        if kind == 'ai_illustration':
            provenance = scene.get('generation', {})
            if not all(provenance.get(k) for k in ('provider', 'model', 'prompt')):
                raise ValueError('Imported AI images require provider, model and prompt provenance')
            if scene.get('disclosure') != 'AI illustration':
                raise ValueError('AI illustrations require readable disclosure')
        motion = scene['motion']
        if motion['type'] not in {'push_in', 'pull_out', 'pan_left', 'pan_right', 'hold'}:
            raise ValueError('Unsupported motion preset')
        amount = float(motion.get('amount', .06))
        if not math.isfinite(amount) or not 0 <= amount <= .12:
            raise ValueError('Camera travel must be between zero and twelve percent')
        if motion['type'] == 'hold' and not motion.get('reason'):
            raise ValueError('A still moment needs an editorial reason')
        if scene.get('transition_in', 'cut') not in {'cut', 'dissolve', 'crossfade', 'slide', 'wipe', 'flash', 'zoomin', 'smoothleft', 'radial'}:
            raise ValueError('Use a clean cut or short transition')
    return plan

def planned_motion(frames, focal, plan):
    motion = plan['motion']; kind = motion['type']; amount = float(motion.get('amount', .06))
    n = max(1, frames-1)
    progress = f'(0.5-0.5*cos(PI*on/{n}))'
    x, y = (max(0, min(1, float(v))) for v in focal)
    zoom = f'1+{amount:.5f}*{progress}'; anchor = f'{x:.5f}'
    if kind == 'pull_out': zoom = f'{1+amount:.5f}-{amount:.5f}*{progress}'
    elif kind in {'pan_left', 'pan_right'}:
        zoom = f'{1+amount:.5f}'
        anchor = progress if kind == 'pan_right' else f'(1-{progress})'
    elif kind == 'hold': zoom = '1'
    return zoom, f'(iw-iw/zoom)*{anchor}', f'(ih-ih/zoom)*{y:.5f}', kind
