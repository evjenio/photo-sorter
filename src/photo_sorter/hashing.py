import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .progress import Log, track

CHUNK_SIZE = 1 << 20


def file_hash(path: Path) -> str:
    digest = hashlib.blake2b(digest_size=20)
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_hash(path: Path) -> str:
    try:
        return file_hash(path)
    except OSError:
        return ""


def hash_files(paths: list[Path], workers: int, log: Log) -> dict[Path, str]:
    """Hash files in parallel; unreadable files map to an empty string."""
    with ThreadPoolExecutor(workers) as pool:
        hashes = list(track(pool.map(_safe_hash, paths), len(paths), "hashing", log))
    return dict(zip(paths, hashes))
