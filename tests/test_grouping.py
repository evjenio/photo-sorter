from datetime import datetime

from conftest import media
from photo_sorter.grouping import attach_companions, companion_suffix

T = datetime(2024, 7, 12, 10, 0, 0)


def test_live_photo_pairs_by_content_identifier():
    photo = media("a/IMG_0001.HEIC", T, content_id="X")
    video = media("a/IMG_0001.MOV", datetime(2024, 7, 12, 10, 0, 2), content_id="X")
    primaries, orphans = attach_companions([video, photo])
    assert primaries == [photo]
    assert photo.companions == [video]
    assert orphans == []


def test_different_content_identifier_is_not_paired():
    photo = media("a/IMG_0001.HEIC", T, content_id="X")
    video = media("a/IMG_0001.MOV", T, content_id="Y")
    primaries, _ = attach_companions([photo, video])
    assert set(primaries) == {photo, video}


def test_raw_jpeg_pair_by_time_and_unrelated_same_stem_kept_apart():
    jpg = media("a/IMG_0001.JPG", T)
    raw = media("a/IMG_0001.CR2", T)
    old_video = media("a/IMG_0001.MOV", datetime(2019, 1, 1))
    primaries, _ = attach_companions([raw, old_video, jpg])
    assert set(primaries) == {jpg, old_video}
    assert jpg.companions == [raw]


def test_sidecars_follow_primary_and_orphans_are_reported():
    photo = media("a/IMG_0001.JPG", T)
    aae = media("a/IMG_0001.AAE")
    xmp = media("a/IMG_0001.JPG.xmp")
    orphan = media("a/IMG_0002.AAE")
    primaries, orphans = attach_companions([photo, aae, xmp, orphan])
    assert primaries == [photo]
    assert set(photo.companions) == {aae, xmp}
    assert orphans == [orphan]
    assert companion_suffix(photo, xmp) == ".jpg.xmp"
    assert companion_suffix(photo, aae) == ".aae"
