from datetime import datetime

import pytest

from conftest import media
from photo_sorter.screenshots import screenshot_reason

T = datetime(2024, 7, 12, 15)


def png(rel, width=None, height=None, lat=None):
    file = media(rel, T)
    file.width, file.height, file.lat = width, height, lat
    return file


@pytest.mark.parametrize("rel", [
    "Screenshot_20240712-150000.png",
    "Screenshot_20240712-150000_Telegram.jpg",
    "Screen Shot 2024-07-12 at 15.00.00.png",
    "Снимок экрана 2024-07-12 в 15.00.00.png",
    "Скриншот 12-07-2024 150000.jpg",
    "Screenshot (12).png",
])
def test_screenshot_by_filename(rel):
    assert screenshot_reason(png(rel), {}) == "filename"


def test_ios_screenshot_by_user_comment():
    assert screenshot_reason(png("IMG_0500.PNG"), {"UserComment": "Screenshot"}) == "metadata"


def test_png_with_screen_resolution_and_no_camera():
    assert screenshot_reason(png("IMG_0501.PNG", 2556, 1179), {}) == "screen size"


@pytest.mark.parametrize("file, exif", [
    (png("IMG_0502.PNG", 1179, 2556), {"Make": "Apple", "Model": "iPhone 15"}),
    (png("IMG_0503.PNG", 1179, 2556, lat=41.7), {}),
    (png("export.png", 1000, 1000), {}),
    (png("IMG_0504.JPG", 1179, 2556), {}),
    (png("IMG_0505.PNG"), {}),
])
def test_camera_and_ordinary_images_are_not_screenshots(file, exif):
    assert screenshot_reason(file, exif) == ""


@pytest.mark.parametrize("rel, expected", [
    ("RPReplay_Final1690000000.MP4", "filename"),
    ("ScreenRecording_07-12-2024 15-00-00_1.MP4", "filename"),
    ("Screen Recording 2024-07-12 at 15.00.00.mov", "filename"),
    ("Запись экрана 2024-07-12 в 15.00.00.mov", "filename"),
    ("IMG_0001.MOV", ""),
])
def test_screen_recordings_by_filename(rel, expected):
    assert screenshot_reason(media(rel, T), {}) == expected
