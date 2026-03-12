"""Parquet writer placeholder."""

from __future__ import annotations

from pathlib import Path


def write_parquet_placeholder(path: str | Path) -> None:
    Path(path).write_text("TODO: parquet export implementation", encoding="utf-8")
