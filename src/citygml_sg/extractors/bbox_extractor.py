"""BBox extraction helpers."""

from __future__ import annotations

from citygml_sg.domain.bbox import BBox
from citygml_sg.domain.geometry import Point3D


def extract_bbox(points: list[Point3D]) -> BBox | None:
    if not points:
        return None
    min_x = min(p.x for p in points)
    min_y = min(p.y for p in points)
    min_z = min(p.z for p in points)
    max_x = max(p.x for p in points)
    max_y = max(p.y for p in points)
    max_z = max(p.z for p in points)
    return BBox(Point3D(min_x, min_y, min_z), Point3D(max_x, max_y, max_z))
