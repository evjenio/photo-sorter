import os
import sqlite3
from datetime import datetime
from pathlib import Path, PurePosixPath

from .hashing import hash_files
from .media import STATE_DIR, kind_of, walk_files
from .metadata import MetadataReader, resolve_date
from .progress import Log
from .similar import PHASH_EXTS, phash_files

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
        if stale:
            log(f"Indexing {len(stale)} files already in destination")
            paths = [path for path, _ in stale.values()]
            hashes = hash_files(paths, workers, log)
            exif = read_metadata(paths, log)
            for rel, (path, st) in stale.items():
                if not hashes[path]:
                    continue
                taken_at, _ = resolve_date(exif.get(str(path), {}), path.name)
                self.db.execute(
                    "INSERT OR REPLACE INTO files (rel, size, mtime_ns, hash, taken_at, phash) VALUES (?, ?, ?, ?, ?, NULL)",
                    (rel, st.st_size, st.st_mtime_ns, hashes[path], taken_at.isoformat() if taken_at else None),
                )
        if with_phash:
            self._fill_phashes(workers, log)
        self.db.commit()

    def _fill_phashes(self, workers: int, log: Log) -> None:
        missing = [
            rel for (rel,) in self.db.execute("SELECT rel FROM files WHERE phash IS NULL")
            if PurePosixPath(rel).suffix.lower() in PHASH_EXTS
        ]
        if not missing:
            return
        paths = {self.dest / rel: rel for rel in missing}
        for path, value in phash_files(list(paths), workers, log).items():
            self.db.execute("UPDATE files SET phash = ? WHERE rel = ?", (f"{value:016x}" if value is not None else "", paths[path]))

    def add(self, rel: str, path: Path, file_hash: str, taken_at: str | None) -> None:
        st = path.stat()
        self.db.execute(
            "INSERT OR REPLACE INTO files (rel, size, mtime_ns, hash, taken_at, phash) VALUES (?, ?, ?, ?, ?, NULL)",
            (rel, st.st_size, st.st_mtime_ns, file_hash, taken_at),
        )

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
