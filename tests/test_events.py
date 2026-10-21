from datetime import datetime, timedelta

from conftest import media
from photo_sorter.events import ExistingEvents, cluster_events, event_folder, event_title

GAP = timedelta(hours=24)
SPAN = timedelta(days=14)


def test_split_on_long_pause():
    a = media("a.jpg", datetime(2024, 7, 1, 10))
    b = media("b.jpg", datetime(2024, 7, 2, 9))
    c = media("c.jpg", datetime(2024, 7, 5, 9))
    assert cluster_events([a, b, c], GAP, SPAN) == [[a, b], [c]]


def test_split_on_country_change_but_not_on_missing_country():
    a = media("a.jpg", datetime(2024, 7, 1, 10), city="Almaty", country="Kazakhstan")
    b = media("b.jpg", datetime(2024, 7, 1, 12))
    c = media("c.jpg", datetime(2024, 7, 1, 18), city="Tbilisi", country="Georgia")
    assert cluster_events([a, b, c], GAP, SPAN) == [[a, b], [c]]


def test_split_on_max_span():
    items = [media(f"{d}.jpg", datetime(2024, 7, 1) + timedelta(days=d)) for d in range(20)]
    clusters = cluster_events(items, GAP, SPAN)
    assert [len(c) for c in clusters] == [15, 5]


def test_titles():
    tbilisi = media("a.jpg", datetime(2024, 7, 12, 10), city="Tbilisi", country="Georgia")
    kazbegi = media("b.jpg", datetime(2024, 7, 13, 10), city="Stepantsminda", country="Georgia")
    no_geo = media("c.jpg", datetime(2024, 7, 12, 11))
    assert event_title([tbilisi, no_geo]) == "12 Tbilisi"
    assert event_title([tbilisi, kazbegi]) == "12 Georgia - Tbilisi, Stepantsminda"
    assert event_title([no_geo]) == "12"
    assert event_folder([tbilisi, kazbegi]) == "2024/2024-07/12 Georgia - Tbilisi, Stepantsminda"


def test_event_crossing_months_stays_in_its_start_month():
    items = [media("a.jpg", datetime(2024, 6, 30, 20), city="Tbilisi", country="Georgia"),
             media("b.jpg", datetime(2024, 7, 1, 9), city="Tbilisi", country="Georgia")]
    assert event_folder(items) == "2024/2024-06/30 Tbilisi"


def test_title_is_filesystem_safe():
    item = media("a.jpg", datetime(2024, 7, 12), city="A/B: C", country="X")
    assert event_folder([item]) == "2024/2024-07/12 A-B- C"


def test_existing_event_folder_is_reused_within_gap():
    existing = ExistingEvents([
        (datetime(2024, 7, 12, 10), "2024/2024-07/12 Tbilisi/x.jpg"),
        (datetime(2024, 7, 12, 11), "_unsorted/y.jpg"),
        (datetime(2024, 7, 13, 8), "screenshots/2024/07/a.png"),
        (datetime(2024, 7, 13, 8, 1), "screenshots/2024/07/b.png"),
    ], GAP)
    near = [media("a.jpg", datetime(2024, 7, 13, 9))]
    far = [media("b.jpg", datetime(2024, 7, 20))]
    assert existing.folder_for(near) == "2024/2024-07/12 Tbilisi"
    assert existing.folder_for(far) is None
