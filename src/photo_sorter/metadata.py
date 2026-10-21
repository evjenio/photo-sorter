import json
import re
import subprocess
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .media import MediaFile
from .progress import Log, track
from .screenshots import screenshot_reason

MetadataReader = Callable[[list[Path], Log], dict[str, dict[str, Any]]]

DATE_TAGS = ("DateTimeOriginal", "CreationDate", "CreateDate", "MediaCreateDate")
TAGS = (
    *DATE_TAGS,
    "Composite:GPSLatitude",
    "Composite:GPSLongitude",
    "GeolocationCity",
    "GeolocationCountry",
    "ContentIdentifier",
    "ImageWidth",
    "ImageHeight",
    "UserComment",
    "Make",
    "Model",
)

EXIF_DATE = re.compile(r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")
FILENAME_DATE = re.compile(
    r"(?<!\d)((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"
    r"(?:[-_ T.]?([01]\d|2[0-3])[-_.:h]?([0-5]\d)[-_.:m]?([0-5]\d)|(?!\d))"
)
MIN_YEAR = 1980
TRANSLITERATION_MARKS = str.maketrans("", "", "’‘ʼ")


def read_exif(paths: list[Path], log: Log, batch_size: int = 500) -> dict[str, dict[str, Any]]:
    """Read tags with exiftool; city districts resolve to their city, QuickTime dates to the container's TZ."""
    result: dict[str, dict[str, Any]] = {}
    args = ["exiftool", "-j", "-n", "-q", "-q", "-api", "geolocation", "-api", "GeolocFeature=-PPLX", "-api", "QuickTimeUTC",
            "-charset", "filename=utf8", *(f"-{tag}" for tag in TAGS), "-@", "-"]
    batches = [paths[start:start + batch_size] for start in range(0, len(paths), batch_size)]
    for batch in track(batches, len(paths), "reading metadata", log, weight=len):
        proc = subprocess.run(args, input="\n".join(map(str, batch)), capture_output=True, text=True)
        if proc.stdout.strip():
            for item in json.loads(proc.stdout):
                result[item["SourceFile"]] = item
    return result


def _valid(dt: datetime) -> datetime | None:
    return dt if MIN_YEAR <= dt.year <= datetime.now().year + 1 else None


def parse_exif_date(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    match = EXIF_DATE.match(value.strip())
    if not match:
        return None
    try:
        return _valid(datetime(*map(int, match.groups())))
    except ValueError:
        return None


def parse_filename_date(name: str) -> datetime | None:
    for match in FILENAME_DATE.finditer(PurePosixPath(name).stem):
        parts = [int(g) for g in match.groups() if g is not None]
        try:
            dt = _valid(datetime(*parts))
        except ValueError:
            continue
        if dt:
            return dt
    return None


def resolve_date(exif: dict[str, Any], filename: str) -> tuple[datetime | None, str]:
    for tag in DATE_TAGS:
        if dt := parse_exif_date(exif.get(tag)):
            return dt, tag
    if dt := parse_filename_date(filename):
        return dt, "filename"
    return None, ""


def _text(value: Any) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


def _place(value: Any) -> str | None:
    text = _text(value)
    return text.translate(TRANSLITERATION_MARKS) if text else None


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def apply_metadata(media: MediaFile, exif: dict[str, Any]) -> None:
    media.taken_at, media.date_source = resolve_date(exif, media.path.name)
    lat, lon = exif.get("GPSLatitude"), exif.get("GPSLongitude")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and (lat, lon) != (0, 0):
        media.lat, media.lon = float(lat), float(lon)
        media.city = _place(exif.get("GeolocationCity"))
        media.country = _place(exif.get("GeolocationCountry"))
    media.content_id = _text(exif.get("ContentIdentifier"))
    media.width = _int(exif.get("ImageWidth"))
    media.height = _int(exif.get("ImageHeight"))
    media.screenshot = screenshot_reason(media, exif)
