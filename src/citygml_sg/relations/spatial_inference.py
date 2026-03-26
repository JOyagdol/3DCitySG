"""Spatial relation inference helpers based on AABB distances."""

from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt

from citygml_sg.domain.bbox import BBox
from citygml_sg.domain.enums import RelationType


def _axis_gap(min_a: float, max_a: float, min_b: float, max_b: float) -> float:
    if max_a < min_b:
        return min_b - max_a
    if max_b < min_a:
        return min_a - max_b
    return 0.0


def _axis_overlap(min_a: float, max_a: float, min_b: float, max_b: float) -> float:
    return min(max_a, max_b) - max(min_a, min_b)


def bbox_distance(first: BBox, second: BBox) -> float:
    gap_x = _axis_gap(first.min_point.x, first.max_point.x, second.min_point.x, second.max_point.x)
    gap_y = _axis_gap(first.min_point.y, first.max_point.y, second.min_point.y, second.max_point.y)
    gap_z = _axis_gap(first.min_point.z, first.max_point.z, second.min_point.z, second.max_point.z)
    return sqrt(gap_x * gap_x + gap_y * gap_y + gap_z * gap_z)


def is_intersecting(first: BBox, second: BBox, intersection_epsilon: float) -> bool:
    overlap_x = _axis_overlap(first.min_point.x, first.max_point.x, second.min_point.x, second.max_point.x)
    overlap_y = _axis_overlap(first.min_point.y, first.max_point.y, second.min_point.y, second.max_point.y)
    overlap_z = _axis_overlap(first.min_point.z, first.max_point.z, second.min_point.z, second.max_point.z)
    return (
        overlap_x > intersection_epsilon
        and overlap_y > intersection_epsilon
        and overlap_z > intersection_epsilon
    )


def infer_spatial_relation(
    first: BBox | None,
    second: BBox | None,
    *,
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
) -> tuple[RelationType | None, dict[str, object]]:
    if first is None or second is None:
        return None, {}

    distance = bbox_distance(first, second)
    intersects = is_intersecting(first, second, intersection_epsilon=intersection_epsilon)

    relation: RelationType | None = None
    confidence = 0.0

    if intersects:
        relation = RelationType.INTERSECTS
        confidence = 0.95
    elif distance <= touch_epsilon:
        relation = RelationType.TOUCHES
        confidence = 0.90
    elif touch_epsilon < distance <= adjacent_epsilon:
        relation = RelationType.ADJACENT_TO
        confidence = 0.80

    if relation is None:
        return None, {}

    return relation, {
        "method": "bbox_aabb_v1",
        "distance": round(distance, 6),
        "epsilon_touch": touch_epsilon,
        "epsilon_adjacent": adjacent_epsilon,
        "epsilon_intersection": intersection_epsilon,
        "confidence": confidence,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
