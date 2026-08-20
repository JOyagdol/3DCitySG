"""JSON serialization helpers for retrieval reports."""

from __future__ import annotations

from typing import Any


def to_json_safe(value: Any) -> Any:
    """Recursively normalize common Python containers for JSON output."""
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [to_json_safe(item) for item in value]
    return value
