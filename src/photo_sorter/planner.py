import csv
import posixpath
from dataclasses import asdict, dataclass, field, fields
from datetime import timedelta
from pathlib import Path, PurePosixPath

from .events import SCREENSHOTS_DIR, UNSORTED_DIR, ExistingEvents, cluster_events, event_folder
from .grouping import attach_companions, companion_suffix
from .hashing import hash_files
from .index import DestIndex
from .media import MediaFile, kind_of, normalized_ext, walk_files
from .metadata import MetadataReader, apply_metadata, read_exif
from .progress import Log, log_stderr
from .similar import PHASH_EXTS, group_similar, phash_files


@dataclass
class PlanOptions:
    gap: timedelta = timedelta(hours=24)
    max_span: timedelta = timedelta(days=14)
    similar: bool = False
    similar_distance: int = 6
    workers: int = 4


@dataclass
class PlanRow:
    action: str
    source: str
    dest: str = ""
    kind: str = ""
    hash: str = ""
    taken_at: str = ""
    date_source: str = ""
    city: str = ""
    country: str = ""
    note: str = ""


@dataclass
class SimilarRow:
    group: int
    status: str
    dest: str
    source: str = ""
    size: int = 0


@dataclass
class Plan:
    rows: list[PlanRow] = field(default_factory=list)
    similar: list[SimilarRow] = field(default_factory=list)


class Namer:
    """Reserves collision-free destination paths, case-insensitively."""

    def __init__(self, dest: Path, taken: list[str]):
        self._dest = dest
        self._used = {rel.lower() for rel in taken}

    def reserve(self, folder: str, stem: str, suffixes: list[str]) -> list[str]:
        attempt = 0
        while True:
            candidate = stem if attempt == 0 else f"{stem}_{attempt}"
            names = [posixpath.join(folder, f"{candidate}{suffix}") for suffix in suffixes]
            if not any(n.lower() in self._used or (self._dest / n).exists() for n in names):
                self._used.update(n.lower() for n in names)
                return names
            attempt += 1


def _copy_row(file: MediaFile, dest: str, note: str = "") -> PlanRow:
    return PlanRow(
        action="copy",
        source=file.rel,
        dest=dest,
        kind=file.kind,
        hash=file.hash,
        taken_at=file.taken_at.isoformat() if file.taken_at else "",
        date_source=file.date_source,
        city=file.city or "",
        country=file.country or "",
        note=note,
    )


def _duplicate_row(file: MediaFile, original: str) -> PlanRow:
    return PlanRow("duplicate", file.rel, kind=file.kind, hash=file.hash, note=f"same as {original}")


def _dedupe(primaries: list[MediaFile], known: dict[str, str], rows: list[PlanRow]) -> list[MediaFile]:
    seen = {h: f"dest/{rel}" for h, rel in known.items()}
    ordered = sorted(primaries, key=lambda p: (-len(p.companions), p.taken_at is None, p.rel))
    unique: list[MediaFile] = []
    detached: list[MediaFile] = []
    for primary in ordered:
        companions: list[MediaFile] = []
        for companion in primary.companions:
            if companion.kind != "sidecar" and companion.hash in seen:
                rows.append(_duplicate_row(companion, seen[companion.hash]))
            else:
                companions.append(companion)
        if primary.hash in seen:
            original = seen[primary.hash]
            rows.append(_duplicate_row(primary, original))
            for companion in companions:
                if companion.kind == "sidecar":
                    rows.append(PlanRow("duplicate", companion.rel, kind="sidecar", hash=companion.hash,
                                        note=f"sidecar of a duplicate of {original}"))
                else:
                    detached.append(companion)
            continue
        primary.companions = companions
        seen[primary.hash] = f"source/{primary.rel}"
        for companion in companions:
            if companion.kind != "sidecar":
                seen[companion.hash] = f"source/{companion.rel}"
        unique.append(primary)
    for file in detached:
        if file.hash in seen:
            rows.append(_duplicate_row(file, seen[file.hash]))
        else:
            seen[file.hash] = f"source/{file.rel}"
            unique.append(file)
    return unique


def _place(primary: MediaFile, folder: str, stem: str, primary_suffix: str, namer: Namer,
           rows: list[PlanRow], note: str = "") -> list[tuple[MediaFile, str]]:
    suffixes = [primary_suffix, *(companion_suffix(primary, c) for c in primary.companions)]
    targets = namer.reserve(folder, stem, suffixes)
    rows.append(_copy_row(primary, targets[0], note))
    for companion, target in zip(primary.companions, targets[1:]):
        rows.append(_copy_row(companion, target, f"companion of {primary.rel}"))
    return list(zip([primary, *primary.companions], targets))


def _date_stem(file: MediaFile) -> str:
    return f"{file.taken_at:%Y-%m-%d_%H-%M-%S}"


def _place_undated(primary: MediaFile, root: str, namer: Namer, rows: list[PlanRow],
                   note: str) -> list[tuple[MediaFile, str]]:
    parent, name = posixpath.split(primary.rel)
    original = PurePosixPath(name)
    folder = posixpath.join(root, parent) if parent else root
    return _place(primary, folder, original.stem, original.suffix, namer, rows, note)


def _similar_rows(placed: list[tuple[MediaFile, str]], index: DestIndex, options: PlanOptions,
                  log: Log) -> list[SimilarRow]:
    candidates = {file.path: (file, target) for file, target in placed if file.ext in PHASH_EXTS}
    if not candidates:
        return []
    log(f"Looking for visually similar images among {len(candidates)} new files")
    hashes: dict[str, int] = {}
    details: dict[str, SimilarRow] = {}
    for path, value in phash_files(list(candidates), options.workers, log).items():
        if value is None:
            continue
        file, target = candidates[path]
        key = f"new:{target}"
        hashes[key] = value
        details[key] = SimilarRow(0, "new", target, file.rel, file.size)
    for rel, (value, size) in index.phashes().items():
        key = f"dest:{rel}"
        hashes[key] = value
        details[key] = SimilarRow(0, "existing", rel, "", size)

    rows: list[SimilarRow] = []
    groups = [g for g in group_similar(hashes, options.similar_distance) if any(k.startswith("new:") for k in g)]
    for number, group in enumerate(groups, 1):
        for key in group:
            row = details[key]
            row.group = number
            rows.append(row)
    return rows


def build_plan(source: Path, dest: Path, index: DestIndex, options: PlanOptions,
               read_metadata: MetadataReader = read_exif, log: Log = log_stderr) -> Plan:
    plan = Plan()
    media: list[MediaFile] = []
    for path in walk_files(source):
        rel = path.relative_to(source).as_posix()
        kind = kind_of(path)
        if kind is None:
            plan.rows.append(PlanRow("ignore", rel, note="not a photo or video"))
        else:
            media.append(MediaFile(rel, path, path.stat().st_size, kind))
    log(f"Found {len(media)} media files and {len(plan.rows)} other files in source")

    log("Reading metadata")
    exif = read_metadata([m.path for m in media if m.kind != "sidecar"])
    for file in media:
        if file.kind != "sidecar":
            apply_metadata(file, exif.get(str(file.path), {}))

    log("Hashing source files")
    hashes = hash_files([m.path for m in media], options.workers, log)
    readable: list[MediaFile] = []
    for file in media:
        file.hash = hashes[file.path]
        if file.hash:
            readable.append(file)
        else:
            plan.rows.append(PlanRow("ignore", file.rel, kind=file.kind, note="unreadable"))

    primaries, orphans = attach_companions(readable)
    plan.rows.extend(
        PlanRow("ignore", o.rel, kind=o.kind, hash=o.hash, note="sidecar without its photo or video") for o in orphans
    )
    unique = _dedupe(primaries, index.hash_locations(), plan.rows)

    namer = Namer(dest, index.paths())
    existing = ExistingEvents(index.dated_entries(), options.gap)
    placed: list[tuple[MediaFile, str]] = []
    camera = [p for p in unique if not p.screenshot]
    dated = sorted((p for p in camera if p.taken_at), key=lambda p: (p.taken_at, p.rel))
    for cluster in cluster_events(dated, options.gap, options.max_span):
        folder = existing.folder_for(cluster) or event_folder(cluster)
        for primary in cluster:
            placed += _place(primary, folder, _date_stem(primary), normalized_ext(primary.ext), namer, plan.rows)

    for primary in sorted((p for p in unique if p.screenshot), key=lambda p: p.rel):
        note = f"screenshot by {primary.screenshot}"
        if primary.taken_at:
            folder = f"{SCREENSHOTS_DIR}/{primary.taken_at:%Y/%m}"
            placed += _place(primary, folder, _date_stem(primary), normalized_ext(primary.ext), namer, plan.rows, note)
        else:
            placed += _place_undated(primary, f"{SCREENSHOTS_DIR}/{UNSORTED_DIR}", namer, plan.rows, f"{note}, no capture date")

    for primary in sorted((p for p in camera if not p.taken_at), key=lambda p: p.rel):
        placed += _place_undated(primary, UNSORTED_DIR, namer, plan.rows, "no capture date")

    if options.similar:
        plan.similar = _similar_rows(placed, index, options, log)
    return plan


def _write_csv(path: Path, rows: list, row_type: type) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[f.name for f in fields(row_type)])
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def write_plan(plan: Plan, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    order = {"copy": 0, "duplicate": 1, "ignore": 2}
    rows = sorted(plan.rows, key=lambda r: (order.get(r.action, 3), r.dest, r.source))
    plan_path = out_dir / "plan.csv"
    _write_csv(plan_path, rows, PlanRow)
    _write_csv(out_dir / "similar.csv", plan.similar, SimilarRow)
    return plan_path


def read_plan(path: Path) -> list[PlanRow]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        dialect = csv.Sniffer().sniff(f.readline(), delimiters=",;\t")
        f.seek(0)
        return [PlanRow(**row) for row in csv.DictReader(f, dialect=dialect)]
