from datetime import datetime

import pytest

from photo_sorter.metadata import parse_exif_date, parse_filename_date, resolve_date


@pytest.mark.parametrize("name, expected", [
    ("IMG_20230512_143012.jpg", datetime(2023, 5, 12, 14, 30, 12)),
    ("IMG-20230512-WA0003.jpg", datetime(2023, 5, 12)),
    ("PXL_20230512_143012345.jpg", datetime(2023, 5, 12, 14, 30, 12)),
    ("Screenshot_2023-05-12-14-30-12.png", datetime(2023, 5, 12, 14, 30, 12)),
    ("photo_2023-05-12_14-30-12.jpg", datetime(2023, 5, 12, 14, 30, 12)),
    ("2023-05-12 14.30.12.jpg", datetime(2023, 5, 12, 14, 30, 12)),
    ("VID_20230512_1430.mp4", datetime(2023, 5, 12)),
    ("IMG_1234.JPG", None),
    ("DSC_20001.jpg", None),
    ("scan_20231345.jpg", None),
    ("1234567890123.jpg", None),
])
def test_parse_filename_date(name, expected):
    assert parse_filename_date(name) == expected


@pytest.mark.parametrize("value, expected", [
    ("2024:07:12 14:30:12", datetime(2024, 7, 12, 14, 30, 12)),
    ("2024:07:12 14:30:12.123+04:00", datetime(2024, 7, 12, 14, 30, 12)),
    ("0000:00:00 00:00:00", None),
    ("1970:01:01 00:00:00", None),
    ("garbage", None),
    (None, None),
])
def test_parse_exif_date(value, expected):
    assert parse_exif_date(value) == expected


def test_resolve_date_prefers_exif_then_filename():
    exif = {"CreateDate": "2024:07:12 10:00:00", "DateTimeOriginal": "2024:07:12 09:00:00"}
    assert resolve_date(exif, "IMG_20200101_000000.jpg") == (datetime(2024, 7, 12, 9), "DateTimeOriginal")
    assert resolve_date({}, "IMG_20200101_000000.jpg") == (datetime(2020, 1, 1), "filename")
    assert resolve_date({}, "IMG_0001.jpg") == (None, "")
