"""Connected Local Celebrity Folder scanner, scene-aware matcher, and real web photo fallback."""
import hashlib
import io
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image, ImageOps

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


def _norm_entity(text: str) -> str:
    """Normalize names and queries so 'Stephen A. Smith' and 'Stephen A Smith' match cleanly."""
    t = (text or '').replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
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


def _iter_media_files(root: Path):
    """Fast os.walk scanner supporting large nested directories."""
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in ALLOWED_EXTS:
                yield Path(dirpath) / fname, ext


def scan_celebrity_folder(db, workspace_id: str, folder_path: str, preference: str = 'mix_both') -> dict:
    root = Path(folder_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f'Directory not found: {root}')

    # Scan the entire directory tree completely BEFORE starting any SQLite write transaction!
    # This avoids holding a DB write lock during disk I/O and indexes thousands of videos in < 1s.
    now = datetime.now(timezone.utc)
    records: list[CelebrityAsset] = []
    celeb_names: set[str] = set()

    for path, ext in sorted(_iter_media_files(root), key=lambda pair: str(pair[0])):
        try:
            st = path.stat()
        except OSError:
            continue
        media_type = 'video' if ext in VIDEO_EXTS else 'image'
        celeb_name, moods = _parse_celebrity_and_mood(root, path)
        celeb_names.add(celeb_name)
        records.append(
            CelebrityAsset(
                id=new_id(),
                workspace_id=workspace_id,
                celebrity_name=celeb_name,
                mood_tags=json.dumps(moods),
                media_type=media_type,
                file_name=path.name,
                file_path=str(path),
                ext=ext,
                duration=None,
                content_hash=_fast_fingerprint(path, st),
                created_at=now,
            )
        )

    folder_row = db.get(CelebrityFolder, workspace_id)
    if folder_row:
        folder_row.folder_path = str(root)
        folder_row.preference = preference or folder_row.preference
    else:
        folder_row = CelebrityFolder(workspace_id=workspace_id, folder_path=str(root), preference=preference or 'mix_both')
        db.add(folder_row)

    db.query(CelebrityAsset).filter_by(workspace_id=workspace_id).delete(synchronize_session=False)
    if records:
        db.bulk_save_objects(records)
    db.commit()
    return {
        'workspace_id': workspace_id,
        'folder_path': str(root),
        'preference': folder_row.preference,
        'total_assets': len(records),
        'celebrities': sorted(celeb_names),
    }


def list_celebrity_library(db, workspace_id: str, limit_per_celebrity: int = 12) -> dict:
    folder_row = db.get(CelebrityFolder, workspace_id)
    rows = (
        db.query(CelebrityAsset)
        .filter_by(workspace_id=workspace_id)
        .order_by(CelebrityAsset.celebrity_name, CelebrityAsset.file_name)
        .all()
    )
    grouped: dict[str, dict] = {}
    for row in rows:
        entry = grouped.setdefault(row.celebrity_name, {
            'celebrity_name': row.celebrity_name,
            'image_count': 0,
            'video_count': 0,
            'assets': [],
        })
        if row.media_type == 'video':
            entry['video_count'] += 1
        else:
            entry['image_count'] += 1
        if limit_per_celebrity <= 0 or len(entry['assets']) < limit_per_celebrity:
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
        'total_assets': len(rows),
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


def _celebrity_variants(celeb_name: str) -> list[str]:
    base = _norm_entity(celeb_name)
    if not base or len(base) < 3 or base in GENERIC_SUBFOLDERS:
        return []
    variants = [base]
    # Also match "Stephen Smith" if vault folder is "Stephen A. Smith" (single-letter middle initial)
    tokens = base.split()
    if len(tokens) >= 3 and any(len(t) == 1 for t in tokens[1:-1]):
        no_mid = ' '.join(t for idx, t in enumerate(tokens) if not (0 < idx < len(tokens) - 1 and len(t) == 1))
        if no_mid and no_mid not in variants:
            variants.append(no_mid)
    return variants


def _named_visual_people(scene: dict, people: list[str] | None) -> list[str]:
    """Identify specific celebrity/person names explicitly targeted in this scene's visuals or query."""
    visual_raw = ' '.join([
        scene.get('image_query', ''),
        scene.get('visual_description', ''),
        scene.get('on_screen_text', ''),
    ])
    visual_norm = _norm_entity(visual_raw)
    found: list[str] = []
    for p in (people or []):
        pn = _norm_entity(p)
        if pn and _has_phrase(visual_norm, pn):
            found.append(pn)
    for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\b', visual_raw):
        pn = _norm_entity(m.group(1))
        if pn and pn not in _STOP_PROPER_PHRASES and pn not in found:
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

    visual_norm = _norm_entity(' '.join([
        scene.get('image_query', ''),
        scene.get('visual_description', ''),
        scene.get('on_screen_text', ''),
    ]))
    narration_norm = _norm_entity(scene.get('narration', ''))
    scene_norm = f'{visual_norm} {narration_norm}'.strip()
    scene_tokens = set(scene_norm.split())
    title_norm = _norm_entity(' '.join([draft_title] + list(people or [])))
    visual_people = _named_visual_people(scene, people)

    scene_num = int(scene.get('number') or 1)
    prefer_type = None
    if pref == 'prefer_clips':
        prefer_type = 'video'
    elif pref == 'prefer_images':
        prefer_type = 'image'
    elif pref == 'mix_both':
        prefer_type = 'video' if scene_num % 2 == 1 else 'image'

    vault_variants = {}
    for a in assets:
        if a.celebrity_name not in vault_variants:
            vault_variants[a.celebrity_name] = _celebrity_variants(a.celebrity_name)

    any_visual_person_in_vault = any(
        any(_has_phrase(vp, v) or _has_phrase(v, vp) for vlist in vault_variants.values() for v in vlist)
        for vp in visual_people
    )
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
        if any(_has_phrase(visual_norm, v) for v in variants):
            score += 250.0
        elif any(_has_phrase(narration_norm, v) for v in variants):
            score += 160.0
        elif not is_broll and len(celeb_words) >= 2 and sum(1 for w in celeb_words if w in scene_tokens) >= 2:
            score += 120.0
        elif is_broll and any(w in scene_tokens for w in celeb_words):
            score += 25.0
        elif not is_broll and not visual_people and any(_has_phrase(title_norm, v) for v in variants):
            # Only fall back to a title celebrity if the scene itself has no missing visual subject.
            score += 30.0

        if score <= 0:
            continue

        moods = json.loads(asset.mood_tags or '[]')
        mood_hits = sum(1 for m in moods if m in scene_tokens)
        score += mood_hits * 20.0

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
    combined = f'{title} {url}'.lower()
    return any(term in combined for term in AI_BLOCKLIST)


def search_web_real_photo(scene: dict, folder: Path, used: set[str] | None = None) -> dict | None:
    """Real web photo fallback via DuckDuckGo Image Search (filters out AI art/illustrations)."""
    used = used or set()
    query = (scene.get('image_query') or scene.get('visual_description') or '').strip()
    if not query:
        return None
    clean_q = re.sub(r'\s+', ' ', query)[:140] + ' real photo'
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(clean_q, max_results=12, type_image='photo', safesearch='moderate'))
    except Exception:
        return None

    scene_num = int(scene.get('number') or 1)
    for item in results:
        img_url = item.get('image') or ''
        src_url = item.get('url') or img_url
        title = item.get('title') or ''
        if not img_url.startswith('http') or _is_ai_or_non_photo(title, img_url + ' ' + src_url):
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
                'note': 'Real photograph retrieved from web search fallback.',
            }
        except Exception:
            continue
    return None
