from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
from pathlib import Path

import imagehash
import pillow_heif
from PIL import Image, ImageOps

from .progress import Log, track

pillow_heif.register_heif_opener()

PHASH_EXTS = frozenset({".jpg", ".jpeg", ".heic", ".heif", ".png", ".webp", ".tif", ".tiff", ".gif", ".bmp"})
HASH_BYTES = 8
MAX_DISTANCE = HASH_BYTES - 1


def perceptual_hash(path: Path) -> int | None:
    try:
        with Image.open(path) as image:
            image.draft("RGB", (512, 512))
            return int(str(imagehash.phash(ImageOps.exif_transpose(image))), 16)
    except Exception:
        return None


def phash_files(paths: list[Path], workers: int, log: Log) -> dict[Path, int | None]:
    with ProcessPoolExecutor(workers) as pool:
        hashes = list(track(pool.map(perceptual_hash, paths, chunksize=16), len(paths), "comparing images", log))
    return dict(zip(paths, hashes))


def group_similar(hashes: dict[str, int], max_distance: int) -> list[list[str]]:
    """Group keys within max_distance bits; hashes that close always share a byte, so only bucket mates are compared."""
    if not 0 <= max_distance <= MAX_DISTANCE:
        raise ValueError(f"max_distance must be between 0 and {MAX_DISTANCE}")
    buckets: dict[tuple[int, int], list[str]] = defaultdict(list)
    for key, value in hashes.items():
        for i in range(HASH_BYTES):
            buckets[(i, (value >> (8 * i)) & 0xFF)].append(key)

    parent = {key: key for key in hashes}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for bucket in buckets.values():
        for a, b in combinations(bucket, 2):
            if (hashes[a] ^ hashes[b]).bit_count() <= max_distance:
                parent[find(a)] = find(b)

    groups: dict[str, list[str]] = defaultdict(list)
    for key in hashes:
        groups[find(key)].append(key)
    return [sorted(g) for g in groups.values() if len(g) > 1]
