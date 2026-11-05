import textwrap
import json
from pathlib import Path
from PIL import Image, ImageDraw
from app.services.assets.demo import font
from app.core.languages import language_info
from app.video.fonts import resolve_font

def create_cover(image_path: Path, headline: str, destination: Path, brand_color='#61e8b6', language='en-US'):
    info=language_info(language)
    headline=headline.strip()
    if not headline: raise ValueError('Cover text must not be empty')
    selected=resolve_font(info.code,headline)
    options={'direction':'rtl','align':'right','language':info.code.split('-')[0]} if info.rtl else {}
    image = Image.open(image_path).convert('RGB').resize((1080,1920))
    draw = ImageDraw.Draw(image)
    words = headline.split()[:5]
    # Fit within safe margins before drawing. A dark panel guarantees contrast.
    for size in range(86,39,-2):
        face=selected.load(size)
        wrapped=textwrap.fill(' '.join(words),max(12,int(1200/size)))
        bounds=draw.multiline_textbbox((0,0),wrapped,font=face,spacing=14,**options)
        if bounds[2]<=840 and bounds[3]<=270:
            break
    if bounds[2]>840 or bounds[3]>270:
        raise ValueError('Cover text exceeds safe margins; shorten the selected-language headline.')
    draw.rounded_rectangle((65,1290,1015,1700), radius=36, fill='#07101f')
    draw.rounded_rectangle((100,1325,270,1336),radius=5,fill=brand_color)
    position=(970-(bounds[2]-bounds[0]),1380) if info.rtl else (110,1380)
    draw.multiline_text(position,wrapped,font=face,fill='white',spacing=14,**options)
    destination.parent.mkdir(parents=True,exist_ok=True)
    image.save(destination)
    destination.with_suffix('.checks.json').write_text(json.dumps({
        'canvas':[1080,1920],'text_bounds':list(bounds),'safe_margins':True,
        'contrast':'white on #07101f panel','face_detection':'not performed; panel avoids the central portrait area',
        'selected_layout':'lower safe panel','text':wrapped.replace('\n',' ')}),encoding='utf-8')
    return destination
