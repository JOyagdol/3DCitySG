"""JSON writer for graph snapshots."""

from __future__ import annotations

import json
from pathlib import Path


def write_json(path: str | Path, payload: dict) -> None:
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
