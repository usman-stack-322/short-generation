"""Check actual glyph coverage before rendering instead of drawing missing squares."""
import os
import unicodedata
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
            family=font['name'].getDebugName(1) or font['name'].getDebugName(4) or path.stem
            result.append((FontFace(path,family,index),frozenset((font.getBestCmap() or {}).keys())))
    return result


@lru_cache(maxsize=64)
def font_coverage(face: FontFace) -> frozenset[int]:
    for loaded_face, coverage in _faces(face.path.resolve()):
        if loaded_face.index == face.index:
            return coverage
    return frozenset()


def _is_skippable_symbol(ch: str) -> bool:
    if ch.isspace():
        return True
    cp = ord(ch)
    if cp in {0x00AD, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFE0E, 0xFE0F, 0xFEFF}:
        return True
    cat = unicodedata.category(ch)
    if cat == 'Cf':
        return True
    # Decorative emojis/pictographs shouldn't abort narration rendering when standard font glyphs exist.
    if cp >= 0x1F000 or 0x2600 <= cp <= 0x27BF:
        return True
    return False


def resolve_font(code, text, preferred_fonts=()):
    language=language_info(code)
    if language.rtl and not features.check_feature('raqm'):
        raise RuntimeError(f'{language.name} rendering requires Pillow with libraqm shaping support.')
    required={ord(char) for char in text if not _is_skippable_symbol(char)}
    required_letters={ord(char) for char in text if not _is_skippable_symbol(char) and unicodedata.category(char).startswith('L')}
    roots=[BACKEND_DIR/'fonts',Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts',
           Path('/usr/share/fonts/truetype/dejavu'),
           Path('/usr/share/fonts/truetype/liberation'),
           Path('/usr/share/fonts/truetype/liberation2'),
           Path('/usr/share/fonts/truetype/noto'),
           Path('/usr/share/fonts/opentype/noto')]
    candidates = tuple(dict.fromkeys([*preferred_fonts, *language.font_files])) if preferred_fonts else language.font_files
    letter_fallback = None
    for name in candidates:
        for root in roots:
            path=root/name
            if path.is_file():
                for face,coverage in _faces(path.resolve()):
                    if required.issubset(coverage):
                        return face
                    if letter_fallback is None and required_letters.issubset(coverage):
                        letter_fallback = face
    if letter_fallback is not None:
        return letter_fallback
    raise RuntimeError(f'Missing {language.name}-compatible font or glyphs. Install '+
                       ', '.join(language.font_files)+f' in Windows Fonts or {BACKEND_DIR / "fonts"}.')
