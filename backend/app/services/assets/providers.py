"""Only explicitly licensed local assets are accepted; no arbitrary URL downloads."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from PIL import Image
from app.services.assets.demo import create_demo_slides

@dataclass
class SafeAsset:
    local_path: Path
    source: str
    license: str
    attribution: str
    url: str | None = None
    creator: str | None = None
    download_url: str | None = None
    scene_number: int | None = None
    provenance: dict = field(default_factory=dict)

class AssetProvider(Protocol):
    def collect(self, topic, personality, script, output_dir) -> list[SafeAsset]: ...

class DemoAssetProvider:
    def collect(self, topic, personality, script, output_dir):
        return [SafeAsset(p, 'Original local illustration', 'Original generated demo graphic',
                          'Created locally by AI Shorts Platform')
                for p in create_demo_slides(topic, personality, script, output_dir)]

def validate_local_image(path: Path, allowed_root: Path):
    path = path.resolve()
    if allowed_root.resolve() not in path.parents or path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
        raise ValueError('Only safe local image paths are allowed')
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('Image exceeds 20 MB')
    with Image.open(path) as image:
        image.verify()
    return path

class LicensedSourceAdapter:
    def collect(self, *args, **kwargs):
        raise NotImplementedError('Configure a licensed image source before enabling this adapter')
