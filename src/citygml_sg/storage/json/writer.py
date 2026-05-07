"""JSON writer for graph snapshots."""

from __future__ import annotations

import json
from typing import Iterable, Mapping
from pathlib import Path


def write_json(path: str | Path, payload: dict) -> None:
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_graph_json_stream(
    path: str | Path,
    *,
    summary: Mapping[str, object],
    nodes: Iterable[Mapping[str, object]],
    edges: Iterable[Mapping[str, object]],
) -> None:
    target = Path(path)
    with target.open("w", encoding="utf-8") as f:
        f.write("{\n")
        f.write('  "summary": ')
        json.dump(dict(summary), f, ensure_ascii=False, indent=2)
        f.write(",\n")

        f.write('  "nodes": [\n')
        first = True
        for node in nodes:
            if not first:
                f.write(",\n")
            f.write("    ")
            json.dump(dict(node), f, ensure_ascii=False)
            first = False
        f.write("\n  ],\n")

        f.write('  "edges": [\n')
        first = True
        for edge in edges:
            if not first:
                f.write(",\n")
            f.write("    ")
            json.dump(dict(edge), f, ensure_ascii=False)
            first = False
        f.write("\n  ]\n")
        f.write("}\n")
