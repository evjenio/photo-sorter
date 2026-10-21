from datetime import datetime
from pathlib import Path

from photo_sorter.media import MediaFile, kind_of


def media(rel: str, taken_at: datetime | None = None, *, city: str | None = None, country: str | None = None,
          content_id: str | None = None) -> MediaFile:
    return MediaFile(rel, Path("/source", rel), 1, kind_of(Path(rel)), taken_at=taken_at,
                     city=city, country=country, content_id=content_id)
