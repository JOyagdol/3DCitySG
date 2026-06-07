"""Spatial relation inference helpers based on AABB distances."""

from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt

from citygml_sg.domain.bbox import BBox
from citygml_sg.domain.geometry import Point3D
from citygml_sg.domain.enums import RelationType


def _axis_gap(min_a: float, max_a: float, min_b: float, max_b: float) -> float:
    if max_a < min_b:
        return min_b - max_a
    if max_b < min_a:
        return min_a - max_b
    return 0.0


def _axis_overlap(min_a: float, max_a: float, min_b: float, max_b: float) -> float:
    return min(max_a, max_b) - max(min_a, min_b)


def _touch_contact_guard(
    first: BBox,
    second: BBox,
    *,
    distance: float,
    intersection_epsilon: float,
    min_contact_area: float | None,
    min_contact_length: float | None,
    demoted_from_intersection: bool,
) -> tuple[bool, dict[str, object]]:
    if demoted_from_intersection:
        return (
            False,
            {
                "touch_contact_dimension": 3,
                "touch_contact_area": None,
                "touch_contact_length": None,
                "touch_guard_reason": "demoted_intersection_candidate",
            },
        )

    if distance > intersection_epsilon:
        return (
            True,
            {
                "touch_contact_dimension": None,
                "touch_contact_area": None,
                "touch_contact_length": None,
                "touch_guard_reason": "gap_within_touch_epsilon",
            },
        )

    overlap_x = max(0.0, _axis_overlap(first.min_point.x, first.max_point.x, second.min_point.x, second.max_point.x))
    overlap_y = max(0.0, _axis_overlap(first.min_point.y, first.max_point.y, second.min_point.y, second.max_point.y))
    overlap_z = max(0.0, _axis_overlap(first.min_point.z, first.max_point.z, second.min_point.z, second.max_point.z))
    positive_overlaps = [value for value in (overlap_x, overlap_y, overlap_z) if value > intersection_epsilon]
    dim = len(positive_overlaps)

    if dim == 2:
        area = positive_overlaps[0] * positive_overlaps[1]
        min_area = float(min_contact_area or 0.0)
        return (
            area >= min_area,
            {
                "touch_contact_dimension": 2,
                "touch_contact_area": round(area, 6),
                "touch_contact_length": None,
                "touch_guard_reason": "face_contact" if area >= min_area else "face_contact_too_small",
            },
        )

    if dim == 1:
        length = positive_overlaps[0]
        min_length = float(min_contact_length or 0.0)
        return (
            length >= min_length,
            {
                "touch_contact_dimension": 1,
                "touch_contact_area": None,
                "touch_contact_length": round(length, 6),
                "touch_guard_reason": "edge_contact" if length >= min_length else "edge_contact_too_small",
            },
        )

    return (
        False,
        {
            "touch_contact_dimension": dim,
            "touch_contact_area": None,
            "touch_contact_length": None,
            "touch_guard_reason": "point_contact_or_no_contact",
        },
    )


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


def _normalize_axis_2d(x: float, y: float) -> tuple[float, float] | None:
    norm = sqrt(x * x + y * y)
    if norm <= 1e-12:
        return None
    return (x / norm, y / norm)


def _axis_interval_2d(points: list[tuple[float, float]], axis: tuple[float, float]) -> tuple[float, float]:
    first_projection = points[0][0] * axis[0] + points[0][1] * axis[1]
    min_value = first_projection
    max_value = first_projection
    for x, y in points[1:]:
        projection = x * axis[0] + y * axis[1]
        min_value = min(min_value, projection)
        max_value = max(max_value, projection)
    return min_value, max_value


def _sat_overlap_2d(
    first_points: list[tuple[float, float]],
    second_points: list[tuple[float, float]],
    axes: list[tuple[float, float]],
    *,
    epsilon: float,
) -> bool:
    for axis in axes:
        first_min, first_max = _axis_interval_2d(first_points, axis)
        second_min, second_max = _axis_interval_2d(second_points, axis)
        overlap = min(first_max, second_max) - max(first_min, second_min)
        if overlap <= epsilon:
            return False
    return True


def _xy_points(points: list[Point3D] | None) -> list[tuple[float, float]]:
    if not points:
        return []
    unique: set[tuple[float, float]] = set()
    ordered: list[tuple[float, float]] = []
    for point in points:
        xy = (float(point.x), float(point.y))
        if xy in unique:
            continue
        unique.add(xy)
        ordered.append(xy)
    return ordered


def _convex_hull_xy(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    sorted_points = sorted(points)
    if len(sorted_points) <= 1:
        return sorted_points

    def cross(origin: tuple[float, float], first: tuple[float, float], second: tuple[float, float]) -> float:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (second[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in sorted_points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(sorted_points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)

    return lower[:-1] + upper[:-1]


def _obb_axes_xy(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not points:
        return []
    if len(points) == 1:
        return [(1.0, 0.0), (0.0, 1.0)]

    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)
    centered = [(x - mean_x, y - mean_y) for x, y in points]
    cov_xx = sum(x * x for x, _ in centered) / len(centered)
    cov_xy = sum(x * y for x, y in centered) / len(centered)
    cov_yy = sum(y * y for _, y in centered) / len(centered)

    trace = cov_xx + cov_yy
    det = cov_xx * cov_yy - cov_xy * cov_xy
    temp = sqrt(max(0.0, trace * trace * 0.25 - det))
    principal_eigen = trace * 0.5 + temp

    vx = cov_xy
    vy = principal_eigen - cov_xx
    primary = _normalize_axis_2d(vx, vy)
    if primary is None:
        primary = (1.0, 0.0)
    secondary = (-primary[1], primary[0])
    return [primary, secondary]


def _polygon_axes_xy(hull: list[tuple[float, float]]) -> list[tuple[float, float]]:
    axes: list[tuple[float, float]] = []
    if len(hull) < 2:
        return axes
    for index in range(len(hull)):
        current = hull[index]
        nxt = hull[(index + 1) % len(hull)]
        edge_x = nxt[0] - current[0]
        edge_y = nxt[1] - current[1]
        normal = _normalize_axis_2d(-edge_y, edge_x)
        if normal is None:
            continue
        axes.append(normal)
    return axes


def _refine_intersection_with_obb_polygon(
    first_bbox: BBox,
    second_bbox: BBox,
    first_points: list[Point3D] | None,
    second_points: list[Point3D] | None,
    *,
    intersection_epsilon: float,
) -> tuple[bool, dict[str, object]]:
    first_xy = _xy_points(first_points)
    second_xy = _xy_points(second_points)
    if len(first_xy) < 3 or len(second_xy) < 3:
        return (
            True,
            {
                "stage2_refinement": "skipped_insufficient_points",
                "stage2_obb_overlap": None,
                "stage2_polygon_overlap": None,
            },
        )

    first_hull = _convex_hull_xy(first_xy)
    second_hull = _convex_hull_xy(second_xy)

    obb_axes = _obb_axes_xy(first_xy) + _obb_axes_xy(second_xy)
    obb_overlap = _sat_overlap_2d(first_xy, second_xy, obb_axes, epsilon=intersection_epsilon)

    polygon_axes = _polygon_axes_xy(first_hull) + _polygon_axes_xy(second_hull)
    polygon_overlap = _sat_overlap_2d(first_hull, second_hull, polygon_axes, epsilon=intersection_epsilon)

    overlap_z = _axis_overlap(first_bbox.min_point.z, first_bbox.max_point.z, second_bbox.min_point.z, second_bbox.max_point.z)
    z_overlap_ok = overlap_z > intersection_epsilon

    return (
        obb_overlap and polygon_overlap and z_overlap_ok,
        {
            "stage2_refinement": "obb_polygon_v2",
            "stage2_obb_overlap": obb_overlap,
            "stage2_polygon_overlap": polygon_overlap,
            "stage2_z_overlap": round(float(overlap_z), 6),
        },
    )


def infer_spatial_relation(
    first: BBox | None,
    second: BBox | None,
    *,
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
    first_points: list[Point3D] | None = None,
    second_points: list[Point3D] | None = None,
    use_two_stage_refinement: bool = False,
    touch_min_contact_area: float | None = None,
    touch_min_contact_length: float | None = None,
) -> tuple[RelationType | None, dict[str, object]]:
    if first is None or second is None:
        return None, {}

    distance = bbox_distance(first, second)
    intersects = is_intersecting(first, second, intersection_epsilon=intersection_epsilon)
    intersects_stage1 = intersects

    relation: RelationType | None = None
    confidence = 0.0

    stage2_props: dict[str, object] = {}
    if intersects and use_two_stage_refinement:
        refined_intersects, stage2_props = _refine_intersection_with_obb_polygon(
            first,
            second,
            first_points,
            second_points,
            intersection_epsilon=intersection_epsilon,
        )
        intersects = refined_intersects

    touch_guard_props: dict[str, object] = {}
    touch_allowed = True
    if not intersects and distance <= touch_epsilon:
        touch_allowed, touch_guard_props = _touch_contact_guard(
            first,
            second,
            distance=distance,
            intersection_epsilon=intersection_epsilon,
            min_contact_area=touch_min_contact_area,
            min_contact_length=touch_min_contact_length,
            demoted_from_intersection=bool(intersects_stage1 and not intersects),
        )

    if intersects:
        relation = RelationType.INTERSECTS
        confidence = 0.95
    elif distance <= touch_epsilon and touch_allowed:
        relation = RelationType.TOUCHES
        confidence = 0.90
    elif (touch_epsilon < distance <= adjacent_epsilon) or (distance <= touch_epsilon and not touch_allowed):
        relation = RelationType.ADJACENT_TO
        confidence = 0.80

    if relation is None:
        return None, {}

    distance_norm = 0.0
    if adjacent_epsilon > 1e-12:
        distance_norm = max(0.0, min(1.0, 1.0 - (distance / adjacent_epsilon)))

    evidence_score = confidence
    if relation == RelationType.INTERSECTS:
        stage2_polygon = stage2_props.get("stage2_polygon_overlap")
        if stage2_polygon is True:
            evidence_score = 0.98
        elif stage2_polygon is False:
            evidence_score = 0.92
        else:
            evidence_score = 0.95
    elif relation == RelationType.TOUCHES:
        touch_dim = touch_guard_props.get("touch_contact_dimension")
        if touch_dim == 2:
            evidence_score = 0.93
        elif touch_dim == 1:
            evidence_score = 0.88
        elif touch_dim == 3:
            evidence_score = 0.85
        else:
            evidence_score = 0.80 + 0.10 * distance_norm
    elif relation == RelationType.ADJACENT_TO:
        evidence_score = 0.60 + 0.30 * distance_norm

    props: dict[str, object] = {
        "method": "bbox_aabb_v1",
        "distance": round(distance, 6),
        "epsilon_touch": touch_epsilon,
        "epsilon_adjacent": adjacent_epsilon,
        "epsilon_intersection": intersection_epsilon,
        "confidence": confidence,
        "evidence_score": round(float(evidence_score), 4),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    if use_two_stage_refinement:
        props.update(stage2_props)
    if touch_guard_props:
        props.update(touch_guard_props)
    props["touch_min_contact_area"] = touch_min_contact_area
    props["touch_min_contact_length"] = touch_min_contact_length
    return relation, props
