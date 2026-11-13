"""Compose retained source photos, never animate a baked preview matte."""
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter, ImageEnhance


def source_photo(path):
    path = Path(path)
    original = path.with_name(path.stem + '-source.jpg')
    return original if original.is_file() else path


def compose_photo(path, destination, focal=(.5, .45), protect_top=True, native_limit=False, max_zoom=1.13):
    source = source_photo(path)
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert('RGB')
        image.load()
    if min(image.size) < 400:
        raise ValueError('Photo resolution is unsuitable; replace it with a larger genuine source')
    width, height = image.size
    canvas_size = (2160, 3840)
    x, y = [max(0, min(1, float(v))) for v in focal]
    if .45 <= width / height <= .72 and (not native_limit or (width>=1080*max_zoom and height>=1920*max_zoom)):
        if protect_top:y=min(y,.18)
        canvas = ImageOps.fit(image, canvas_size, Image.Resampling.LANCZOS, centering=(x, y))
        treatment = 'full-bleed portrait; focal crop'
    else:
        # Same photograph fills the entire frame; the sharp foreground retains
        # all action/heads/awards. No generic background or fabricated imagery.
        canvas = ImageOps.fit(image, canvas_size, Image.Resampling.LANCZOS)
        canvas = canvas.filter(ImageFilter.GaussianBlur(55))
        canvas = ImageEnhance.Brightness(ImageEnhance.Color(canvas).enhance(.8)).enhance(.78)
        bounds=(min(2080,int(width*2/max_zoom)),min(2840,int(height*2/max_zoom))) if native_limit else (2080,2840)
        foreground = ImageOps.contain(image, bounds, Image.Resampling.LANCZOS)
        position = ((2160-foreground.width)//2, (3840-foreground.height)//2)
        shadow = Image.new('RGBA', canvas_size)
        shadow.paste((0, 0, 0, 110), (position[0]-14, position[1]-14,
                     position[0]+foreground.width+14, position[1]+foreground.height+14))
        canvas = Image.alpha_composite(canvas.convert('RGBA'), shadow.filter(ImageFilter.GaussianBlur(32))).convert('RGB')
        canvas.paste(foreground, position)
        treatment = 'same-photo blurred full-bleed background; complete fitted foreground'
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs = {'compress_level': 1} if destination.suffix.lower() == '.png' else {'quality': 96, 'subsampling': 0}
    canvas.save(destination, **save_kwargs)
    return {'source': str(source), 'source_size': [width, height], 'treatment': treatment,
            'focal': [x, y], 'prepared_path': str(destination), 'native_detail_preserved': native_limit, 'maximum_zoom':max_zoom}


def motion_expression(index, frames, focal=(.5, .45)):
    """Twelve percent travel, eased at both ends, with intentional direction."""
    n = max(1, frames-1)
    progress = f'(0.5-0.5*cos(PI*on/{n}))'
    x, y = focal
    if index % 3 == 0:
        zoom = f'1.01+0.12*{progress}'
        movement = 'push in'
        anchor = f'{x:.4f}'
    elif index % 3 == 1:
        zoom = f'1.13-0.12*{progress}'
        movement = 'pull out'
        anchor = f'{x:.4f}'
    else:
        zoom = '1.09'
        anchor = f'(0.25+0.5*{progress})'
        movement = 'lateral pan'
    return zoom, f'(iw-iw/zoom)*{anchor}', f'(ih-ih/zoom)*{y:.4f}', movement
