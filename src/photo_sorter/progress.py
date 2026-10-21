import sys
import time
from typing import Callable, Iterable, Iterator, TypeVar

T = TypeVar("T")
Log = Callable[[str], None]


def log_stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def track(items: Iterable[T], total: int, label: str, log: Log, every: float = 5.0,
          weight: Callable[[T], int] | None = None) -> Iterator[T]:
    done = reported = 0
    last = time.monotonic()
    for item in items:
        yield item
        done += weight(item) if weight else 1
        now = time.monotonic()
        if now - last >= every:
            log(f"  {label}: {done}/{total}")
            last, reported = now, done
    if total and reported != done:
        log(f"  {label}: {done}/{total}")
