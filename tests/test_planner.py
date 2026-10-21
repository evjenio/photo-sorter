from pathlib import Path

import pytest

from photo_sorter.applier import apply_plan
from photo_sorter.index import DestIndex
from photo_sorter.planner import PlanOptions, build_plan, read_plan, write_plan

TBILISI = {"GPSLatitude": 41.7151, "GPSLongitude": 44.8271, "GeolocationCity": "Tbilisi", "GeolocationCountry": "Georgia"}
KAZBEGI = {"GPSLatitude": 42.6569, "GPSLongitude": 44.6433, "GeolocationCity": "Stepantsminda", "GeolocationCountry": "Georgia"}

EXIF = {
    "trip/IMG_0001.HEIC": {"DateTimeOriginal": "2024:07:12 10:00:00", "ContentIdentifier": "L1", **TBILISI},
    "trip/IMG_0001.MOV": {"CreationDate": "2024:07:12 10:00:01+04:00", "ContentIdentifier": "L1"},
    "trip/IMG_0002.JPG": {"DateTimeOriginal": "2024:07:13 09:00:00", **KAZBEGI},
    "copies/IMG_0001 (1).HEIC": {"DateTimeOriginal": "2024:07:12 10:00:00", "ContentIdentifier": "L1", **TBILISI},
    "whatsapp/IMG-20240801-WA0001.jpg": {},
    "whatsapp/IMG-20240801-WA0002.jpg": {},
    "misc/random.jpg": {},
    "misc/old.jpg": {"DateTimeOriginal": "2020:01:01 12:00:00"},
    "phone/Screenshot_20240712-150000.png": {},
    "phone/IMG_0500.PNG": {"DateTimeOriginal": "2024:07:12 16:00:00", "UserComment": "Screenshot"},
    "phone/RPReplay_Final1690000000.MP4": {"CreationDate": "2024:07:12 17:00:00+04:00"},
    "phone/Screenshot (12).png": {},
}


def write(root: Path, rel: str, content: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


@pytest.fixture
def library(tmp_path):
    source, dest = tmp_path / "source", tmp_path / "dest"
    for rel in EXIF:
        write(source, rel, rel.encode())
    write(source, "copies/IMG_0001 (1).HEIC", b"trip/IMG_0001.HEIC")
    write(source, "trip/IMG_0001.AAE", b"edit")
    write(source, "trip/notes.txt", b"hello")
    write(source, "whatsapp/IMG-20240801-WA0002.jpg", b"same picture again")
    write(source, "misc/old.jpg", b"already sorted")
    write(dest, "2020/2020-01-01/2020-01-01_12-00-00.jpg", b"already sorted")
    return source, dest


def fake_reader(source: Path):
    def read(paths, log):
        return {str(p): EXIF.get(p.relative_to(source).as_posix(), {}) for p in paths if p.is_relative_to(source)}
    return read


def make_plan(source, dest):
    index = DestIndex(dest)
    reader = fake_reader(source)
    index.refresh(reader, 2, False, lambda _: None)
    plan = build_plan(source, dest, index, PlanOptions(similar=False, workers=2), reader, lambda _: None)
    return plan, index


def by_source(plan):
    return {row.source: row for row in plan.rows}


def test_plan_places_events_companions_duplicates_and_unsorted(library):
    source, dest = library
    plan, index = make_plan(source, dest)
    rows = by_source(plan)
    trip = "2024/2024-07-12 Georgia - Tbilisi, Stepantsminda"

    assert rows["trip/IMG_0001.HEIC"].dest == f"{trip}/2024-07-12_10-00-00.heic"
    assert rows["trip/IMG_0001.MOV"].dest == f"{trip}/2024-07-12_10-00-00.mov"
    assert rows["trip/IMG_0001.AAE"].dest == f"{trip}/2024-07-12_10-00-00.aae"
    assert rows["trip/IMG_0002.JPG"].dest == f"{trip}/2024-07-13_09-00-00.jpg"
    assert rows["copies/IMG_0001 (1).HEIC"].action == "duplicate"
    assert rows["copies/IMG_0001 (1).HEIC"].note == "same as source/trip/IMG_0001.HEIC"
    assert rows["whatsapp/IMG-20240801-WA0001.jpg"].dest == "2024/2024-08-01/2024-08-01_00-00-00.jpg"
    assert rows["whatsapp/IMG-20240801-WA0002.jpg"].dest == "2024/2024-08-01/2024-08-01_00-00-00_1.jpg"
    assert rows["misc/random.jpg"].dest == "_unsorted/misc/random.jpg"
    assert rows["misc/old.jpg"].action == "duplicate"
    assert rows["misc/old.jpg"].note == "same as dest/2020/2020-01-01/2020-01-01_12-00-00.jpg"
    assert rows["trip/notes.txt"].action == "ignore"
    index.close()


def test_screenshots_go_to_month_folders_outside_events(library):
    source, dest = library
    plan, index = make_plan(source, dest)
    index.close()
    rows = by_source(plan)

    assert rows["phone/Screenshot_20240712-150000.png"].dest == "screenshots/2024/07/2024-07-12_15-00-00.png"
    assert rows["phone/Screenshot_20240712-150000.png"].note == "screenshot by filename"
    assert rows["phone/IMG_0500.PNG"].dest == "screenshots/2024/07/2024-07-12_16-00-00.png"
    assert rows["phone/IMG_0500.PNG"].note == "screenshot by metadata"
    assert rows["phone/RPReplay_Final1690000000.MP4"].dest == "screenshots/2024/07/2024-07-12_17-00-00.mp4"
    assert rows["phone/Screenshot (12).png"].dest == "screenshots/_unsorted/phone/Screenshot (12).png"
    trip = [r.dest for r in plan.rows if r.dest.startswith("2024/2024-07-12")]
    assert {d.rsplit("/", 1)[0] for d in trip} == {"2024/2024-07-12 Georgia - Tbilisi, Stepantsminda"}


def test_apply_copies_verifies_and_is_idempotent(library, tmp_path):
    source, dest = library
    plan, index = make_plan(source, dest)
    plan_path = write_plan(plan, tmp_path / "plan")
    rows = read_plan(plan_path)

    first = apply_plan(source, dest, rows, index, lambda _: None)
    second = apply_plan(source, dest, rows, index, lambda _: None)
    index.close()

    copies = [r for r in rows if r.action == "copy"]
    assert (first.copied, first.failed) == (len(copies), 0)
    assert (second.copied, second.already_there, second.failed) == (0, len(copies), 0)
    trip = dest / "2024/2024-07-12 Georgia - Tbilisi, Stepantsminda"
    assert (trip / "2024-07-12_10-00-00.heic").read_bytes() == b"trip/IMG_0001.HEIC"
    assert not list(dest.rglob("*.part"))
    assert (source / "trip/IMG_0001.HEIC").exists()


def test_rerun_with_new_files_reuses_event_folder_and_skips_copied(library, tmp_path):
    source, dest = library
    plan, index = make_plan(source, dest)
    apply_plan(source, dest, plan.rows, index, lambda _: None)
    index.close()

    EXIF["late/phone2.jpg"] = {"DateTimeOriginal": "2024:07:12 18:00:00"}
    try:
        write(source, "late/phone2.jpg", b"from another phone")
        replan, index = make_plan(source, dest)
        index.close()
    finally:
        del EXIF["late/phone2.jpg"]

    rows = by_source(replan)
    assert rows["late/phone2.jpg"].dest == "2024/2024-07-12 Georgia - Tbilisi, Stepantsminda/2024-07-12_18-00-00.jpg"
    assert [r.source for r in replan.rows if r.action == "copy"] == ["late/phone2.jpg"]


def test_apply_refuses_to_overwrite_different_content(library, tmp_path):
    source, dest = library
    plan, index = make_plan(source, dest)
    target = next(r for r in plan.rows if r.source == "misc/random.jpg")
    write(dest, target.dest, b"something else")
    result = apply_plan(source, dest, [target], index, lambda _: None)
    index.close()
    assert result.failed == 1
    assert (dest / target.dest).read_bytes() == b"something else"
