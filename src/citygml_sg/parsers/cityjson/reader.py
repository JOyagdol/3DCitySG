"""CityJSON reader."""

from __future__ import annotations

import json
from pathlib import Path


def read_cityjson(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
