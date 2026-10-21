import argparse
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from .applier import apply_plan
from .index import DestIndex
from .metadata import read_exif
from .planner import PlanOptions, build_plan, latest_plan, plans_dir, read_plan, write_plan
from .progress import log_stderr
from .similar import MAX_DISTANCE


def _check_roots(source: Path, dest: Path) -> None:
    if not source.is_dir():
        raise SystemExit(f"source is not a directory: {source}")
    source, dest = source.resolve(), dest.resolve()
    if dest.is_relative_to(source) or source.is_relative_to(dest):
        raise SystemExit("source and destination must not be inside each other")


def _scan(args: argparse.Namespace) -> int:
    if not shutil.which("exiftool"):
        raise SystemExit("exiftool is not installed")
    _check_roots(args.source, args.dest)
    options = PlanOptions(
        gap=timedelta(hours=args.gap_hours),
        max_span=timedelta(days=args.max_event_days),
        similar=args.similar,
        similar_distance=args.similar_distance,
        workers=args.workers,
    )
    index = DestIndex(args.dest)
    try:
        index.refresh(read_exif, options.workers, options.similar, log_stderr)
        plan = build_plan(args.source, args.dest, index, options)
    finally:
        index.close()

    out_dir = plans_dir(args.dest) / datetime.now().strftime("%Y%m%d-%H%M%S")
    plan_path = write_plan(plan, out_dir)

    copies = [r for r in plan.rows if r.action == "copy"]
    folders = Counter(r.dest.rsplit("/", 1)[0] for r in copies)
    actions = Counter(r.action for r in plan.rows)
    print(f"\nTo copy:     {actions['copy']} files into {len(folders)} folders")
    print(f"Duplicates:  {actions['duplicate']}")
    print(f"Ignored:     {actions['ignore']}")
    if options.similar:
        print(f"Similar:     {len({r.group for r in plan.similar})} groups (see similar.csv)")
    else:
        print("Similar:     skipped (enable with --similar)")
    for folder, count in sorted(folders.items())[:20]:
        print(f"  {folder}  ({count})")
    if len(folders) > 20:
        print(f"  ... and {len(folders) - 20} more")
    print(f"\nReview the plan: {plan_path}")
    print(f"Then run: photo-sorter apply {args.source} {args.dest} --latest")
    return 0


def _apply(args: argparse.Namespace) -> int:
    _check_roots(args.source, args.dest)
    plan_path = latest_plan(args.dest) if args.latest else args.plan
    log_stderr(f"Applying plan {plan_path}")
    rows = read_plan(plan_path)
    index = DestIndex(args.dest)
    try:
        result = apply_plan(args.source, args.dest, rows, index, log_stderr, dry_run=args.dry_run)
    finally:
        index.close()
    verb = "Would copy" if args.dry_run else "Copied"
    print(f"{verb}: {result.copied}, already in place: {result.already_there}, failed: {result.failed}")
    return 1 if result.failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="photo-sorter", description="Copy a messy photo library into an ordered one.")
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="build a copy plan; the source is never modified")
    scan.add_argument("source", type=Path)
    scan.add_argument("dest", type=Path)
    scan.add_argument("--gap-hours", type=float, default=24, help="pause that starts a new event (default: 24)")
    scan.add_argument("--max-event-days", type=float, default=14, help="longest event (default: 14)")
    scan.add_argument("--similar-distance", type=int, default=6, choices=range(MAX_DISTANCE + 1),
                      metavar=f"0-{MAX_DISTANCE}", help="phash bit distance for similar images (default: 6)")
    scan.add_argument("--similar", action="store_true", help="report visually similar images in similar.csv (slow)")
    scan.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    scan.set_defaults(handler=_scan)

    apply = commands.add_parser("apply", help="copy files according to a reviewed plan")
    apply.add_argument("source", type=Path)
    apply.add_argument("dest", type=Path)
    plan = apply.add_mutually_exclusive_group(required=True)
    plan.add_argument("plan", type=Path, nargs="?", help="plan.csv written by scan")
    plan.add_argument("--latest", action="store_true", help="apply the plan from the most recent scan")
    apply.add_argument("--dry-run", action="store_true")
    apply.set_defaults(handler=_apply)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
