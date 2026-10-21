from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Iterator

STATE_DIR = ".photo-sorter"

PHOTO_EXTS = frozenset({
    ".jpg", ".jpeg", ".heic", ".heif", ".png", ".webp", ".gif", ".tif", ".tiff", ".bmp",
    ".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf", ".srw", ".pef",
})
VIDEO_EXTS = frozenset({
    ".mov", ".mp4", ".m4v", ".3gp", ".avi", ".mkv", ".mts", ".m2ts", ".wmv", ".mpg", ".mpeg",
})
SIDECAR_EXTS = frozenset({".aae", ".xmp", ".thm"})
MEDIA_EXTS = PHOTO_EXTS | VIDEO_EXTS

EXT_ALIASES = {".jpeg": ".jpg", ".tiff": ".tif"}


@dataclass(eq=False)
class MediaFile:
    rel: str
    path: Path
    size: int
    kind: str
    hash: str = ""
    taken_at: datetime | None = None
    date_source: str = ""
    lat: float | None = None
    lon: float | None = None
    city: str | None = None
    country: str | None = None
    content_id: str | None = None
    width: int | None = None
    height: int | None = None
    screenshot: str = ""
    companions: list[MediaFile] = field(default_factory=list)

    @property
    def ext(self) -> str:
        return PurePosixPath(self.rel).suffix.lower()


def kind_of(path: Path | PurePosixPath) -> str | None:
    ext = path.suffix.lower()
    if ext in PHOTO_EXTS:
        return "photo"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in SIDECAR_EXTS:
        return "sidecar"
    return None


def normalized_ext(ext: str) -> str:
    ext = ext.lower()
    return EXT_ALIASES.get(ext, ext)


def walk_files(root: Path) -> Iterator[Path]:
    """Yield regular files under root, skipping hidden entries and NAS thumbnail folders."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "@eaDir", "#recycle")))
        for name in sorted(filenames):
            if name.startswith(".") or name.lower() in ("thumbs.db", "desktop.ini"):
                continue
            path = Path(dirpath, name)
            if path.is_file() and not path.is_symlink():
                yield path
