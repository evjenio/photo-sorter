import re
from pathlib import PurePosixPath
from typing import Any

from .media import MediaFile

SCREENSHOT_NAME = re.compile(
    r"^(screenshot|screen[ _-]?shot|screencap(ture)?|снимок экрана|скриншот|bildschirmfoto|capture d.[ée]cran)",
    re.IGNORECASE,
)
RECORDING_NAME = re.compile(
    r"^(screen[ _-]?recording|screenrecorder|screen[ _-]?record|rpreplay|запись экрана|запись_экрана)",
    re.IGNORECASE,
)
SCREEN_SIZES = frozenset({
    (640, 1136), (750, 1334), (828, 1792), (1080, 1920), (1125, 2436), (1170, 2532), (1179, 2556),
    (1206, 2622), (1242, 2208), (1242, 2688), (1284, 2778), (1290, 2796), (1320, 2868),
    (720, 1280), (720, 1520), (720, 1600), (1080, 2160), (1080, 2220), (1080, 2280), (1080, 2340),
    (1080, 2400), (1080, 2408), (1080, 2412), (1220, 2712), (1440, 2560), (1440, 2960), (1440, 3040),
    (1440, 3088), (1440, 3120), (1440, 3200),
    (1536, 2048), (1488, 2266), (1620, 2160), (1640, 2360), (1668, 2224), (1668, 2388), (2048, 2732),
    (768, 1366), (800, 1280), (864, 1536), (900, 1440), (900, 1600), (1050, 1680),
    (1200, 1920), (1600, 2560), (1664, 2560), (1800, 2880), (1912, 2940),
    (1920, 3072), (1964, 3024), (2160, 3840), (2234, 3456),
})


def screenshot_reason(media: MediaFile, exif: dict[str, Any]) -> str:
    """Why the file looks captured from a screen, or an empty string for camera media."""
    name = PurePosixPath(media.rel).name
    if media.kind == "video":
        return "filename" if RECORDING_NAME.match(name) else ""
    if media.kind != "photo":
        return ""
    if SCREENSHOT_NAME.match(name):
        return "filename"
    if str(exif.get("UserComment", "")).strip().lower() == "screenshot":
        return "metadata"
    if (
        media.ext == ".png"
        and not exif.get("Make")
        and not exif.get("Model")
        and media.lat is None
        and media.width
        and media.height
        and tuple(sorted((media.width, media.height))) in SCREEN_SIZES
    ):
        return "screen size"
    return ""
