"""Observed View Graph JSON loading and lightweight validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


KITCHEN_FURNITURE_CATEGORIES = {"sink", "counter", "cabinet", "storage", "fridge", "kitchen"}
LOW_CONFIDENCE_FURNITURE_CATEGORIES = {"sofa", "table", "tv"}


def default_observed_weight(category: str, *, furniture_keyword_weight: float = 3.0) -> float:
    """Return the default retrieval weight for an observed object category."""
    normalized = category.strip().lower()
    if normalized in KITCHEN_FURNITURE_CATEGORIES:
        return 4.0
    if normalized in LOW_CONFIDENCE_FURNITURE_CATEGORIES:
        return 1.0
    return float(furniture_keyword_weight)


def as_float(value: object, *, field: str, path: Path) -> float:
    """Parse a numeric OVG field with a path-aware error message."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: observed object field '{field}' must be numeric, got {value!r}") from exc


def load_observed_view_graph(
    path_value: str | None,
    *,
    furniture_keyword_weight: float = 3.0,
) -> tuple[list[dict[str, object]], list[object], dict[str, object], dict[str, object]]:
    """Load an observed view graph JSON file into query-ready dictionaries."""
    if not path_value:
        return [], [], {}, {}

    path = Path(path_value)
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: observed view graph must be a JSON object")

    objects_raw = raw.get("objects", [])
    if not isinstance(objects_raw, list):
        raise ValueError(f"{path}: 'objects' must be a list")

    objects: list[dict[str, object]] = []
    for index, item in enumerate(objects_raw):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: objects[{index}] must be a JSON object")
        category = str(item.get("category", "")).strip().lower()
        if not category:
            continue

        observed: dict[str, object] = {
            "alias": str(item.get("alias") or category),
            "category": category,
            "weight": as_float(
                item.get("weight", default_observed_weight(category, furniture_keyword_weight=furniture_keyword_weight)),
                field="weight",
                path=path,
            ),
            "confidence": as_float(item.get("confidence", 1.0), field="confidence", path=path),
            "visibility": as_float(item.get("visibility", 1.0), field="visibility", path=path),
        }
        if item.get("type") is not None:
            observed["type"] = str(item["type"])
        for id_field in ("id", "gml_id", "target_id"):
            if item.get(id_field) is not None:
                observed[id_field] = str(item[id_field])
        if isinstance(item.get("target_ids"), list):
            observed["target_ids"] = [str(target_id) for target_id in item["target_ids"]]
        if isinstance(item.get("attributes"), dict):
            observed["attributes"] = item["attributes"]
        objects.append(observed)

    relations_raw = raw.get("relations", [])
    if not isinstance(relations_raw, list):
        raise ValueError(f"{path}: 'relations' must be a list")

    constraints_raw = raw.get("constraints", {})
    if not isinstance(constraints_raw, dict):
        raise ValueError(f"{path}: 'constraints' must be a JSON object")

    query_raw = raw.get("query", {})
    if not isinstance(query_raw, dict):
        raise ValueError(f"{path}: 'query' must be a JSON object")

    return objects, relations_raw, constraints_raw, query_raw


def optional_non_negative_int(value: object, *, field: str, path: str) -> int | None:
    """Parse an optional non-negative integer OVG constraint field."""
    if value is None:
        return None
    try:
        converted = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: observed constraint field '{field}' must be an integer, got {value!r}") from exc
    if converted < 0:
        raise ValueError(f"{path}: observed constraint field '{field}' must be non-negative, got {value!r}")
    return converted
