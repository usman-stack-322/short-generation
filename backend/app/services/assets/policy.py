"""Conservative metadata gates. Metadata is evidence, never proof of authenticity."""
import re
import unicodedata
from urllib.parse import urlparse


def normalized(value):
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', value).casefold()))


def license_allowed(name, url, creator):
    name = normalized(name)
    host = urlparse(url).hostname
    if name.startswith('cc by ') and not any(x in name.split() for x in ('sa','nc','nd')):
        return bool(creator and host == 'creativecommons.org' and re.fullmatch(r'https://creativecommons.org/licenses/by/[1-4]\.0/?', url))
    return name in {'cc0', 'cc0 1 0', 'public domain'} and (not url or bool(re.fullmatch(r'https://creativecommons.org/publicdomain/(zero|mark)/1\.0/?',url)))


def photo_supported(item):
    text = normalized(' '.join(str(item.get(k, '')) for k in ('title','description','categories')))
    forbidden = ('ai generated','ai enhanced','ai assisted','midjourney','stable diffusion','dall e','deepfake','faceswap','face swapped','computer generated','photomontage','artificial intelligence','synthetic','face swap','illustration','drawing','painting','rendering','composite','collage','screenshot','watermark removal','digitally manipulated')
    return not any(term in text for term in forbidden) and (
        item.get('source') in {'pexels', 'pixabay', 'openverse'} or any(term in text for term in ('photograph','photo taken','photo of','photographs'))
        or bool(item.get('camera_make') and item.get('camera_model')))


def matches_subject(item, personality):
    # Wikimedia's structured depicts identifier is stronger than a search hit or a name alone.
    entity = item.get('subject_entity')
    return bool(entity and entity in item.get('depicts', []) and normalized(personality) in normalized(
        ' '.join(str(item.get(k,'')) for k in ('title','description','categories'))))


def contextual(item, query):
    # Never misrepresent a generic person as the selected personality.
    text = normalized(' '.join(str(item.get(k,'')) for k in ('title','description','categories')))
    words = set(normalized(query).split()) - {'photograph','photographs','photo','generic'}
    return bool(words) and words.issubset(set(text.split())) and not any(term in text.split() for term in ('portrait','player','actor','politician'))
