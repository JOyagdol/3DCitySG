"""Containment rules based on bounding boxes."""

from __future__ import annotations

from citygml_sg.domain.bbox import BBox


def is_contained(inner: BBox | None, outer: BBox | None) -> bool:
    if inner is None or outer is None:
        return False
    return outer.contains(inner)
