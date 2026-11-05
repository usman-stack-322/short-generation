"""Check actual glyph coverage before rendering instead of drawing missing squares."""
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from PIL import ImageFont, features
from fontTools.ttLib import TTFont, TTCollection
from app.core.config import BACKEND_DIR
from app.core.languages import language_info


@dataclass(frozen=True)
class FontFace:
    path: Path
    family: str
    index: int
    def load(self,size):
        return ImageFont.truetype(str(self.path),size,index=self.index)


@lru_cache(maxsize=64)
def _faces(path):
    count=1
    if path.suffix.lower()=='.ttc':
        with TTCollection(str(path),lazy=True) as collection:
            count=len(collection.fonts)
    result=[]
    for index in range(count):
        with TTFont(str(path),fontNumber=index,lazy=True) as font:
            family=font['name'].getDebugName(1)
            result.append((FontFace(path,family,index),frozenset((font.getBestCmap() or {}).keys())))
    return result


def resolve_font(code,text):
    language=language_info(code)
    if language.rtl and not features.check_feature('raqm'):
        raise RuntimeError(f'{language.name} rendering requires Pillow with libraqm shaping support.')
    required={ord(char) for char in text if not char.isspace() and ord(char) not in {0x200c,0x200d,0x200e,0x200f}}
    roots=[BACKEND_DIR/'fonts',Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts',
           Path('/usr/share/fonts/truetype/dejavu'),Path('/usr/share/fonts/truetype/noto'),
           Path('/usr/share/fonts/opentype/noto')]
    for root in roots:
        for name in language.font_files:
            path=root/name
            if path.is_file():
                for face,coverage in _faces(path.resolve()):
                    if required.issubset(coverage):
                        return face
    raise RuntimeError(f'Missing {language.name}-compatible font or glyphs. Install '+
                       ', '.join(language.font_files)+f' in Windows Fonts or {BACKEND_DIR / "fonts"}.')
