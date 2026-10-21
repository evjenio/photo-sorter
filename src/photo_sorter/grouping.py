import posixpath
from collections import defaultdict
from datetime import timedelta
from pathlib import PurePosixPath

from .media import MEDIA_EXTS, MediaFile

COMPANION_MAX_SKEW = timedelta(seconds=5)
PREFERRED_PRIMARY_EXTS = frozenset({".heic", ".heif", ".jpg", ".jpeg"})


def _group_key(file: MediaFile) -> tuple[str, str]:
    parent, name = posixpath.split(file.rel)
    stem = PurePosixPath(name).stem
    if file.kind == "sidecar" and PurePosixPath(stem).suffix.lower() in MEDIA_EXTS:
        stem = PurePosixPath(stem).stem
    return parent.lower(), stem.lower()


def _primary_rank(file: MediaFile) -> tuple[int, str]:
    if file.ext in PREFERRED_PRIMARY_EXTS:
        return 0, file.rel
    return (1 if file.kind == "photo" else 2), file.rel


def _is_companion(primary: MediaFile, other: MediaFile) -> bool:
    if other.ext == primary.ext or any(c.ext == other.ext for c in primary.companions):
        return False
    if primary.content_id and other.content_id:
        return primary.content_id == other.content_id
    if primary.taken_at and other.taken_at:
        return abs(primary.taken_at - other.taken_at) <= COMPANION_MAX_SKEW
    return False


def attach_companions(files: list[MediaFile]) -> tuple[list[MediaFile], list[MediaFile]]:
    """Bind Live Photo videos, RAW+JPEG pairs and sidecars to a primary; returns (primaries, orphan sidecars)."""
    groups: dict[tuple[str, str], list[MediaFile]] = defaultdict(list)
    for file in files:
        groups[_group_key(file)].append(file)

    primaries: list[MediaFile] = []
    orphans: list[MediaFile] = []
    for group in groups.values():
        pending = sorted((f for f in group if f.kind != "sidecar"), key=_primary_rank)
        sidecars = [f for f in group if f.kind == "sidecar"]
        group_primaries: list[MediaFile] = []
        while pending:
            primary = pending.pop(0)
            rest = []
            for other in pending:
                if _is_companion(primary, other):
                    primary.companions.append(other)
                else:
                    rest.append(other)
            pending = rest
            group_primaries.append(primary)
        if sidecars and group_primaries:
            group_primaries[0].companions.extend(sidecars)
        else:
            orphans.extend(sidecars)
        primaries.extend(group_primaries)
    return primaries, orphans


def companion_suffix(primary: MediaFile, companion: MediaFile) -> str:
    """Suffix that keeps a companion next to its primary, e.g. `.mov` or `.jpg.xmp`."""
    stem = PurePosixPath(primary.rel).stem
    name = PurePosixPath(companion.rel).name
    if name.lower().startswith(stem.lower()):
        return name[len(stem):].lower()
    return PurePosixPath(name).suffix.lower()
