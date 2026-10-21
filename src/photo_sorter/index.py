import os
import sqlite3
from datetime import datetime
from pathlib import Path, PurePosixPath

from .hashing import hash_files
from .media import STATE_DIR, kind_of, walk_files
from .metadata import MetadataReader, resolve_date
from .progress import Log, track
from .similar import PHASH_EXTS, phash_files

INDEX_BATCH = 1000

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    rel TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    hash TEXT NOT NULL,
    taken_at TEXT,
    phash TEXT
)
"""


def _silent(_: str) -> None:
    pass


class DestIndex:
    """Cache of what the destination already holds, so reruns skip rehashing."""

    def __init__(self, dest: Path):
        self.dest = dest
        state = dest / STATE_DIR
        state.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(state / "index.sqlite")
        self.db.execute(SCHEMA)

    def close(self) -> None:
        self.db.commit()
        self.db.close()

    def refresh(self, read_metadata: MetadataReader, workers: int, with_phash: bool, log: Log) -> None:
        known = {rel: (size, mtime) for rel, size, mtime in self.db.execute("SELECT rel, size, mtime_ns FROM files")}
        present: dict[str, tuple[Path, os.stat_result]] = {}
        for path in walk_files(self.dest):
            if kind_of(path) in ("photo", "video"):
                present[path.relative_to(self.dest).as_posix()] = (path, path.stat())

        self.db.executemany("DELETE FROM files WHERE rel = ?", [(rel,) for rel in known.keys() - present.keys()])
        stale = {
            rel: (path, st) for rel, (path, st) in present.items()
            if known.get(rel) != (st.st_size, st.st_mtime_ns)
        }
        self.db.commit()
        if stale:
            log(f"Indexing {len(stale)} files already in destination")
            items = list(stale.items())
            batches = [items[i:i + INDEX_BATCH] for i in range(0, len(items), INDEX_BATCH)]
            for batch in track(batches, len(items), "indexing destination", log, weight=len):
                self._index_batch(batch, read_metadata, workers)
        if with_phash:
            self._fill_phashes(workers, log)

    def _index_batch(self, batch: list[tuple[str, tuple[Path, os.stat_result]]], read_metadata: MetadataReader,
                     workers: int) -> None:
        paths = [path for _, (path, _) in batch]
        hashes = hash_files(paths, workers, _silent)
        exif = read_metadata(paths, _silent)
        for rel, (path, st) in batch:
            if not hashes[path]:
                continue
            taken_at, _ = resolve_date(exif.get(str(path), {}), path.name)
            self.db.execute(
                "INSERT OR REPLACE INTO files (rel, size, mtime_ns, hash, taken_at, phash) VALUES (?, ?, ?, ?, ?, NULL)",
                (rel, st.st_size, st.st_mtime_ns, hashes[path], taken_at.isoformat() if taken_at else None),
            )
        self.db.commit()

    def _fill_phashes(self, workers: int, log: Log) -> None:
        missing = [
            rel for (rel,) in self.db.execute("SELECT rel FROM files WHERE phash IS NULL")
            if PurePosixPath(rel).suffix.lower() in PHASH_EXTS
        ]
        if not missing:
            return
        batches = [missing[i:i + INDEX_BATCH] for i in range(0, len(missing), INDEX_BATCH)]
        for batch in track(batches, len(missing), "comparing images in destination", log, weight=len):
            paths = {self.dest / rel: rel for rel in batch}
            for path, value in phash_files(list(paths), workers, _silent).items():
                self.db.execute("UPDATE files SET phash = ? WHERE rel = ?", (f"{value:016x}" if value is not None else "", paths[path]))
            self.db.commit()

    def add(self, rel: str, path: Path, file_hash: str, taken_at: str | None) -> None:
        st = path.stat()
        self.db.execute(
            "INSERT OR REPLACE INTO files (rel, size, mtime_ns, hash, taken_at, phash) VALUES (?, ?, ?, ?, ?, NULL)",
            (rel, st.st_size, st.st_mtime_ns, file_hash, taken_at),
        )

    def confirms(self, rel: str, file_hash: str, path: Path) -> bool:
        """True when the index already vouches that path holds file_hash, so it needn't be read."""
        row = self.db.execute("SELECT size, mtime_ns, hash FROM files WHERE rel = ?", (rel,)).fetchone()
        if row is None:
            return False
        st = path.stat()
        return row == (st.st_size, st.st_mtime_ns, file_hash)

    def commit(self) -> None:
        self.db.commit()

    def hash_locations(self) -> dict[str, str]:
        return {h: rel for rel, h in self.db.execute("SELECT rel, hash FROM files ORDER BY rel DESC")}

    def paths(self) -> list[str]:
        return [rel for (rel,) in self.db.execute("SELECT rel FROM files")]

    def dated_entries(self) -> list[tuple[datetime, str]]:
        rows = self.db.execute("SELECT taken_at, rel FROM files WHERE taken_at IS NOT NULL")
        return [(datetime.fromisoformat(taken_at), rel) for taken_at, rel in rows]

    def phashes(self) -> dict[str, tuple[int, int]]:
        rows = self.db.execute("SELECT rel, phash, size FROM files WHERE phash IS NOT NULL AND phash != ''")
        return {rel: (int(phash, 16), size) for rel, phash, size in rows}
