import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .hashing import file_hash
from .index import DestIndex
from .planner import PlanRow
from .progress import Log, track

COMMIT_EVERY = 200


@dataclass
class ApplyResult:
    copied: int = 0
    already_there: int = 0
    failed: int = 0


def safe_join(root: Path, rel: str) -> Path:
    path = PurePosixPath(rel)
    if not rel or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe path in plan: {rel!r}")
    return root.joinpath(*path.parts)


def _copy_verified(src: Path, target: Path, expected_hash: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.part")
    try:
        shutil.copy2(src, partial)
        if file_hash(partial) != expected_hash:
            raise OSError("content changed since the plan was made")
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def apply_plan(source: Path, dest: Path, rows: list[PlanRow], index: DestIndex, log: Log,
               dry_run: bool = False) -> ApplyResult:
    result = ApplyResult()
    copies = [row for row in rows if row.action == "copy"]
    for done, row in enumerate(track(copies, len(copies), "copying", log), 1):
        try:
            src = safe_join(source, row.source)
            target = safe_join(dest, row.dest)
            if target.exists():
                if file_hash(target) != row.hash:
                    raise OSError(f"{row.dest} already exists with different content")
                result.already_there += 1
            elif dry_run:
                log(f"  {row.source} -> {row.dest}")
                result.copied += 1
                continue
            else:
                _copy_verified(src, target, row.hash)
                result.copied += 1
            if row.kind != "sidecar":
                index.add(row.dest, target, row.hash, row.taken_at or None)
        except (OSError, ValueError) as error:
            log(f"  failed {row.source}: {error}")
            result.failed += 1
        if done % COMMIT_EVERY == 0:
            index.commit()
    index.commit()
    return result
