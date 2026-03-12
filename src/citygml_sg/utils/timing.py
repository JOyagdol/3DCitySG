"""Timing utility helpers."""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter


@contextmanager
def timed(label: str):
    start = perf_counter()
    try:
        yield
    finally:
        elapsed = perf_counter() - start
        print(f"{label}: {elapsed:.4f}s")
