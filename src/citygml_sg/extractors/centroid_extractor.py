"""Centroid extraction helpers."""

from __future__ import annotations

from citygml_sg.domain.bbox import BBox
from citygml_sg.domain.geometry import Point3D


def extract_centroid(bbox: BBox | None) -> Point3D | None:
    if bbox is None:
        return None
    return Point3D(
        (bbox.min_point.x + bbox.max_point.x) / 2.0,
        (bbox.min_point.y + bbox.max_point.y) / 2.0,
        (bbox.min_point.z + bbox.max_point.z) / 2.0,
    )
