"""
src/pdf_research_pipeline/utils/timers.py

Timing utilities for measuring stage and parser durations.

Decision: Use time.perf_counter() for high-resolution wall-clock timing.
perf_counter is monotonic and not affected by system clock adjustments,
making it the correct choice for pipeline stage duration measurement.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator


@dataclass
class TimingResult:
    name: str
    duration_ms: int
    start_ts: float = field(repr=False)
    end_ts: float = field(repr=False)


@contextmanager
def timed(name: str) -> Generator[list[TimingResult], None, None]:
    """
    Context manager that measures elapsed time and appends a TimingResult
    to the provided list.

    Usage:
        results: list[TimingResult] = []
        with timed("extract_pages") as results:
            do_work()
        print(results[0].duration_ms)
    """
    result: list[TimingResult] = []
    t0 = time.perf_counter()
    ts0 = time.time()
    try:
        yield result
    finally:
        t1 = time.perf_counter()
        ts1 = time.time()
        result.append(
            TimingResult(
                name=name,
                duration_ms=int((t1 - t0) * 1000),
                start_ts=ts0,
                end_ts=ts1,
            )
        )


def now_ms() -> int:
    """Current epoch time in milliseconds."""
    return int(time.time() * 1000)
