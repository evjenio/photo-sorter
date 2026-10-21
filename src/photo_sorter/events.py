import posixpath
import re
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import datetime, timedelta

from .media import MediaFile

UNSORTED_DIR = "_unsorted"
SCREENSHOTS_DIR = "screenshots"
MAX_TITLE_CITIES = 3
UNSAFE_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def cluster_events(items: list[MediaFile], gap: timedelta, max_span: timedelta) -> list[list[MediaFile]]:
    """Split time-sorted items on long pauses, country changes and overly long spans."""
    clusters: list[list[MediaFile]] = []
    current: list[MediaFile] = []
    country: str | None = None
    for item in items:
        if current and (
            item.taken_at - current[-1].taken_at > gap
            or item.taken_at - current[0].taken_at > max_span
            or (country and item.country and item.country != country)
        ):
            clusters.append(current)
            current, country = [], None
        current.append(item)
        country = item.country or country
    if current:
        clusters.append(current)
    return clusters


def sanitize(name: str) -> str:
    return UNSAFE_CHARS.sub("-", name).strip().rstrip(".")


def event_title(items: list[MediaFile]) -> str:
    day = f"{items[0].taken_at:%d}"
    cities = Counter(i.city for i in items if i.city)
    countries = Counter(i.country for i in items if i.country)
    country = countries.most_common(1)[0][0] if countries else None
    if not cities:
        return f"{day} {country}" if country else day
    top = {city for city, _ in cities.most_common(MAX_TITLE_CITIES)}
    ordered = list(dict.fromkeys(i.city for i in items if i.city in top))
    if len(ordered) == 1:
        return f"{day} {ordered[0]}"
    places = ", ".join(ordered)
    return f"{day} {country} - {places}" if country else f"{day} {places}"


def event_folder(items: list[MediaFile]) -> str:
    return f"{items[0].taken_at:%Y/%Y-%m}/{sanitize(event_title(items))}"


class ExistingEvents:
    """Finds a destination folder that already holds photos from the same time window."""

    def __init__(self, entries: list[tuple[datetime, str]], gap: timedelta):
        located = sorted(
            (taken_at, posixpath.dirname(rel))
            for taken_at, rel in entries
            if posixpath.dirname(rel) and not rel.startswith((f"{UNSORTED_DIR}/", f"{SCREENSHOTS_DIR}/"))
        )
        self._times = [t for t, _ in located]
        self._folders = [f for _, f in located]
        self._gap = gap

    def folder_for(self, cluster: list[MediaFile]) -> str | None:
        lo = bisect_left(self._times, cluster[0].taken_at - self._gap)
        hi = bisect_right(self._times, cluster[-1].taken_at + self._gap)
        if lo == hi:
            return None
        return Counter(self._folders[lo:hi]).most_common(1)[0][0]
