"""JSON writer for graph snapshots."""

from __future__ import annotations

import json
from typing import Iterable, Mapping
from pathlib import Path

PATCHABLE_NUMBER_WIDTH = 24


def write_json(path: str | Path, payload: dict) -> None:
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _format_patchable_json_number(value: float) -> str:
    text = f"{float(value):.6f}"
    if len(text) > PATCHABLE_NUMBER_WIDTH:
        text = f"{float(value):.6e}"
    if len(text) > PATCHABLE_NUMBER_WIDTH:
        raise ValueError(f"Patchable JSON number is too wide: {text}")
    return text.rjust(PATCHABLE_NUMBER_WIDTH)


def _prepare_summary_with_patch_slots(
    summary: Mapping[str, object],
    stage_duration_keys: Iterable[str],
) -> tuple[str, dict[str, int]]:
    text = json.dumps(dict(summary), ensure_ascii=False, indent=2)
    stage_idx = text.find('"stage_durations": {')
    if stage_idx < 0:
        return text, {}

    offsets: dict[str, int] = {}
    search_idx = stage_idx
    placeholder = _format_patchable_json_number(0.0)
    for key in stage_duration_keys:
        pattern = f'"{key}": 0.0'
        idx = text.find(pattern, search_idx)
        if idx < 0:
            continue
        value_start = idx + len(f'"{key}": ')
        value_end = value_start + len("0.0")
        text = text[:value_start] + placeholder + text[value_end:]
        offsets[key] = value_start
        search_idx = value_start + len(placeholder)

    return text, offsets


def patch_json_number_fields(
    path: str | Path,
    offsets: Mapping[str, int],
    values: Mapping[str, float],
) -> None:
    if not offsets:
        return

    with Path(path).open("r+b") as f:
        for key, offset in offsets.items():
            if key not in values:
                continue
            f.seek(offset)
            f.write(_format_patchable_json_number(float(values[key])).encode("utf-8"))


def _write_text(handle, text: str) -> None:
    handle.write(text.encode("utf-8"))


def write_graph_json_stream(
    path: str | Path,
    *,
    summary: Mapping[str, object],
    nodes: Iterable[Mapping[str, object]],
    edges: Iterable[Mapping[str, object]],
    patchable_stage_duration_keys: Iterable[str] = (),
) -> dict[str, int]:
    target = Path(path)
    with target.open("wb") as f:
        _write_text(f, "{\n")
        _write_text(f, '  "summary": ')
        summary_start = f.tell()
        summary_text, relative_patch_offsets = _prepare_summary_with_patch_slots(
            summary,
            patchable_stage_duration_keys,
        )
        _write_text(f, summary_text)
        absolute_patch_offsets = {
            key: summary_start + len(summary_text[:offset].encode("utf-8"))
            for key, offset in relative_patch_offsets.items()
        }
        _write_text(f, ",\n")

        _write_text(f, '  "nodes": [\n')
        first = True
        for node in nodes:
            if not first:
                _write_text(f, ",\n")
            _write_text(f, "    ")
            _write_text(f, json.dumps(dict(node), ensure_ascii=False))
            first = False
        _write_text(f, "\n  ],\n")

        _write_text(f, '  "edges": [\n')
        first = True
        for edge in edges:
            if not first:
                _write_text(f, ",\n")
            _write_text(f, "    ")
            _write_text(f, json.dumps(dict(edge), ensure_ascii=False))
            first = False
        _write_text(f, "\n  ]\n")
        _write_text(f, "}\n")

    return absolute_patch_offsets
