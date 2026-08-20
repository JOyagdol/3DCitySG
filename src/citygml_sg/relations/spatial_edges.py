"""Spatial relation edge construction for CityGML scene graphs."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Iterator

from citygml_sg.domain.bbox import BBox
from citygml_sg.domain.edge import Edge
from citygml_sg.domain.enums import NodeType, RelationType
from citygml_sg.domain.geometry import Point3D
from citygml_sg.domain.node import Node
from citygml_sg.graph.edge_factory import create_edge
from citygml_sg.graph.graph_builder import SceneGraph
from citygml_sg.relations.spatial_inference import infer_spatial_relation
from citygml_sg.relations.spatial_priority import normalize_spatial_precedence
from citygml_sg.relations.spatial_scope import (
    FLOOR_LIKE_SURFACE_TYPES,
    WALL_LIKE_SURFACE_TYPES,
    bbox_xy_overlaps,
    boundary_plane_axis,
    build_room_spatial_scope,
)
from citygml_sg.utils.logging import get_logger

LOGGER = get_logger(__name__)

DEFAULT_ATTACHMENT_VERTICAL_GAP_EPSILON = 0.10
DEFAULT_TOUCH_MIN_CONTACT_AREA = 0.01
DEFAULT_TOUCH_MIN_CONTACT_LENGTH = 0.10
DEFAULT_ADJACENT_SURFACE_MIN_SHARED_EDGE_LENGTH = 0.10
DEFAULT_ADJACENT_SURFACE_EDGE_LINE_TOLERANCE = 0.01
VERTICAL_RELATION_OBJECT_TYPES: set[NodeType] = {NodeType.BUILDING_FURNITURE, NodeType.OPENING}
EXTERNAL_FLAG_KEYS: tuple[str, ...] = (
    "is_external",
    "attr_pset_wallcommon_isexternal",
    "attr_pset_buildingelementproxycommon_isexternal",
)

EdgeIndexFn = Callable[[SceneGraph, RelationType], dict[str, list[str]]]
NodeBboxBuilder = Callable[..., dict[str, BBox]]
NodePointBuilder = Callable[..., dict[str, list[Point3D]]]
NodeRingBuilder = Callable[..., dict[str, list[list[Point3D]]]]
EdgeAdder = Callable[[SceneGraph, Edge], None]
NodeFilter = Callable[[Node], bool]


def _add_spatial_edges_for_pairs(
    graph: SceneGraph,
    source_ids: list[str],
    target_ids: list[str],
    *,
    nodes_by_id: dict[str, Node],
    node_bboxes: dict[str, BBox],
    node_points: dict[str, list[Point3D]],
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
    use_two_stage_refinement: bool,
    add_edge_if_valid: EdgeAdder,
    room_boundary_ids: list[str] | None = None,
    touch_min_contact_area: float = DEFAULT_TOUCH_MIN_CONTACT_AREA,
    touch_min_contact_length: float = DEFAULT_TOUCH_MIN_CONTACT_LENGTH,
) -> int:
    added = 0
    for source_id in source_ids:
        source_bbox = node_bboxes.get(source_id)
        if source_bbox is None:
            continue
        for target_id in target_ids:
            if source_id == target_id:
                continue
            target_bbox = node_bboxes.get(target_id)
            relation, props = infer_spatial_relation(
                source_bbox,
                target_bbox,
                touch_epsilon=touch_epsilon,
                adjacent_epsilon=adjacent_epsilon,
                intersection_epsilon=intersection_epsilon,
                first_points=node_points.get(source_id),
                second_points=node_points.get(target_id),
                use_two_stage_refinement=use_two_stage_refinement,
                touch_min_contact_area=touch_min_contact_area,
                touch_min_contact_length=touch_min_contact_length,
            )
            if relation is None:
                continue
            if relation == RelationType.ADJACENT_TO and room_boundary_ids:
                source_node = nodes_by_id.get(source_id)
                target_node = nodes_by_id.get(target_id)
                if source_node is None or target_node is None:
                    continue
                if (
                    source_node.node_type != NodeType.BOUNDARY_SURFACE
                    and target_node.node_type != NodeType.BOUNDARY_SURFACE
                    and _has_boundary_occlusion_between(
                        source_id,
                        target_id,
                        source_bbox,
                        target_bbox,
                        room_boundary_ids=room_boundary_ids,
                        node_bboxes=node_bboxes,
                        touch_epsilon=touch_epsilon,
                    )
                ):
                    continue
            before = len(graph.edges)
            add_edge_if_valid(graph, create_edge(source_id, target_id, relation, **props))
            if len(graph.edges) > before:
                added += 1
    return added


def _point_distance(first: Point3D, second: Point3D) -> float:
    dx = first.x - second.x
    dy = first.y - second.y
    dz = first.z - second.z
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def _segment_points(ring: list[Point3D]) -> Iterator[tuple[Point3D, Point3D]]:
    if len(ring) < 2:
        return
    for index in range(len(ring) - 1):
        if _point_distance(ring[index], ring[index + 1]) > 1e-12:
            yield ring[index], ring[index + 1]
    if _point_distance(ring[0], ring[-1]) > 1e-12:
        yield ring[-1], ring[0]


def _segment_shared_length(
    first_start: Point3D,
    first_end: Point3D,
    second_start: Point3D,
    second_end: Point3D,
    *,
    line_tolerance: float,
) -> float:
    ux = first_end.x - first_start.x
    uy = first_end.y - first_start.y
    uz = first_end.z - first_start.z
    vx = second_end.x - second_start.x
    vy = second_end.y - second_start.y
    vz = second_end.z - second_start.z
    first_length = (ux * ux + uy * uy + uz * uz) ** 0.5
    second_length = (vx * vx + vy * vy + vz * vz) ** 0.5
    if first_length <= 1e-12 or second_length <= 1e-12:
        return 0.0

    cross_uv_x = uy * vz - uz * vy
    cross_uv_y = uz * vx - ux * vz
    cross_uv_z = ux * vy - uy * vx
    parallel_error = (
        cross_uv_x * cross_uv_x
        + cross_uv_y * cross_uv_y
        + cross_uv_z * cross_uv_z
    ) ** 0.5
    if parallel_error > line_tolerance * first_length * second_length:
        return 0.0

    dir_x = ux / first_length
    dir_y = uy / first_length
    dir_z = uz / first_length

    def point_line_distance(point: Point3D) -> float:
        wx = point.x - first_start.x
        wy = point.y - first_start.y
        wz = point.z - first_start.z
        cross_x = wy * dir_z - wz * dir_y
        cross_y = wz * dir_x - wx * dir_z
        cross_z = wx * dir_y - wy * dir_x
        return (cross_x * cross_x + cross_y * cross_y + cross_z * cross_z) ** 0.5

    if (
        point_line_distance(second_start) > line_tolerance
        or point_line_distance(second_end) > line_tolerance
    ):
        return 0.0

    def project(point: Point3D) -> float:
        return (
            (point.x - first_start.x) * dir_x
            + (point.y - first_start.y) * dir_y
            + (point.z - first_start.z) * dir_z
        )

    first_min, first_max = 0.0, first_length
    second_a = project(second_start)
    second_b = project(second_end)
    second_min = min(second_a, second_b)
    second_max = max(second_a, second_b)
    return max(0.0, min(first_max, second_max) - max(first_min, second_min))


def _boundary_shared_edge_length(
    first_rings: list[list[Point3D]] | None,
    second_rings: list[list[Point3D]] | None,
    *,
    line_tolerance: float,
) -> float:
    if not first_rings or not second_rings:
        return 0.0
    max_shared_length = 0.0
    for first_ring in first_rings:
        for first_start, first_end in _segment_points(first_ring):
            for second_ring in second_rings:
                for second_start, second_end in _segment_points(second_ring):
                    max_shared_length = max(
                        max_shared_length,
                        _segment_shared_length(
                            first_start,
                            first_end,
                            second_start,
                            second_end,
                            line_tolerance=line_tolerance,
                        ),
                    )
    return max_shared_length


def _bbox_centroid(bbox: BBox) -> Point3D:
    return Point3D(
        (bbox.min_point.x + bbox.max_point.x) / 2.0,
        (bbox.min_point.y + bbox.max_point.y) / 2.0,
        (bbox.min_point.z + bbox.max_point.z) / 2.0,
    )


def _is_true_like(value: object) -> bool:
    text = str(value).strip().lower()
    return text in {"true", "yes", "y", "1"}


def _is_external_boundary_surface(node: Node | None) -> bool:
    if node is None or node.node_type != NodeType.BOUNDARY_SURFACE:
        return False
    for key in EXTERNAL_FLAG_KEYS:
        if key not in node.properties:
            continue
        if _is_true_like(node.properties.get(key)):
            return True
    return False


def _segment_intersects_bbox(
    start: Point3D,
    end: Point3D,
    bbox: BBox,
    *,
    expand_epsilon: float = 0.0,
) -> bool:
    min_x = float(bbox.min_point.x) - expand_epsilon
    min_y = float(bbox.min_point.y) - expand_epsilon
    min_z = float(bbox.min_point.z) - expand_epsilon
    max_x = float(bbox.max_point.x) + expand_epsilon
    max_y = float(bbox.max_point.y) + expand_epsilon
    max_z = float(bbox.max_point.z) + expand_epsilon

    dx = float(end.x - start.x)
    dy = float(end.y - start.y)
    dz = float(end.z - start.z)

    t_min = 0.0
    t_max = 1.0
    for start_value, delta, min_value, max_value in (
        (float(start.x), dx, min_x, max_x),
        (float(start.y), dy, min_y, max_y),
        (float(start.z), dz, min_z, max_z),
    ):
        if abs(delta) < 1e-12:
            if start_value < min_value or start_value > max_value:
                return False
            continue
        inv = 1.0 / delta
        t1 = (min_value - start_value) * inv
        t2 = (max_value - start_value) * inv
        if t1 > t2:
            t1, t2 = t2, t1
        t_min = max(t_min, t1)
        t_max = min(t_max, t2)
        if t_min > t_max:
            return False
    return True


def _has_boundary_occlusion_between(
    source_id: str,
    target_id: str,
    source_bbox: BBox,
    target_bbox: BBox,
    *,
    room_boundary_ids: list[str],
    node_bboxes: dict[str, BBox],
    touch_epsilon: float,
) -> bool:
    start = _bbox_centroid(source_bbox)
    end = _bbox_centroid(target_bbox)
    for boundary_id in room_boundary_ids:
        if boundary_id == source_id or boundary_id == target_id:
            continue
        boundary_bbox = node_bboxes.get(boundary_id)
        if boundary_bbox is None:
            continue
        if _segment_intersects_bbox(start, end, boundary_bbox, expand_epsilon=touch_epsilon):
            return True
    return False


def _infer_vertical_relation(
    first: BBox | None,
    second: BBox | None,
    *,
    touch_epsilon: float,
    intersection_epsilon: float,
) -> tuple[RelationType | None, dict[str, object]]:
    if first is None or second is None:
        return None, {}
    if not bbox_xy_overlaps(first, second, intersection_epsilon=intersection_epsilon):
        return None, {}

    first_bottom = first.min_point.z
    first_top = first.max_point.z
    second_bottom = second.min_point.z
    second_top = second.max_point.z

    if first_bottom >= second_top + touch_epsilon:
        gap = first_bottom - second_top
        return (
            RelationType.ABOVE,
            {
                "method": "bbox_vertical_v1",
                "distance": round(gap, 6),
                "epsilon_touch": touch_epsilon,
                "epsilon_adjacent": 0.0,
                "epsilon_intersection": intersection_epsilon,
                "confidence": 0.85,
                "evidence_score": round(max(0.70, 0.90 - min(0.20, gap / 10.0)), 4),
                "computed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    if second_bottom >= first_top + touch_epsilon:
        gap = second_bottom - first_top
        return (
            RelationType.BELOW,
            {
                "method": "bbox_vertical_v1",
                "distance": round(gap, 6),
                "epsilon_touch": touch_epsilon,
                "epsilon_adjacent": 0.0,
                "epsilon_intersection": intersection_epsilon,
                "confidence": 0.85,
                "evidence_score": round(max(0.70, 0.90 - min(0.20, gap / 10.0)), 4),
                "computed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    return None, {}


def build_spatial_edges(
    graph: SceneGraph,
    *,
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
    edge_index: EdgeIndexFn,
    build_node_bboxes: NodeBboxBuilder,
    build_node_points: NodePointBuilder,
    build_node_polygon_rings: NodeRingBuilder,
    add_edge_if_valid: EdgeAdder,
    is_door_or_window_opening: NodeFilter,
) -> int:
    edge_count_before = len(graph.edges)
    nodes_by_id = graph.nodes
    room_to_furniture, room_to_boundary, room_to_opening, scope_stats = build_room_spatial_scope(
        graph,
        include_container_fallback=True,
        collapse_layered_fallback=True,
        edge_index=edge_index,
        build_node_bboxes=build_node_bboxes,
        is_door_or_window_opening=is_door_or_window_opening,
    )
    if scope_stats["fallback_room_count"] > 0:
        LOGGER.info(
            "[SpatialScope] room boundary fallback used: "
            "rooms=%d raw_links=%d collapsed_links=%d reduced=%d",
            scope_stats["fallback_room_count"],
            scope_stats["fallback_boundary_link_count"],
            scope_stats["fallback_boundary_collapsed_link_count"],
            scope_stats["fallback_boundary_reduced_link_count"],
        )

    target_types = {NodeType.BUILDING_FURNITURE, NodeType.BOUNDARY_SURFACE, NodeType.OPENING}
    node_bboxes = build_node_bboxes(graph, target_types=target_types)
    node_points = build_node_points(graph, target_types=target_types)
    boundary_polygon_rings = build_node_polygon_rings(
        graph,
        target_types={NodeType.BOUNDARY_SURFACE},
    )

    for _room_id, furniture_ids in room_to_furniture.items():
        unique_furniture_ids = sorted(set(furniture_ids))
        if not unique_furniture_ids:
            continue

        boundary_ids = sorted(set(room_to_boundary.get(_room_id, [])))
        opening_ids = sorted(set(room_to_opening.get(_room_id, [])))

        _add_spatial_edges_for_pairs(
            graph,
            unique_furniture_ids,
            boundary_ids,
            nodes_by_id=nodes_by_id,
            node_bboxes=node_bboxes,
            node_points=node_points,
            touch_epsilon=touch_epsilon,
            adjacent_epsilon=adjacent_epsilon,
            intersection_epsilon=intersection_epsilon,
            use_two_stage_refinement=True,
            add_edge_if_valid=add_edge_if_valid,
            room_boundary_ids=boundary_ids,
        )
        _add_spatial_edges_for_pairs(
            graph,
            boundary_ids,
            unique_furniture_ids,
            nodes_by_id=nodes_by_id,
            node_bboxes=node_bboxes,
            node_points=node_points,
            touch_epsilon=touch_epsilon,
            adjacent_epsilon=adjacent_epsilon,
            intersection_epsilon=intersection_epsilon,
            use_two_stage_refinement=True,
            add_edge_if_valid=add_edge_if_valid,
            room_boundary_ids=boundary_ids,
        )
        _add_spatial_edges_for_pairs(
            graph,
            unique_furniture_ids,
            opening_ids,
            nodes_by_id=nodes_by_id,
            node_bboxes=node_bboxes,
            node_points=node_points,
            touch_epsilon=touch_epsilon,
            adjacent_epsilon=adjacent_epsilon,
            intersection_epsilon=intersection_epsilon,
            use_two_stage_refinement=True,
            add_edge_if_valid=add_edge_if_valid,
            room_boundary_ids=boundary_ids,
        )
        _add_spatial_edges_for_pairs(
            graph,
            opening_ids,
            unique_furniture_ids,
            nodes_by_id=nodes_by_id,
            node_bboxes=node_bboxes,
            node_points=node_points,
            touch_epsilon=touch_epsilon,
            adjacent_epsilon=adjacent_epsilon,
            intersection_epsilon=intersection_epsilon,
            use_two_stage_refinement=True,
            add_edge_if_valid=add_edge_if_valid,
            room_boundary_ids=boundary_ids,
        )

        for i in range(len(unique_furniture_ids)):
            for j in range(i + 1, len(unique_furniture_ids)):
                first_id = unique_furniture_ids[i]
                second_id = unique_furniture_ids[j]
                _add_spatial_edges_for_pairs(
                    graph,
                    [first_id],
                    [second_id],
                    nodes_by_id=nodes_by_id,
                    node_bboxes=node_bboxes,
                    node_points=node_points,
                    touch_epsilon=touch_epsilon,
                    adjacent_epsilon=adjacent_epsilon,
                    intersection_epsilon=intersection_epsilon,
                    use_two_stage_refinement=True,
                    add_edge_if_valid=add_edge_if_valid,
                    room_boundary_ids=boundary_ids,
                )
                _add_spatial_edges_for_pairs(
                    graph,
                    [second_id],
                    [first_id],
                    nodes_by_id=nodes_by_id,
                    node_bboxes=node_bboxes,
                    node_points=node_points,
                    touch_epsilon=touch_epsilon,
                    adjacent_epsilon=adjacent_epsilon,
                    intersection_epsilon=intersection_epsilon,
                    use_two_stage_refinement=True,
                    add_edge_if_valid=add_edge_if_valid,
                    room_boundary_ids=boundary_ids,
                )

    processed_boundary_pairs: set[tuple[str, str]] = set()
    for boundary_ids in room_to_boundary.values():
        unique_boundary_ids = sorted(set(boundary_ids))
        for i in range(len(unique_boundary_ids)):
            for j in range(i + 1, len(unique_boundary_ids)):
                first_id = unique_boundary_ids[i]
                second_id = unique_boundary_ids[j]
                pair_key = tuple(sorted((first_id, second_id)))
                if pair_key in processed_boundary_pairs:
                    continue
                processed_boundary_pairs.add(pair_key)

                first_bbox = node_bboxes.get(first_id)
                second_bbox = node_bboxes.get(second_id)
                if first_bbox is None or second_bbox is None:
                    continue
                first_node = nodes_by_id.get(first_id)
                second_node = nodes_by_id.get(second_id)
                first_surface_type = str(
                    (first_node.properties.get("surface_type") if first_node else "") or ""
                )
                second_surface_type = str(
                    (second_node.properties.get("surface_type") if second_node else "") or ""
                )
                wall_pair = (
                    first_surface_type in WALL_LIKE_SURFACE_TYPES
                    and second_surface_type in WALL_LIKE_SURFACE_TYPES
                )
                if wall_pair:
                    # Keep wall-wall adjacency conservative: only exterior-wall pairs.
                    if not (
                        _is_external_boundary_surface(first_node)
                        and _is_external_boundary_surface(second_node)
                    ):
                        continue
                    # Suppress parallel layered wall pairs; keep corner-like junctions.
                    if boundary_plane_axis(first_bbox) == boundary_plane_axis(second_bbox):
                        continue
                relation, props = infer_spatial_relation(
                    first_bbox,
                    second_bbox,
                    touch_epsilon=touch_epsilon,
                    adjacent_epsilon=adjacent_epsilon,
                    intersection_epsilon=intersection_epsilon,
                    first_points=node_points.get(first_id),
                    second_points=node_points.get(second_id),
                    use_two_stage_refinement=True,
                    touch_min_contact_area=DEFAULT_TOUCH_MIN_CONTACT_AREA,
                    touch_min_contact_length=DEFAULT_TOUCH_MIN_CONTACT_LENGTH,
                )
                if relation is None:
                    continue
                if relation not in {RelationType.TOUCHES, RelationType.INTERSECTS}:
                    continue
                shared_edge_length = _boundary_shared_edge_length(
                    boundary_polygon_rings.get(first_id),
                    boundary_polygon_rings.get(second_id),
                    line_tolerance=DEFAULT_ADJACENT_SURFACE_EDGE_LINE_TOLERANCE,
                )
                if shared_edge_length < DEFAULT_ADJACENT_SURFACE_MIN_SHARED_EDGE_LENGTH:
                    continue

                base_props = dict(props)
                base_props["basis_relation"] = relation.value
                base_props["shared_edge_length"] = round(shared_edge_length, 6)
                base_props[
                    "min_shared_edge_length"
                ] = DEFAULT_ADJACENT_SURFACE_MIN_SHARED_EDGE_LENGTH
                base_props[
                    "shared_edge_line_tolerance"
                ] = DEFAULT_ADJACENT_SURFACE_EDGE_LINE_TOLERANCE
                base_props["adjacent_surface_method"] = "polygon_shared_edge_v1"
                add_edge_if_valid(
                    graph,
                    create_edge(first_id, second_id, RelationType.ADJACENT_SURFACE, **base_props),
                )
                add_edge_if_valid(
                    graph,
                    create_edge(second_id, first_id, RelationType.ADJACENT_SURFACE, **base_props),
                )

    processed_vertical_pairs: set[tuple[str, str]] = set()
    for room_id in sorted(set(room_to_furniture.keys()) | set(room_to_opening.keys())):
        candidate_ids = sorted(
            set(room_to_furniture.get(room_id, []) + room_to_opening.get(room_id, []))
        )
        scoped_ids: list[str] = []
        for node_id in candidate_ids:
            node = nodes_by_id.get(node_id)
            if node is None or node.node_type not in VERTICAL_RELATION_OBJECT_TYPES:
                continue
            if node.node_type == NodeType.OPENING and not is_door_or_window_opening(node):
                continue
            if node_id not in node_bboxes:
                continue
            scoped_ids.append(node_id)

        for i in range(len(scoped_ids)):
            for j in range(i + 1, len(scoped_ids)):
                first_id = scoped_ids[i]
                second_id = scoped_ids[j]
                pair_key = tuple(sorted((first_id, second_id)))
                if pair_key in processed_vertical_pairs:
                    continue
                processed_vertical_pairs.add(pair_key)

                relation, props = _infer_vertical_relation(
                    node_bboxes.get(first_id),
                    node_bboxes.get(second_id),
                    touch_epsilon=touch_epsilon,
                    intersection_epsilon=intersection_epsilon,
                )
                if relation is None:
                    continue

                inverse_relation = (
                    RelationType.BELOW if relation == RelationType.ABOVE else RelationType.ABOVE
                )
                add_edge_if_valid(graph, create_edge(first_id, second_id, relation, **props))
                add_edge_if_valid(
                    graph,
                    create_edge(second_id, first_id, inverse_relation, **props),
                )

    normalized_edges, removed = normalize_spatial_precedence(graph.edges)
    if removed > 0:
        graph.replace_edges(normalized_edges)
        LOGGER.info(
            "[Spatial] precedence normalization applied: "
            "removed_weaker_edges=%d rule=INTERSECTS>TOUCHES>ADJACENT_TO",
            removed,
        )

    attached_candidates: dict[tuple[str, str], dict[str, object]] = {}
    for edge in graph.edges:
        if edge.relation != RelationType.TOUCHES:
            continue
        source_node = nodes_by_id.get(edge.source_id)
        target_node = nodes_by_id.get(edge.target_id)
        if source_node is None or target_node is None:
            continue

        furniture_id: str | None = None
        boundary_id: str | None = None
        if (
            source_node.node_type == NodeType.BUILDING_FURNITURE
            and target_node.node_type == NodeType.BOUNDARY_SURFACE
        ):
            furniture_id = edge.source_id
            boundary_id = edge.target_id
        elif (
            source_node.node_type == NodeType.BOUNDARY_SURFACE
            and target_node.node_type == NodeType.BUILDING_FURNITURE
        ):
            furniture_id = edge.target_id
            boundary_id = edge.source_id
        if furniture_id is None or boundary_id is None:
            continue
        attached_candidates[(furniture_id, boundary_id)] = {
            "method": "touch_attachment_v1",
            "source": "touches_relation",
            "confidence": 0.9,
            "evidence_score": 0.9,
        }

    attachment_gap_epsilon = max(float(touch_epsilon), DEFAULT_ATTACHMENT_VERTICAL_GAP_EPSILON)
    for room_id, furniture_ids in room_to_furniture.items():
        unique_furniture_ids = sorted(set(furniture_ids))
        boundary_ids = sorted(set(room_to_boundary.get(room_id, [])))
        for furniture_id in unique_furniture_ids:
            furniture_bbox = node_bboxes.get(furniture_id)
            if furniture_bbox is None:
                continue
            for boundary_id in boundary_ids:
                boundary_node = nodes_by_id.get(boundary_id)
                if boundary_node is None or boundary_node.node_type != NodeType.BOUNDARY_SURFACE:
                    continue
                surface_type = str(boundary_node.properties.get("surface_type") or "")
                if surface_type not in FLOOR_LIKE_SURFACE_TYPES:
                    continue
                boundary_bbox = node_bboxes.get(boundary_id)
                if boundary_bbox is None:
                    continue
                if not bbox_xy_overlaps(
                    furniture_bbox,
                    boundary_bbox,
                    intersection_epsilon=intersection_epsilon,
                ):
                    continue
                vertical_gap = abs(
                    float(furniture_bbox.min_point.z) - float(boundary_bbox.max_point.z)
                )
                if vertical_gap > attachment_gap_epsilon:
                    continue
                pair_key = (furniture_id, boundary_id)
                if pair_key in attached_candidates:
                    continue
                attached_candidates[pair_key] = {
                    "method": "floor_contact_gap_v2",
                    "source": "floor_vertical_gap",
                    "vertical_gap": round(vertical_gap, 6),
                    "vertical_gap_epsilon": round(attachment_gap_epsilon, 6),
                    "confidence": 0.85,
                    "evidence_score": round(
                        max(
                            0.75,
                            0.92
                            - min(
                                0.15,
                                vertical_gap / max(attachment_gap_epsilon, 1e-9) * 0.15,
                            ),
                        ),
                        4,
                    ),
                }

    for furniture_id, boundary_id in sorted(attached_candidates):
        boundary_node = nodes_by_id.get(boundary_id)
        boundary_surface_type = "BoundarySurface"
        if boundary_node is not None:
            boundary_surface_type = str(
                boundary_node.properties.get("surface_type") or "BoundarySurface"
            )
        attachment_props = attached_candidates[(furniture_id, boundary_id)]
        add_edge_if_valid(
            graph,
            create_edge(
                furniture_id,
                boundary_id,
                RelationType.ATTACHED_TO,
                method=str(attachment_props.get("method") or "touch_attachment_v1"),
                source=str(attachment_props.get("source") or "touches_relation"),
                boundary_surface_type=boundary_surface_type,
                confidence=float(attachment_props.get("confidence") or 0.9),
                evidence_score=float(
                    attachment_props.get("evidence_score")
                    or attachment_props.get("confidence")
                    or 0.9
                ),
                vertical_gap=attachment_props.get("vertical_gap"),
                vertical_gap_epsilon=attachment_props.get("vertical_gap_epsilon"),
                computed_at=datetime.now(timezone.utc).isoformat(),
            ),
        )

    return len(graph.edges) - edge_count_before


def _reverse_edge_index(
    graph: SceneGraph,
    relations: set[RelationType],
) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        if edge.relation in relations:
            index[edge.target_id].append(edge.source_id)
    return index


def _ancestor_ids(start_id: str, reverse_index: dict[str, list[str]]) -> set[str]:
    visited: set[str] = set()
    stack = list(reverse_index.get(start_id, []))
    while stack:
        node_id = stack.pop()
        if node_id in visited:
            continue
        visited.add(node_id)
        stack.extend(reverse_index.get(node_id, []))
    return visited


def _descendants(start_id: str, adjacency: dict[str, list[str]]) -> set[str]:
    visited: set[str] = set()
    stack = list(adjacency.get(start_id, []))
    while stack:
        node_id = stack.pop()
        if node_id in visited:
            continue
        visited.add(node_id)
        stack.extend(adjacency.get(node_id, []))
    return visited


def augment_connects_edges(
    graph: SceneGraph,
    *,
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
    edge_index: EdgeIndexFn,
    build_node_bboxes: NodeBboxBuilder,
    add_edge_if_valid: EdgeAdder,
    is_connects_opening: NodeFilter,
    semantic_hierarchy_relations: set[RelationType],
) -> int:
    nodes_by_id = graph.nodes
    connects_index = edge_index(graph, RelationType.CONNECTS)
    reverse_hierarchy = _reverse_edge_index(graph, semantic_hierarchy_relations)
    forward_hierarchy = edge_index(graph, RelationType.CONTAINS)

    for relation in (
        RelationType.CONSISTS_OF_BUILDING_PART,
        RelationType.INTERIOR_ROOM,
        RelationType.HAS_CITY_OBJECT,
        RelationType.HAS_GROUP_MEMBER,
        RelationType.OUTER_BUILDING_INSTALLATION,
        RelationType.INTERIOR_BUILDING_INSTALLATION,
        RelationType.ROOM_INSTALLATION,
    ):
        for source_id, target_ids in edge_index(graph, relation).items():
            forward_hierarchy[source_id].extend(target_ids)

    opening_and_room_bboxes = build_node_bboxes(
        graph,
        target_types={NodeType.OPENING, NodeType.ROOM},
    )
    added = 0

    opening_ids = [
        node_id
        for node_id, node in nodes_by_id.items()
        if node.node_type == NodeType.OPENING and is_connects_opening(node)
    ]
    for opening_id in opening_ids:
        if connects_index.get(opening_id):
            continue
        opening_node = nodes_by_id.get(opening_id)
        if opening_node is None:
            continue

        ancestors = _ancestor_ids(opening_id, reverse_hierarchy)
        ancestor_rooms = sorted(
            node_id
            for node_id in ancestors
            if (
                nodes_by_id.get(node_id) is not None
                and nodes_by_id[node_id].node_type == NodeType.ROOM
            )
        )
        candidate_room_ids: set[str] = set(ancestor_rooms)

        if not candidate_room_ids:
            seed_ids = [
                node_id
                for node_id in ancestors
                if nodes_by_id.get(node_id) is not None
                and nodes_by_id[node_id].node_type in {NodeType.BUILDING_PART, NodeType.BUILDING}
            ]
            for seed_id in seed_ids:
                for descendant_id in _descendants(seed_id, forward_hierarchy):
                    node = nodes_by_id.get(descendant_id)
                    if node is not None and node.node_type == NodeType.ROOM:
                        candidate_room_ids.add(descendant_id)

        if not candidate_room_ids:
            continue

        opening_bbox = opening_and_room_bboxes.get(opening_id)
        filtered_room_ids: list[str] = []
        if opening_bbox is not None:
            for room_id in sorted(candidate_room_ids):
                room_bbox = opening_and_room_bboxes.get(room_id)
                if room_bbox is None:
                    continue
                relation, _ = infer_spatial_relation(
                    opening_bbox,
                    room_bbox,
                    touch_epsilon=touch_epsilon,
                    adjacent_epsilon=adjacent_epsilon,
                    intersection_epsilon=intersection_epsilon,
                    touch_min_contact_area=DEFAULT_TOUCH_MIN_CONTACT_AREA,
                    touch_min_contact_length=DEFAULT_TOUCH_MIN_CONTACT_LENGTH,
                )
                if relation is not None:
                    filtered_room_ids.append(room_id)

        final_room_ids = filtered_room_ids or sorted(candidate_room_ids)
        for room_id in final_room_ids:
            before = len(graph.edges)
            add_edge_if_valid(
                graph,
                create_edge(
                    opening_id,
                    room_id,
                    RelationType.CONNECTS,
                    method="hierarchy_bbox_fallback_v1",
                    source="connects_fallback",
                    confidence=0.85,
                    evidence_score=0.85,
                    computed_at=datetime.now(timezone.utc).isoformat(),
                ),
            )
            if len(graph.edges) > before:
                added += 1

    if added > 0:
        LOGGER.info("[CONNECTS] fallback augmentation added_edges=%d", added)
    return added
