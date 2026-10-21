import pytest

import photo_sorter.index as index_module
from photo_sorter.index import DestIndex


class Interrupted(Exception):
    pass


def test_interrupted_indexing_keeps_finished_batches(tmp_path, monkeypatch):
    monkeypatch.setattr(index_module, "INDEX_BATCH", 2, raising=False)
    for i in range(5):
        (tmp_path / f"{i}.jpg").write_bytes(f"photo {i}".encode())

    def read_until_second_batch(paths, log):
        calls.append([p.name for p in paths])
        if len(calls) == 2:
            raise Interrupted
        return {}

    calls = []
    index = DestIndex(tmp_path)
    with pytest.raises(Interrupted):
        index.refresh(read_until_second_batch, 2, False, lambda _: None)
    index.db.close()

    resumed = DestIndex(tmp_path)
    assert sorted(resumed.paths()) == ["0.jpg", "1.jpg"]

    seen = []
    resumed.refresh(lambda paths, log: seen.extend(p.name for p in paths) or {}, 2, False, lambda _: None)
    assert sorted(seen) == ["2.jpg", "3.jpg", "4.jpg"]
    assert len(resumed.paths()) == 5
    resumed.close()
