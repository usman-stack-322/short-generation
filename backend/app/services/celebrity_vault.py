"""Connected Local Celebrity Folder scanner, scene-aware matcher, and real web photo fallback."""
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import io
import json
import os
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image, ImageOps
from sqlalchemy import func, select

from app.core.security import new_id
from app.models import CelebrityAsset, CelebrityFolder
from app.services.assets.licensed import BROWSER_USER_AGENT

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}
VIDEO_EXTS = {'.mp4', '.mov', '.webm', '.mkv', '.m4v'}
ALLOWED_EXTS = IMAGE_EXTS | VIDEO_EXTS

GENERIC_SUBFOLDERS = {
    'videos', 'video', 'clips', 'clip', 'images', 'image', 'photos', 'photo',
    'pics', 'pic', 'pictures', 'media', 'raw', 'broll', 'b roll', 'b-roll',
    'assets', 'celebrities', 'celebrity', 'data', 'new folder', 'untitled folder',
    'int', 'ints', 'intro', 'outro', 'interview', 'interviews', 'podcast', 'podcasts',
    'highlights', 'highlight', 'reaction', 'reactions', 'short', 'shorts',
    'cut', 'cuts', 'archive', 'old', 'new', 'extra', 'extras', 'temp', 'misc',
}

_GENERIC_BROLL_FOLDERS = {
    'basketball highlights', 'nba highlights', 'football highlights', 'highlights',
    'crowd', 'arena', 'broll', 'b roll', 'studio background', 'panel',
}

_STOP_PROPER_PHRASES = {
    'close up', 'wide angle', 'wide shot', 'medium shot', 'high profile',
    'sports media', 'media coverage', 'nba legends', 'nba sports', 'talk show',
    'editorial photo', 'archival clip', 'basketball fans', 'heated sports',
    'this passionate', 'new york', 'los angeles', 'united states',
}

# Common editorial/title-case non-person nouns that must never trigger missing-person blocks.
_NON_PERSON_WORDS = {
    'clash', 'clashes', 'commentary', 'analysis', 'highlights', 'highlight', 'arena',
    'studio', 'podcast', 'podcasts', 'show', 'debate', 'debates', 'media', 'discussion',
    'discussions', 'court', 'floor', 'desk', 'room', 'basketball', 'football', 'baseball',
    'soccer', 'boxing', 'ufc', 'nba', 'wnba', 'nfl', 'mlb', 'ncaa', 'news', 'report',
    'reports', 'story', 'history', 'timeline', 'moment', 'moments', 'scene', 'clip',
    'clips', 'video', 'videos', 'photo', 'photos', 'image', 'images', 'picture', 'crowd',
    'fans', 'panel', 'host', 'microphone', 'microphones', 'mic', 'interview', 'interviews',
    'conference', 'press', 'game', 'games', 'series', 'finals', 'season', 'league',
    'championship', 'trophy', 'ring', 'rings', 'award', 'awards', 'ceremony', 'hall',
    'fame', 'star', 'stars', 'legend', 'legends', 'player', 'players', 'coach', 'coaches',
    'team', 'teams', 'club', 'city', 'state', 'street', 'house', 'building', 'screen',
    'setup', 'reaction', 'reactions', 'impact', 'drama', 'beef', 'feud', 'battle', 'fight',
    'match', 'round', 'score', 'scoreboard', 'camera', 'lighting', 'spotlight', 'stage',
    'tour', 'concert', 'album', 'song', 'track', 'record', 'records', 'label', 'world',
    'america', 'american', 'national', 'global', 'eastern', 'western', 'north', 'south',
    'east', 'west', 'first', 'second', 'third', 'final', 'early', 'late', 'modern',
    'classic', 'old', 'new', 'big', 'major', 'top', 'best', 'real', 'true', 'full',
    'live', 'breaking', 'special', 'official', 'exclusive', 'historic', 'famous',
    'iconic', 'heated', 'intense', 'passionate', 'sports', 'sport', 'athlete', 'athletes',
    'athletic', 'locker', 'tunnel', 'bench', 'sideline', 'jersey', 'hoops', 'network',
    'broadcast', 'broadcasting', 'digital', 'production', 'editorial', 'archival',
    'youtube', 'espn', 'fox', 'tnt', 'nbc', 'cbs', 'abc', 'context', 'overviews',
}

_NICKNAME_ALIASES = {
    'nick young': ['swaggy p', 'swaggyp'],
    'stephen curry': ['steph curry'],
    'lebron james': ['king james', 'bron'],
    'shaquille o neal': ['shaq', 'shaquille oneal'],
    'shaquille oneal': ['shaq', 'shaquille o neal'],
    'iman shumpert': ['shump'],
    'gilbert arenas': ['agent zero', 'gils arena'],
    'joe budden': ['budden'],
    'carmelo anthony': ['melo'],
    'charles barkley': ['chuck'],
}

MOOD_KEYWORDS = {
    'angry', 'mad', 'rant', 'yelling', 'heated', 'furious', 'serious', 'stern',
    'laugh', 'laughing', 'funny', 'smile', 'smiling', 'happy', 'shocked',
    'surprised', 'confused', 'podcast', 'interview', 'mic', 'studio', 'court',
    'game', 'bench', 'press', 'reaction', 'talking', 'pointing', 'celebrating',
}

AI_BLOCKLIST = (
    'lexica.art', 'civitai.com', 'midjourney', 'prompthero', 'openart.ai',
    'nightcafe', 'artstation', 'deviantart', 'pollinations', 'stablediffusion',
    'stable-diffusion', 'dall-e', 'dalle', 'ai generated', 'ai-generated',
    'illustration', 'cartoon', 'vector', 'clipart', '3d render', 'digital art',
    'fan art', 'fanart', 'drawing', 'painting', 'sketch', 'caricature',
)

WATERMARK_STOCK_BLOCKLIST = (
    'gettyimages', 'getty', 'alamy', 'shutterstock', 'istockphoto', 'istock',
    'dreamstime', 'depositphotos', '123rf', 'vecteezy', 'adobestock', 'stock.adobe',
    'bigstockphoto', 'bigstock', 'canstockphoto', 'canstock', 'pond5', 'envato',
    'elements.envato', 'graphicriver', 'freepik', 'megapixl', 'colourbox',
    'agefotostock', 'superstock', 'corbis', 'wireimage', 'filmmagic',
    'imago-images', 'imago.com', 'bridgeman', 'ingimage', 'dissolve.com',
    'punchstock', 'masterfile', 'photolibrary', 'panthermedia', 'westend61',
    'watermark', 'watermarked', 'comp-image', 'preview only', 'sample only',
    'editorial use only', 'royalty-free preview', 'stockcake', 'rawpixel',
    'poster', 'flyer', 'meme', 'thumbnail', 'infographic', 'text overlay',
)


def _norm_entity(text: str) -> str:
    """Normalize names and queries so accents, initials, and '$' aliases match cleanly."""
    t = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode('ascii')
    t = t.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    t = t.replace('$', 's')
    t = re.sub(r"\b([A-Za-z])\.", r"\1", t)
    t = re.sub(r"'s\b", ' ', t, flags=re.I)
    return ' '.join(re.findall(r'[a-z0-9]+', t.lower()))


def _clean_folder_name(part: str) -> str:
    """Clean Google Drive export suffixes, arrows, and trailing folder noise while keeping real names."""
    s = part.replace('’', "'").replace('‘', "'")
    s = re.sub(r'[-_\s]*20\d{6}T\d{6}Z(?:[-_0-9]+)?$', '', s, flags=re.I)
    s = re.sub(r'[→←•|]+', ' ', s)
    s = s.replace('_', ' ')
    s = re.sub(r'\s*-\s*', ' ', s)
    s = re.sub(r'\s+\(\d+\)$', '', s)
    s = re.sub(r'\s+\bnew\b(?:\s+\d{1,4})?$', '', s, flags=re.I)
    if not re.match(r'^\d+\s', s.strip()):
        s = re.sub(r'\s+\d{1,2}$', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    if s.lower() in {'new folder', 'untitled folder', 'copy'}:
        return ''
    return s


def _fast_fingerprint(path: Path, st) -> str:
    """Instant metadata fingerprint for scanning thousands of large files without blocking disk I/O."""
    sig = f'{path}:{st.st_size}:{st.st_mtime_ns}'.encode('utf-8', errors='ignore')
    return hashlib.sha256(sig).hexdigest()


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _parse_celebrity_and_mood(root: Path, file_path: Path) -> tuple[str, list[str]]:
    rel = file_path.relative_to(root)
    stem_tokens = [t for t in re.split(r'[_\-\s.]+', file_path.stem.lower()) if t]
    moods = [t for t in stem_tokens if t in MOOD_KEYWORDS]
    folder_parts = list(rel.parts[:-1])
    if folder_parts:
        # Walk from top-level celebrity folder downward so inner folders ('int/', 'pic/', 'New folder/')
        # contribute mood tags instead of overwriting the celebrity's real name.
        chosen = ''
        for part in folder_parts:
            cleaned = _clean_folder_name(part)
            low = cleaned.lower()
            for w in re.findall(r'[a-z0-9]+', low):
                if w in MOOD_KEYWORDS:
                    moods.append(w)
            if not cleaned or low in GENERIC_SUBFOLDERS or low in MOOD_KEYWORDS or len(low) < 2:
                continue
            if not chosen:
                chosen = cleaned
        if chosen:
            return chosen.title(), sorted(set(moods))
    name_tokens = [
        t for t in stem_tokens
        if not t.isdigit() and t not in MOOD_KEYWORDS and t not in {'img', 'pic', 'photo', 'clip', 'vid', 'video'}
    ]
    celeb = ' '.join(name_tokens[:4]).strip() or file_path.stem
    return celeb.title(), sorted(set(moods))


def _iter_media_entries(root: Path):
    """Fast iterative os.scandir walk yielding (Path, ext, stat_result) while skipping protected/temp dirs."""
    stack = [str(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    name = entry.name
                    if name.startswith('.tmp_') or name.startswith('$'):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if name.lower() == 'system volume information':
                                continue
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            ext = os.path.splitext(name)[1].lower()
                            if ext in ALLOWED_EXTS:
                                yield Path(entry.path), ext, entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
        except OSError:
            continue


def _iter_media_files(root: Path):
    """Backwards-compatible media file iterator."""
    for path, ext, _st in _iter_media_entries(root):
        yield path, ext


def _ensure_vault_folder_row(db, workspace_id: str, root: Path, preference: str | None = None) -> CelebrityFolder:
    folder_row = db.get(CelebrityFolder, workspace_id)
    if folder_row:
        if not folder_row.folder_path or Path(folder_row.folder_path) != root:
            folder_row.folder_path = str(root)
        if preference:
            folder_row.preference = preference
    else:
        folder_row = CelebrityFolder(
            workspace_id=workspace_id,
            folder_path=str(root),
            preference=preference or 'mix_both',
        )
        db.add(folder_row)
    return folder_row


def index_vault_files(db, workspace_id: str, root: Path, saved_paths: list[Path], preference: str | None = None) -> int:
    """Incrementally register newly uploaded clips in SQLite so 100GB+ uploads are usable immediately."""
    if not saved_paths:
        return 0
    _ensure_vault_folder_row(db, workspace_id, root, preference)
    now = datetime.now(timezone.utc)
    records_map: dict[str, tuple[str, str, str, str, str, str]] = {}
    for raw_path in saved_paths:
        try:
            path = raw_path.resolve()
            st = path.stat()
        except OSError:
            continue
        if st.st_size <= 0:
            continue
        ext = path.suffix.lower()
        if ext not in ALLOWED_EXTS or path.name.startswith('.tmp_'):
            continue
        media_type = 'video' if ext in VIDEO_EXTS else 'image'
        celeb_name, moods = _parse_celebrity_and_mood(root, path)
        records_map[str(path)] = (
            celeb_name,
            json.dumps(moods),
            media_type,
            path.name,
            ext,
            _fast_fingerprint(path, st),
        )
    if not records_map:
        return 0

    fps = list(records_map.keys())
    existing_rows: dict[str, CelebrityAsset] = {}
    for idx in range(0, len(fps), 500):
        chunk = fps[idx: idx + 500]
        for row in db.query(CelebrityAsset).filter(
            CelebrityAsset.workspace_id == workspace_id,
            CelebrityAsset.file_path.in_(chunk),
        ).all():
            existing_rows[row.file_path] = row

    new_records: list[CelebrityAsset] = []
    for fp, (celeb_name, moods_json, media_type, file_name, ext, digest) in records_map.items():
        prev = existing_rows.get(fp)
        if prev:
            if (
                prev.content_hash != digest
                or prev.celebrity_name != celeb_name
                or prev.mood_tags != moods_json
                or prev.media_type != media_type
            ):
                prev.celebrity_name = celeb_name
                prev.mood_tags = moods_json
                prev.media_type = media_type
                prev.file_name = file_name
                prev.ext = ext
                prev.content_hash = digest
        else:
            new_records.append(
                CelebrityAsset(
                    id=new_id(),
                    workspace_id=workspace_id,
                    celebrity_name=celeb_name,
                    mood_tags=moods_json,
                    media_type=media_type,
                    file_name=file_name,
                    file_path=fp,
                    ext=ext,
                    duration=None,
                    content_hash=digest,
                    created_at=now,
                )
            )
    for idx in range(0, len(new_records), 1000):
        db.bulk_save_objects(new_records[idx: idx + 1000])
    db.commit()
    return len(records_map)


def scan_celebrity_folder(db, workspace_id: str, folder_path: str, preference: str = 'mix_both') -> dict:
    root = Path(folder_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f'Directory not found: {root}')

    # Scan the entire directory tree BEFORE starting any SQLite write transaction!
    # Preserves existing asset IDs when unchanged so in-progress drafts/renders keep working smoothly.
    now = datetime.now(timezone.utc)
    scanned: dict[str, tuple[str, str, str, str, str, str]] = {}
    celeb_names: set[str] = set()

    for path, ext, st in sorted(_iter_media_entries(root), key=lambda item: str(item[0])):
        if st.st_size <= 0:
            continue
        media_type = 'video' if ext in VIDEO_EXTS else 'image'
        celeb_name, moods = _parse_celebrity_and_mood(root, path)
        celeb_names.add(celeb_name)
        scanned[str(path)] = (
            celeb_name,
            json.dumps(moods),
            media_type,
            path.name,
            ext,
            _fast_fingerprint(path, st),
        )

    folder_row = _ensure_vault_folder_row(db, workspace_id, root, preference or 'mix_both')

    existing_rows = {
        r.file_path: r
        for r in db.query(CelebrityAsset).filter_by(workspace_id=workspace_id).all()
    }
    stale_ids = [r.id for fp, r in existing_rows.items() if fp not in scanned]
    for idx in range(0, len(stale_ids), 500):
        db.query(CelebrityAsset).filter(
            CelebrityAsset.id.in_(stale_ids[idx: idx + 500])
        ).delete(synchronize_session=False)

    new_records: list[CelebrityAsset] = []
    for fp, (celeb_name, moods_json, media_type, file_name, ext, digest) in scanned.items():
        prev = existing_rows.get(fp)
        if prev:
            if (
                prev.content_hash != digest
                or prev.celebrity_name != celeb_name
                or prev.mood_tags != moods_json
                or prev.media_type != media_type
            ):
                prev.celebrity_name = celeb_name
                prev.mood_tags = moods_json
                prev.media_type = media_type
                prev.file_name = file_name
                prev.ext = ext
                prev.content_hash = digest
        else:
            new_records.append(
                CelebrityAsset(
                    id=new_id(),
                    workspace_id=workspace_id,
                    celebrity_name=celeb_name,
                    mood_tags=moods_json,
                    media_type=media_type,
                    file_name=file_name,
                    file_path=fp,
                    ext=ext,
                    duration=None,
                    content_hash=digest,
                    created_at=now,
                )
            )

    for idx in range(0, len(new_records), 1000):
        db.bulk_save_objects(new_records[idx: idx + 1000])
    db.commit()
    return {
        'workspace_id': workspace_id,
        'folder_path': str(root),
        'preference': folder_row.preference,
        'total_assets': len(scanned),
        'celebrities': sorted(celeb_names),
    }


def list_vault_celebrity_names(db, workspace_id: str, limit: int = 120) -> list[str]:
    """Return distinct local celebrity folder names sorted by asset count descending."""
    if db is None or not workspace_id:
        return []
    try:
        rows = db.query(CelebrityAsset.celebrity_name).filter_by(workspace_id=workspace_id).all()
    except Exception:
        return []
    counts = Counter(
        row[0] for row in rows
        if row and row[0] and _norm_entity(row[0]) not in GENERIC_SUBFOLDERS and _norm_entity(row[0]) not in _GENERIC_BROLL_FOLDERS
    )
    return [name for name, _cnt in counts.most_common(limit)]


def list_celebrity_library(db, workspace_id: str, limit_per_celebrity: int = 12) -> dict:
    folder_row = db.get(CelebrityFolder, workspace_id)
    count_rows = (
        db.query(CelebrityAsset.celebrity_name, CelebrityAsset.media_type, func.count(CelebrityAsset.id))
        .filter_by(workspace_id=workspace_id)
        .group_by(CelebrityAsset.celebrity_name, CelebrityAsset.media_type)
        .order_by(CelebrityAsset.celebrity_name)
        .all()
    )
    grouped: dict[str, dict] = {}
    total_assets = 0
    for celeb_name, media_type, cnt in count_rows:
        entry = grouped.setdefault(celeb_name, {
            'celebrity_name': celeb_name,
            'image_count': 0,
            'video_count': 0,
            'assets': [],
        })
        if media_type == 'video':
            entry['video_count'] += cnt
        else:
            entry['image_count'] += cnt
        total_assets += cnt

    if limit_per_celebrity > 0 and grouped:
        ranked = select(
            CelebrityAsset.id.label('asset_id'),
            func.row_number().over(
                partition_by=CelebrityAsset.celebrity_name,
                order_by=CelebrityAsset.file_name,
            ).label('rn'),
        ).where(CelebrityAsset.workspace_id == workspace_id).subquery()
        preview_rows = (
            db.query(CelebrityAsset)
            .join(ranked, CelebrityAsset.id == ranked.c.asset_id)
            .filter(ranked.c.rn <= limit_per_celebrity)
            .order_by(CelebrityAsset.celebrity_name, CelebrityAsset.file_name)
            .all()
        )
    else:
        preview_rows = (
            db.query(CelebrityAsset)
            .filter_by(workspace_id=workspace_id)
            .order_by(CelebrityAsset.celebrity_name, CelebrityAsset.file_name)
            .all()
        )

    for row in preview_rows:
        entry = grouped.get(row.celebrity_name)
        if not entry:
            continue
        entry['assets'].append({
            'id': row.id,
            'celebrity_name': row.celebrity_name,
            'media_type': row.media_type,
            'file_name': row.file_name,
            'ext': row.ext,
            'duration': row.duration,
            'mood_tags': json.loads(row.mood_tags or '[]'),
            'preview_url': f'/api/assets/vault/{row.id}/file',
        })
    return {
        'folder_path': folder_row.folder_path if folder_row else '',
        'preference': folder_row.preference if folder_row else 'mix_both',
        'total_assets': total_assets,
        'celebrities': list(grouped.values()),
    }


def stage_vault_asset_for_draft(asset: CelebrityAsset, scene_num: int, folder: Path) -> dict:
    src = Path(asset.file_path)
    if not src.is_file():
        raise ValueError(f'Celebrity vault file missing: {src}')
    folder.mkdir(parents=True, exist_ok=True)
    out_id = uuid4().hex[:10]
    dst = folder / f'vault_s{scene_num}_{out_id}{asset.ext}'
    shutil.copyfile(src, dst)
    real_hash = _file_hash(dst)
    return {
        'path': str(dst),
        'hash': real_hash,
        'source_url': '',
        'creator': asset.celebrity_name,
        'license': 'Connected Local Celebrity Folder',
        'license_url': '',
        'credit': f'{asset.celebrity_name} ({asset.file_name})',
        'kind': 'celebrity_clip' if asset.media_type == 'video' else 'celebrity_photo',
        'media_type': asset.media_type,
        'celebrity_name': asset.celebrity_name,
        'vault_asset_id': asset.id,
        'duration': asset.duration,
        'provider': 'celebrity_vault',
        'note': f'Local celebrity {asset.media_type} from connected folder ({asset.celebrity_name}).',
    }


def _has_phrase(norm_haystack: str, phrase: str) -> bool:
    if not phrase or len(phrase) < 3 or not norm_haystack:
        return False
    return re.search(rf'(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])', norm_haystack) is not None


def _names_close(a: str, b: str) -> bool:
    """True when two multi-word normalized names differ only by minor spelling/transliteration."""
    ta, tb = a.split(), b.split()
    if len(ta) < 2 or len(tb) < 2:
        return False
    if any(t in _NON_PERSON_WORDS for t in ta + tb):
        return False
    return (
        SequenceMatcher(None, a, b).ratio() >= 0.88
        and SequenceMatcher(None, ta[0], tb[0]).ratio() >= 0.75
        and SequenceMatcher(None, ta[-1], tb[-1]).ratio() >= 0.75
    )


def _celebrity_variants(celeb_name: str) -> list[str]:
    base = _norm_entity(celeb_name)
    if not base or len(base) < 3 or base in GENERIC_SUBFOLDERS:
        return []
    variants = [base]
    compact = _norm_entity(re.sub(r"([A-Za-z])['’]([A-Za-z])", r"\1\2", celeb_name or ''))
    if compact and compact not in variants:
        variants.append(compact)
    # Match "Stephen Smith" if vault folder is "Stephen A. Smith" (single-letter middle initial)
    tokens = base.split()
    if len(tokens) >= 3 and any(len(t) == 1 for t in tokens[1:-1]):
        no_mid = ' '.join(t for idx, t in enumerate(tokens) if not (0 < idx < len(tokens) - 1 and len(t) == 1))
        if no_mid and no_mid not in variants:
            variants.append(no_mid)
    # Match joined apostrophe fragments like "shaquille o neal" -> "shaquille oneal"
    for i in range(len(tokens) - 1):
        if len(tokens[i]) == 1 and len(tokens[i + 1]) >= 2:
            joined = ' '.join(tokens[:i] + [tokens[i] + tokens[i + 1]] + tokens[i + 2:])
            if joined and joined not in variants:
                variants.append(joined)
    for alias_key in list(variants):
        for alias in _NICKNAME_ALIASES.get(alias_key, []):
            norm_alias = _norm_entity(alias)
            if norm_alias and norm_alias not in variants:
                variants.append(norm_alias)
    return variants


def _named_visual_people(scene: dict, people: list[str] | None) -> list[str]:
    """Identify specific celebrity/person names explicitly targeted in this scene's visuals or query."""
    visual_raw = ' '.join([
        scene.get('image_query', ''),
        scene.get('visual_description', ''),
        scene.get('on_screen_text', ''),
    ])
    visual_norm = _norm_entity(visual_raw)
    visual_compact = _norm_entity(re.sub(r"([A-Za-z])['’]([A-Za-z])", r"\1\2", visual_raw))
    found: list[str] = []
    for p in (people or []):
        pn = _norm_entity(p)
        p_compact = _norm_entity(re.sub(r"([A-Za-z])['’]([A-Za-z])", r"\1\2", p or ''))
        if pn and (_has_phrase(visual_norm, pn) or (p_compact and _has_phrase(visual_compact, p_compact))):
            if pn not in found:
                found.append(pn)
    # Only harvest unknown capitalized two-word names from image_query and visual_description
    # (on_screen_text holds punchy headline banners like "Shumpert Clash" or "Basketball Commentary").
    query_and_desc = ' '.join([scene.get('image_query', ''), scene.get('visual_description', '')])
    for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\b', query_and_desc):
        pn = _norm_entity(m.group(1))
        words = pn.split()
        if (
            pn
            and pn not in _STOP_PROPER_PHRASES
            and not any(w in _NON_PERSON_WORDS for w in words)
            and pn not in found
        ):
            found.append(pn)
    return found


def match_celebrity_asset(
    db,
    workspace_id: str,
    scene: dict,
    folder: Path,
    draft_title: str = '',
    people: list[str] | None = None,
    existing: list[dict | None] | None = None,
    preference: str | None = None,
) -> dict | None:
    assets = db.query(CelebrityAsset).filter_by(workspace_id=workspace_id).all()
    if not assets:
        return None
    folder_row = db.get(CelebrityFolder, workspace_id)
    pref = preference or (folder_row.preference if folder_row else 'mix_both')
    existing = existing or []
    used_ids = {a.get('vault_asset_id') for a in existing if a and a.get('vault_asset_id')}
    used_hashes = {a.get('hash') for a in existing if a and a.get('hash')}
    used_celebrities = Counter(a.get('celebrity_name') for a in existing if a and a.get('celebrity_name'))

    visual_norm = _norm_entity(' '.join([
        scene.get('image_query', ''),
        scene.get('visual_description', ''),
        scene.get('on_screen_text', ''),
    ]))
    narration_norm = _norm_entity(scene.get('narration', ''))
    scene_norm = f'{visual_norm} {narration_norm}'.strip()
    scene_tokens = set(scene_norm.split())
    title_norm = _norm_entity(' '.join([draft_title] + list(people or [])))
    title_tokens = set(title_norm.split())
    domain_tokens = scene_tokens | title_tokens
    visual_people = _named_visual_people(scene, people)

    scene_num = int(scene.get('number') or 1)
    prefer_type = None
    if pref == 'prefer_clips':
        prefer_type = 'video'
    elif pref == 'prefer_images':
        prefer_type = 'image'
    elif pref == 'mix_both':
        prefer_type = 'video' if scene_num % 2 == 1 else 'image'

    vault_variants: dict[str, list[str]] = {}
    surname_owners: Counter[str] = Counter()
    celeb_surname: dict[str, str] = {}
    for a in assets:
        if a.celebrity_name not in vault_variants:
            vlist = _celebrity_variants(a.celebrity_name)
            vault_variants[a.celebrity_name] = vlist
            cn = _norm_entity(a.celebrity_name)
            if vlist and cn not in GENERIC_SUBFOLDERS and cn not in _GENERIC_BROLL_FOLDERS:
                tokens = cn.split()
                if len(tokens) >= 2 and len(tokens[-1]) >= 4 and tokens[-1] not in _NON_PERSON_WORDS:
                    celeb_surname[a.celebrity_name] = tokens[-1]
                    surname_owners[tokens[-1]] += 1
    unique_surnames = {
        celeb: sname for celeb, sname in celeb_surname.items() if surname_owners[sname] == 1
    }

    def _matches_visual_person(vp: str) -> bool:
        for celeb_name, vlist in vault_variants.items():
            if any(_has_phrase(vp, v) or _has_phrase(v, vp) or _names_close(vp, v) for v in vlist):
                return True
            sname = unique_surnames.get(celeb_name)
            if sname and len(vp.split()) == 1 and vp == sname:
                return True
        return False

    any_visual_person_in_vault = any(_matches_visual_person(vp) for vp in visual_people)
    # If the scene visually depicts a specific named celebrity who does not exist in the local folder,
    # return None so the Real Web Photo Fallback fetches genuine photos of THAT celebrity.
    if visual_people and not any_visual_person_in_vault:
        return None

    scored: list[tuple[float, str, CelebrityAsset]] = []
    for asset in assets:
        if not Path(asset.file_path).is_file():
            continue
        celeb_norm = _norm_entity(asset.celebrity_name)
        variants = vault_variants.get(asset.celebrity_name) or []
        if not variants or celeb_norm in GENERIC_SUBFOLDERS:
            continue
        is_broll = celeb_norm in _GENERIC_BROLL_FOLDERS
        if is_broll and visual_people:
            # Never hijack a named-person scene with generic "Basketball Highlights"
            continue

        score = 0.0
        celeb_words = [w for w in celeb_norm.split() if len(w) >= 3]
        sname = unique_surnames.get(asset.celebrity_name)
        if any(_has_phrase(visual_norm, v) for v in variants):
            score += 260.0
        elif not is_broll and any(_names_close(vp, v) for vp in visual_people for v in variants):
            score += 230.0
        elif sname and _has_phrase(visual_norm, sname) and (
            not visual_people or any(vp == sname or _has_phrase(vp, v) or _names_close(vp, v) for vp in visual_people for v in variants)
        ):
            score += 195.0
        elif any(_has_phrase(narration_norm, v) for v in variants):
            score += 165.0
        elif sname and _has_phrase(narration_norm, sname):
            score += 140.0
        elif not is_broll and len(celeb_words) >= 2 and sum(1 for w in celeb_words if w in scene_tokens) >= 2:
            score += 125.0
        elif is_broll and any(w in domain_tokens for w in celeb_words):
            score += 40.0
        elif not is_broll and not visual_people and (
            any(_has_phrase(title_norm, v) for v in variants)
            or (sname and _has_phrase(title_norm, sname))
        ):
            # Spread scenes across all story/title vault celebrities when a scene lacks a specific target.
            score += 65.0

        if score <= 0:
            continue

        moods = json.loads(asset.mood_tags or '[]')
        mood_hits = sum(1 for m in moods if m in scene_tokens)
        score += mood_hits * 20.0

        if not is_broll:
            prior_uses = used_celebrities.get(asset.celebrity_name, 0)
            if prior_uses == 0:
                score += 75.0
            else:
                score -= 35.0 * prior_uses

        if prefer_type and asset.media_type == prefer_type:
            score += 15.0
        if asset.id in used_ids or asset.content_hash in used_hashes:
            score -= 500.0

        # Deterministic rotation tie-breaker so multiple scenes featuring the same celebrity pick fresh clips
        tie = hashlib.md5(f'{scene_num}:{asset.id}'.encode()).hexdigest()
        scored.append((score, tie, asset))

    if not scored:
        return None
    scored.sort(key=lambda pair: (pair[0], pair[1]), reverse=True)
    if scored[0][0] <= 0:
        return None
    best = scored[0][2]
    return stage_vault_asset_for_draft(best, scene_num, folder)


def _is_ai_or_non_photo(title: str, url: str) -> bool:
    """Block AI-generated images, cartoons/vectors, AND paid/watermarked stock photos with labels."""
    combined = f'{title} {url}'.lower()
    return any(term in combined for term in AI_BLOCKLIST + WATERMARK_STOCK_BLOCKLIST)


def item_matches_celebrities(text: str, celebrities: list[str] | None) -> bool:
    """True when real image metadata (title/tags/url) clearly identifies one of the target celebrities."""
    if not celebrities:
        return True
    norm_text = _norm_entity(text or '')
    if not norm_text:
        return False
    text_tokens = set(norm_text.split())
    for celeb in celebrities:
        for variant in _celebrity_variants(celeb):
            if _has_phrase(norm_text, variant):
                return True
            words = [w for w in variant.split() if len(w) >= 3]
            if len(words) >= 2 and all(w in text_tokens for w in words):
                return True
    return False


def search_web_real_photo(
    scene: dict,
    folder: Path,
    used: set[str] | None = None,
    target_celebrities: list[str] | None = None,
) -> dict | None:
    """Real web photo fallback via DuckDuckGo Image Search (celebrity-locked & filters watermarked stock/AI art)."""
    used = used or set()
    targets = [c.strip() for c in (target_celebrities or []) if c and c.strip()]
    query = (scene.get('image_query') or scene.get('visual_description') or '').strip()
    if not query and not targets:
        return None
    scene_num = int(scene.get('number') or 1)
    neg = '-getty -alamy -shutterstock -istock -dreamstime -depositphotos -123rf -watermark'
    if targets:
        # Query per celebrity discussed so we only surface real clean photographs of them.
        queries = [(celeb, f'{celeb} press conference photo {neg}') for celeb in targets]
    else:
        compact_q = re.sub(r'\s+', ' ', query)[:120]
        queries = [(None, f'{compact_q} real photo {neg}')]

    for active_celeb, clean_q in queries:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.images(clean_q, max_results=12, type_image='photo', safesearch='moderate'))
        except Exception:
            continue

        match_scope = [active_celeb] if active_celeb else []
        for item in results:
            img_url = item.get('image') or ''
            src_url = item.get('url') or img_url
            title = item.get('title') or ''
            src_name = item.get('source') or ''
            if not img_url.startswith('http') or _is_ai_or_non_photo(f'{title} {src_name}', f'{img_url} {src_url}'):
                continue
            if match_scope and not item_matches_celebrities(f'{title} {src_url} {img_url}', match_scope):
                continue
            try:
                resp = httpx.get(
                    img_url,
                    headers={'User-Agent': BROWSER_USER_AGENT, 'Accept': 'image/*'},
                    timeout=12,
                    follow_redirects=True,
                    trust_env=False,
                )
                if resp.status_code != 200 or len(resp.content) < 5000:
                    continue
                with Image.open(io.BytesIO(resp.content)) as src_img:
                    src_img.load()
                    if src_img.width < 300 or src_img.height < 250:
                        continue
                    img = ImageOps.exif_transpose(src_img).convert('RGB')
                out_id = uuid4().hex[:12]
                out_path = folder / f'web_{scene_num}_{out_id}.jpg'
                img.save(out_path, 'JPEG', quality=94)
                digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
                if digest in used:
                    out_path.unlink(missing_ok=True)
                    continue
                return {
                    'path': str(out_path),
                    'hash': digest,
                    'source_url': src_url,
                    'creator': item.get('source') or 'Web Photograph',
                    'license': 'Editorial Web Photograph',
                    'license_url': src_url,
                    'credit': f'Photo via Web Search: {title[:80]}',
                    'kind': 'real_web_photo',
                    'media_type': 'image',
                    'provider': 'duckduckgo_photo',
                    **({'celebrity_name': active_celeb} if active_celeb else {}),
                    'note': 'Real photograph retrieved from web search fallback.',
                }
            except Exception:
                continue
    return None
