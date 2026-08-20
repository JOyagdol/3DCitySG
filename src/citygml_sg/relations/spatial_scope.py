"""Room-scoped spatial candidate discovery and boundary representative selection."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from citygml_sg.domain.bbox import BBox
from citygml_sg.domain.enums import NodeType, RelationType
from citygml_sg.domain.node import Node
from citygml_sg.graph.graph_builder import SceneGraph

DEFAULT_BOUNDARY_LAYER_GAP_EPSILON = 0.25
DEFAULT_BOUNDARY_LAYER_OVERLAP_RATIO = 0.85
FLOOR_LIKE_SURFACE_TYPES: set[str] = {"FloorSurface", "OuterFloorSurface", "GroundSurface"}
WALL_LIKE_SURFACE_TYPES: set[str] = {"WallSurface", "InteriorWallSurface"}
FLOOR_FINISH_KEYWORDS: tuple[str, ...] = (
    "\ub9c8\uac10",
    "\ub9c8\ub8e8",
    "\ud0c0\uc77c",
    "tile",
    "finish",
    "finishing",
)
FLOOR_SUBSTRATE_KEYWORDS: tuple[str, ...] = ("\ub2e8\uc5f4", "insulation", "foam", "substrate")

EdgeIndexFn = Callable[[SceneGraph, RelationType], dict[str, list[str]]]
NodeBboxBuilder = Callable[..., dict[str, BBox]]
OpeningFilterFn = Callable[[Node], bool]
RoomSpatialScope = tuple[
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, int],
]


def bbox_axis_span(bbox: BBox, axis: int) -> float:
    if axis == 0:
        return float(bbox.max_point.x - bbox.min_point.x)
    if axis == 1:
        return float(bbox.max_point.y - bbox.min_point.y)
    return float(bbox.max_point.z - bbox.min_point.z)


def bbox_axis_center(bbox: BBox, axis: int) -> float:
    if axis == 0:
        return float((bbox.min_point.x + bbox.max_point.x) / 2.0)
    if axis == 1:
        return float((bbox.min_point.y + bbox.max_point.y) / 2.0)
    return float((bbox.min_point.z + bbox.max_point.z) / 2.0)


def bbox_axis_overlap(bbox_a: BBox, bbox_b: BBox, axis: int) -> float:
    if axis == 0:
        return float(
            min(bbox_a.max_point.x, bbox_b.max_point.x)
            - max(bbox_a.min_point.x, bbox_b.min_point.x)
        )
    if axis == 1:
        return float(
            min(bbox_a.max_point.y, bbox_b.max_point.y)
            - max(bbox_a.min_point.y, bbox_b.min_point.y)
        )
    return float(
        min(bbox_a.max_point.z, bbox_b.max_point.z)
        - max(bbox_a.min_point.z, bbox_b.min_point.z)
    )


def bbox_xy_overlaps(first: BBox, second: BBox, *, intersection_epsilon: float) -> bool:
    overlap_x = min(first.max_point.x, second.max_point.x) - max(
        first.min_point.x,
        second.min_point.x,
    )
    overlap_y = min(first.max_point.y, second.max_point.y) - max(
        first.min_point.y,
        second.min_point.y,
    )
    return overlap_x >= -intersection_epsilon and overlap_y >= -intersection_epsilon


def boundary_plane_axis(bbox: BBox) -> int:
    spans = [bbox_axis_span(bbox, 0), bbox_axis_span(bbox, 1), bbox_axis_span(bbox, 2)]
    min_axis = 0
    min_value = spans[0]
    for axis, span in enumerate(spans[1:], start=1):
        if span < min_value:
            min_axis = axis
            min_value = span
    return min_axis


def boundary_projected_area(bbox: BBox, normal_axis: int) -> float:
    tangent_axes = [axis for axis in (0, 1, 2) if axis != normal_axis]
    return max(bbox_axis_span(bbox, tangent_axes[0]), 0.0) * max(
        bbox_axis_span(bbox, tangent_axes[1]),
        0.0,
    )


def node_keyword_text(node: Node) -> str:
    values: list[str] = []
    for key in (
        "gml_name",
        "attr_ifc_object_type",
        "attr_identity_data_type_name",
        "attr_other_family_and_type",
        "attr_other_type",
        "attr_materials_and_finishes_structural_material",
    ):
        value = node.properties.get(key)
        if value is not None:
            values.append(str(value))
    return " ".join(values).lower()


def floor_finish_priority(node: Node) -> float:
    text = node_keyword_text(node)
    priority = 0.0
    if str(node.properties.get("attr_is_walkable") or "").lower() == "true":
        priority += 1.0
    if any(keyword in text for keyword in FLOOR_FINISH_KEYWORDS):
        priority += 2.0
    if any(keyword in text for keyword in FLOOR_SUBSTRATE_KEYWORDS):
        priority -= 3.0
    return priority


def boundary_representation_score(
    node: Node,
    bbox: BBox,
    *,
    surface_type: str,
    normal_axis: int,
) -> tuple[float, float, float]:
    projected_area = boundary_projected_area(bbox, normal_axis)
    if surface_type in FLOOR_LIKE_SURFACE_TYPES:
        # Furniture should attach to the usable top finish, not lower insulation/slab layers.
        return (round(float(bbox.max_point.z), 6), floor_finish_priority(node), projected_area)
    return (projected_area, 0.0, 0.0)


def boundaries_are_layered_duplicates(
    first_bbox: BBox,
    second_bbox: BBox,
    *,
    normal_axis: int,
    gap_epsilon: float,
    overlap_ratio_threshold: float,
) -> bool:
    normal_gap = abs(
        bbox_axis_center(first_bbox, normal_axis)
        - bbox_axis_center(second_bbox, normal_axis)
    )
    if normal_gap > gap_epsilon:
        return False

    tangent_axes = [axis for axis in (0, 1, 2) if axis != normal_axis]
    for axis in tangent_axes:
        overlap = bbox_axis_overlap(first_bbox, second_bbox, axis)
        if overlap <= 0.0:
            return False
        min_span = min(bbox_axis_span(first_bbox, axis), bbox_axis_span(second_bbox, axis))
        if min_span <= 0.0:
            return False
        overlap_ratio = overlap / min_span
        if overlap_ratio < overlap_ratio_threshold:
            return False
    return True


def collapse_layered_boundary_ids(
    boundary_ids: set[str],
    *,
    nodes_by_id: dict[str, Node],
    boundary_bboxes: dict[str, BBox],
) -> list[str]:
    groups: list[dict[str, object]] = []
    for boundary_id in sorted(boundary_ids):
        bbox = boundary_bboxes.get(boundary_id)
        node = nodes_by_id.get(boundary_id)
        if bbox is None or node is None:
            continue
        surface_type = str(node.properties.get("surface_type") or "BoundarySurface")
        normal_axis = boundary_plane_axis(bbox)
        merged = False
        for group in groups:
            if group["surface_type"] != surface_type:
                continue
            if group["normal_axis"] != normal_axis:
                continue
            rep_bbox: BBox = group["rep_bbox"]  # type: ignore[assignment]
            if not boundaries_are_layered_duplicates(
                rep_bbox,
                bbox,
                normal_axis=normal_axis,
                gap_epsilon=DEFAULT_BOUNDARY_LAYER_GAP_EPSILON,
                overlap_ratio_threshold=DEFAULT_BOUNDARY_LAYER_OVERLAP_RATIO,
            ):
                continue
            candidate_score = boundary_representation_score(
                node,
                bbox,
                surface_type=surface_type,
                normal_axis=normal_axis,
            )
            rep_score: tuple[float, float, float] = group["rep_score"]  # type: ignore[assignment]
            if candidate_score > rep_score:
                group["rep_id"] = boundary_id
                group["rep_bbox"] = bbox
                group["rep_score"] = candidate_score
            merged = True
            break

        if merged:
            continue

        groups.append(
            {
                "surface_type": surface_type,
                "normal_axis": normal_axis,
                "rep_id": boundary_id,
                "rep_bbox": bbox,
                "rep_score": boundary_representation_score(
                    node,
                    bbox,
                    surface_type=surface_type,
                    normal_axis=normal_axis,
                ),
            }
        )

    return sorted(str(group["rep_id"]) for group in groups)


def build_room_spatial_scope(
    graph: SceneGraph,
    *,
    include_container_fallback: bool,
    collapse_layered_fallback: bool = False,
    edge_index: EdgeIndexFn,
    build_node_bboxes: NodeBboxBuilder,
    is_door_or_window_opening: OpeningFilterFn,
) -> RoomSpatialScope:
    """Build room-scoped furniture/boundary/opening maps.

    When include_container_fallback is True, rooms without direct BOUNDED_BY links
    inherit boundary surfaces from their parent BuildingPart/Building containers.
    """
    nodes_by_id = graph.nodes
    inside_index = edge_index(graph, RelationType.INSIDE)  # furniture -> room
    # room|building|buildingpart -> boundary surface
    bounded_by_index = edge_index(graph, RelationType.BOUNDED_BY)
    has_opening_index = edge_index(graph, RelationType.HAS_OPENING)  # boundary surface -> opening

    room_to_furniture: dict[str, list[str]] = defaultdict(list)
    for furniture_id, room_ids in inside_index.items():
        furniture_node = nodes_by_id.get(furniture_id)
        if furniture_node is None or furniture_node.node_type != NodeType.BUILDING_FURNITURE:
            continue
        for room_id in room_ids:
            room_node = nodes_by_id.get(room_id)
            if room_node is None or room_node.node_type != NodeType.ROOM:
                continue
            room_to_furniture[room_id].append(furniture_id)

    room_to_boundary: dict[str, list[str]] = defaultdict(list)
    for room_id, boundary_ids in bounded_by_index.items():
        room_node = nodes_by_id.get(room_id)
        if room_node is None or room_node.node_type != NodeType.ROOM:
            continue
        for boundary_id in boundary_ids:
            boundary_node = nodes_by_id.get(boundary_id)
            if boundary_node is None or boundary_node.node_type != NodeType.BOUNDARY_SURFACE:
                continue
            room_to_boundary[room_id].append(boundary_id)

    fallback_room_count = 0
    fallback_boundary_link_count = 0
    fallback_boundary_collapsed_link_count = 0
    fallback_boundary_reduced_link_count = 0
    if include_container_fallback:
        boundary_bboxes = build_node_bboxes(graph, target_types={NodeType.BOUNDARY_SURFACE})
        room_to_containers: dict[str, set[str]] = defaultdict(set)
        for edge in graph.edges:
            if edge.relation not in {RelationType.INTERIOR_ROOM, RelationType.CONTAINS}:
                continue
            source_node = nodes_by_id.get(edge.source_id)
            target_node = nodes_by_id.get(edge.target_id)
            if source_node is None or target_node is None:
                continue
            if target_node.node_type != NodeType.ROOM:
                continue
            if source_node.node_type not in {NodeType.BUILDING, NodeType.BUILDING_PART}:
                continue
            room_to_containers[edge.target_id].add(edge.source_id)

        all_room_ids = [
            node_id for node_id, node in nodes_by_id.items() if node.node_type == NodeType.ROOM
        ]
        for room_id in sorted(all_room_ids):
            if room_to_boundary.get(room_id):
                continue
            fallback_boundary_ids: set[str] = set()
            for container_id in sorted(room_to_containers.get(room_id, set())):
                for boundary_id in bounded_by_index.get(container_id, []):
                    boundary_node = nodes_by_id.get(boundary_id)
                    if (
                        boundary_node is None
                        or boundary_node.node_type != NodeType.BOUNDARY_SURFACE
                    ):
                        continue
                    fallback_boundary_ids.add(boundary_id)
            if not fallback_boundary_ids:
                continue
            raw_count = len(fallback_boundary_ids)
            selected_boundary_ids = sorted(fallback_boundary_ids)
            if collapse_layered_fallback and raw_count > 1:
                selected_boundary_ids = collapse_layered_boundary_ids(
                    fallback_boundary_ids,
                    nodes_by_id=nodes_by_id,
                    boundary_bboxes=boundary_bboxes,
                )
            room_to_boundary[room_id].extend(selected_boundary_ids)
            fallback_room_count += 1
            fallback_boundary_link_count += raw_count
            fallback_boundary_collapsed_link_count += len(selected_boundary_ids)
            fallback_boundary_reduced_link_count += max(0, raw_count - len(selected_boundary_ids))

    room_to_opening: dict[str, list[str]] = defaultdict(list)
    for room_id, boundary_ids in room_to_boundary.items():
        for boundary_id in boundary_ids:
            for opening_id in has_opening_index.get(boundary_id, []):
                opening_node = nodes_by_id.get(opening_id)
                if opening_node is None or opening_node.node_type != NodeType.OPENING:
                    continue
                if not is_door_or_window_opening(opening_node):
                    continue
                room_to_opening[room_id].append(opening_id)

    return (
        room_to_furniture,
        room_to_boundary,
        room_to_opening,
        {
            "fallback_room_count": fallback_room_count,
            "fallback_boundary_link_count": fallback_boundary_link_count,
            "fallback_boundary_collapsed_link_count": fallback_boundary_collapsed_link_count,
            "fallback_boundary_reduced_link_count": fallback_boundary_reduced_link_count,
        },
    )
