from photo_sorter.progress import track


def test_reports_final_count():
    messages = []
    assert list(track([1, 2, 3], 3, "hashing", messages.append)) == [1, 2, 3]
    assert messages == ["  hashing: 3/3"]


def test_counts_by_weight_after_each_item_is_processed():
    messages = []
    for _ in track([[1, 2], [3]], 3, "batches", messages.append, every=0, weight=len):
        messages.append("processed")
    assert messages == ["processed", "  batches: 2/3", "processed", "  batches: 3/3"]
