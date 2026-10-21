import shutil

import pytest
from PIL import Image

from photo_sorter.metadata import read_exif

pytestmark = pytest.mark.skipif(not shutil.which("exiftool"), reason="exiftool is not installed")


def _dms(value):
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = round(((value - degrees) * 60 - minutes) * 60, 2)
    return degrees, minutes, seconds


def test_reads_date_and_reverse_geocodes_city(tmp_path):
    path = tmp_path / "photo.jpg"
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0x9003] = "2024:07:12 10:00:00"
    exif.get_ifd(0x8825).update({1: "N", 2: _dms(41.7151), 3: "E", 4: _dms(44.8271)})
    Image.new("RGB", (32, 32)).save(path, exif=exif)

    tags = read_exif([path], lambda _: None)[str(path)]

    assert tags["DateTimeOriginal"] == "2024:07:12 10:00:00"
    assert tags["GPSLatitude"] == pytest.approx(41.7151, abs=1e-3)
    assert tags["GeolocationCity"] == "Tbilisi"
    assert tags["GeolocationCountry"] == "Georgia"


def test_reports_progress_per_batch(tmp_path):
    paths = []
    for i in range(3):
        path = tmp_path / f"{i}.jpg"
        Image.new("RGB", (8, 8)).save(path)
        paths.append(path)
    messages = []

    read_exif(paths, messages.append, batch_size=2)

    assert messages[-1] == "  reading metadata: 3/3"
