import sys
import time
from typing import Callable, Iterable, Iterator, TypeVar

T = TypeVar("T")
Log = Callable[[str], None]


def log_stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def track(items: Iterable[T], total: int, label: str, log: Log, every: float = 5.0) -> Iterator[T]:
    last = time.monotonic()
    for done, item in enumerate(items, 1):
        now = time.monotonic()
        if now - last >= every:
            log(f"  {label}: {done}/{total}")
            last = now
        yield item
