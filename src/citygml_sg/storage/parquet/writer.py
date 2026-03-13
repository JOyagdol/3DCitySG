"""Parquet writer placeholder."""

from __future__ import annotations

from pathlib import Path


def write_parquet_placeholder(path: str | Path) -> None:
    Path(path).write_text("Planned stub: parquet export adapter is not wired in v1.", encoding="utf-8")
