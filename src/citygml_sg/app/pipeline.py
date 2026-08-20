"""Top-level pipeline orchestration."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from time import perf_counter
from typing import Callable
from xml.etree.ElementTree import Element

from citygml_sg.domain.edge import Edge
from citygml_sg.domain.bbox import BBox
from citygml_sg.domain.enums import NodeType, RelationType
from citygml_sg.domain.geometry import Point3D
from citygml_sg.domain.node import Node
from citygml_sg.evaluation.scorecard import build_scorecard as _build_scorecard
from citygml_sg.extractors.bbox_extractor import extract_bbox
from citygml_sg.graph.edge_factory import create_edge
from citygml_sg.graph.graph_builder import SceneGraph
from citygml_sg.graph.graph_schema import OBJECT_NODE_TYPES
from citygml_sg.graph.node_factory import create_node
from citygml_sg.modules.address.parser import parse_address_element
from citygml_sg.modules.boundary_surface.parser import parse_boundary_surface_element
from citygml_sg.modules.building.parser import parse_building_element
from citygml_sg.modules.building_furniture.parser import parse_building_furniture_element
from citygml_sg.modules.building_installation.parser import parse_building_installation_element
from citygml_sg.modules.building_part.parser import parse_building_part_element
from citygml_sg.modules.city_object_group.parser import parse_city_object_group_element
from citygml_sg.modules.city_object_member.parser import parse_city_object_member_element
from citygml_sg.modules.opening.parser import parse_opening_element
from citygml_sg.modules.room.parser import parse_room_element
from citygml_sg.parsers.citygml.reader import read_citygml
from citygml_sg.app.reporting import _emit_conversion_report, _log_stage_timeline, _progress_bar
from citygml_sg.config.settings import load_project_config
from citygml_sg.storage.json.writer import patch_json_number_fields, write_graph_json_stream, write_json
from citygml_sg.storage.neo4j.client import Neo4jClient
from citygml_sg.storage.neo4j.constraints import CONSTRAINTS
from citygml_sg.storage.neo4j.reader import Neo4jReader
from citygml_sg.storage.neo4j.writer import Neo4jWriter
from citygml_sg.relations.spatial_edges import (
    DEFAULT_TOUCH_MIN_CONTACT_AREA,
    DEFAULT_TOUCH_MIN_CONTACT_LENGTH,
    augment_connects_edges as _augment_connects_edges,
    build_spatial_edges as _build_spatial_edges,
)
from citygml_sg.relations.spatial_scope import build_room_spatial_scope as _build_room_spatial_scope
from citygml_sg.utils.io import ensure_dir
from citygml_sg.utils.logging import get_logger
from citygml_sg.utils.xml import get_gml_id, local_name
from citygml_sg.world_graph.citygml_to_graph.appearance_subgraph import (
    attach_appearance_subgraph as _attach_appearance_subgraph,
    normalize_target_refs as _normalize_target_refs,
)
from citygml_sg.world_graph.citygml_to_graph.geometry_subgraph import (
    attach_geometry_subgraph as _attach_geometry_subgraph,
    attach_lod_geometry_structure as _attach_lod_geometry_structure,
    iter_ring_positions as _iter_ring_positions,
)

LOGGER = get_logger(__name__)

BOUNDARY_SURFACE_TAGS = {
    "WallSurface",
    "RoofSurface",
    "GroundSurface",
    "InteriorWallSurface",
    "FloorSurface",
    "CeilingSurface",
    "ClosureSurface",
    "OuterCeilingSurface",
    "OuterFloorSurface",
}
OPENING_TAGS = {"Door", "Window"}
SPATIAL_OPENING_TYPES = {"Door", "Window"}
CONNECTS_OPENING_TYPES = {"Door"}
BOUNDARY_SURFACE_TYPE_NODE_PREFIX = "boundary_surface_type::"
APPEARANCE_FALLBACK_OWNER_TAGS: set[str] = {
    "cityObjectMember",
    "CityObjectGroup",
    "Building",
    "BuildingPart",
    "Room",
    "BuildingInstallation",
    "IntBuildingInstallation",
    "BuildingFurniture",
    *BOUNDARY_SURFACE_TAGS,
    *OPENING_TAGS,
}

SEMANTIC_NODE_TYPES: set[NodeType] = {
    NodeType.CITY_OBJECT_MEMBER,
    NodeType.CITY_OBJECT_GROUP,
    NodeType.BUILDING,
    NodeType.BUILDING_PART,
    NodeType.ROOM,
    NodeType.BUILDING_INSTALLATION,
    NodeType.INT_BUILDING_INSTALLATION,
    NodeType.BOUNDARY_SURFACE,
    NodeType.OPENING,
    NodeType.BUILDING_FURNITURE,
    NodeType.ADDRESS,
    NodeType.APPEARANCE,
    NodeType.SURFACE_DATA,
}
GEOMETRY_NODE_TYPES: set[NodeType] = {
    NodeType.GEOMETRY,
    NodeType.IMPLICIT_GEOMETRY,
    NodeType.SOLID,
    NodeType.MULTI_SURFACE,
    NodeType.MULTI_CURVE,
    NodeType.POLYGON,
    NodeType.LINEAR_RING,
    NodeType.POSITION,
}
SEMANTIC_RELATIONS: set[RelationType] = {
    RelationType.HAS_CITY_OBJECT,
    RelationType.HAS_GROUP_MEMBER,
    RelationType.CONTAINS,
    RelationType.CONSISTS_OF_BUILDING_PART,
    RelationType.INTERIOR_ROOM,
    RelationType.OUTER_BUILDING_INSTALLATION,
    RelationType.INTERIOR_BUILDING_INSTALLATION,
    RelationType.ROOM_INSTALLATION,
    RelationType.INTERIOR_FURNITURE,
    RelationType.BOUNDED_BY,
    RelationType.HAS_SURFACE_TYPE,
    RelationType.HAS_OPENING,
    RelationType.HAS_ADDRESS,
    RelationType.HAS_APPEARANCE,
    RelationType.HAS_SURFACE_DATA,
    RelationType.APPLIES_TO,
}
SPATIAL_RELATIONS: set[RelationType] = {
    RelationType.INSIDE,
    RelationType.CONNECTS,
    RelationType.ADJACENT_TO,
    RelationType.TOUCHES,
    RelationType.INTERSECTS,
    RelationType.ABOVE,
    RelationType.BELOW,
    RelationType.ADJACENT_SURFACE,
    RelationType.ATTACHED_TO,
    RelationType.HOSTED_BY,
}
SEMANTIC_HIERARCHY_RELATIONS: set[RelationType] = {
    RelationType.HAS_CITY_OBJECT,
    RelationType.HAS_GROUP_MEMBER,
    RelationType.CONTAINS,
    RelationType.CONSISTS_OF_BUILDING_PART,
    RelationType.INTERIOR_ROOM,
    RelationType.OUTER_BUILDING_INSTALLATION,
    RelationType.INTERIOR_BUILDING_INSTALLATION,
    RelationType.ROOM_INSTALLATION,
    RelationType.INTERIOR_FURNITURE,
    RelationType.BOUNDED_BY,
    RelationType.HAS_OPENING,
}
GEOMETRY_RELATIONS: set[RelationType] = {
    RelationType.HAS_LOD_GEOMETRY,
    RelationType.HAS_GEOMETRY_COMPONENT,
    RelationType.HAS_GEOMETRY_MEMBER,
    RelationType.HAS_GEOMETRY,
    RelationType.HAS_RING,
    RelationType.HAS_POS,
}

DEFAULT_SPATIAL_TOUCH_EPSILON = 0.05
DEFAULT_SPATIAL_ADJACENT_EPSILON = 0.50
DEFAULT_SPATIAL_INTERSECTION_EPSILON = 1e-6

PIPELINE_STAGE_ORDER: tuple[str, ...] = (
    "parse_xml",
    "collect_semantics",
    "build_nodes",
    "build_semantic_edges",
    "build_geometry",
    "export_neo4j",
    "export_json",
)

BENCHMARK_QUERY_SET: tuple[tuple[str, str, str], ...] = (
    (
        "B1",
        "baseline__all_nodes",
        "MATCH (n) RETURN count(n) AS count",
    ),
    (
        "B2",
        "baseline__buildings",
        "MATCH (:Building) RETURN count(*) AS count",
    ),
    (
        "B3",
        "baseline__rooms",
        "MATCH (:Room) RETURN count(*) AS count",
    ),
    (
        "B4",
        "baseline__openings",
        "MATCH (:Opening) RETURN count(*) AS count",
    ),
    (
        "B5",
        "baseline__furniture_inside_room_links",
        "MATCH (:BuildingFurniture)-[:INSIDE]->(:Room) RETURN count(*) AS count",
    ),
    (
        "B6",
        "baseline__room_boundary_links",
        "MATCH (:Room)-[:BOUNDED_BY]->(:BoundarySurface) RETURN count(*) AS count",
    ),
    (
        "B7",
        "baseline__boundary_opening_links",
        "MATCH (:BoundarySurface)-[:HAS_OPENING]->(:Opening) RETURN count(*) AS count",
    ),
    (
        "H1",
        "hard__furniture_furniture_spatial_any",
        (
            "MATCH (:BuildingFurniture)-[r:INTERSECTS|TOUCHES|ADJACENT_TO]->(:BuildingFurniture) "
            "RETURN count(r) AS count"
        ),
    ),
    (
        "H2",
        "hard__furniture_opening_spatial_any",
        (
            "MATCH (:BuildingFurniture)-[r:INTERSECTS|TOUCHES|ADJACENT_TO]->(:Opening) "
            "RETURN count(r) AS count"
        ),
    ),
    (
        "H3",
        "hard__furniture_boundary_spatial_any",
        (
            "MATCH (:BuildingFurniture)-[r:INTERSECTS|TOUCHES|ADJACENT_TO]->(:BoundarySurface) "
            "RETURN count(r) AS count"
        ),
    ),
    (
        "H4",
        "hard__opening_room_connects",
        "MATCH (:Opening {opening_type: 'Door'})-[:CONNECTS]->(:Room) RETURN count(*) AS count",
    ),
    (
        "H5",
        "hard__room_internal_furniture_touching_opening",
        (
            "MATCH (f:BuildingFurniture)-[:INSIDE]->(r:Room)<-[:CONNECTS]-(o:Opening) "
            "MATCH (f)-[:TOUCHES]->(o) RETURN count(DISTINCT f) AS count"
        ),
    ),
    (
        "S1",
        "scenario__rooms_with_furniture",
        "MATCH (r:Room)-[:INTERIOR_FURNITURE]->(:BuildingFurniture) RETURN count(DISTINCT r) AS count",
    ),
    (
        "S2",
        "scenario__rooms_with_installations",
        (
            "MATCH (r:Room)-[:ROOM_INSTALLATION]->(:IntBuildingInstallation) "
            "RETURN count(DISTINCT r) AS count"
        ),
    ),
    (
        "S3",
        "scenario__door_opening_count",
        "MATCH (:Opening {opening_type: 'Door'}) RETURN count(*) AS count",
    ),
    (
        "S4",
        "scenario__rooms_with_internal_furniture_spatial_pairs",
        (
            "MATCH (r:Room)<-[:INSIDE]-(f1:BuildingFurniture)-[:INTERSECTS|TOUCHES|ADJACENT_TO]->"
            "(f2:BuildingFurniture)-[:INSIDE]->(r) "
            "WHERE f1.id < f2.id RETURN count(DISTINCT r) AS count"
        ),
    ),
    (
        "S5",
        "scenario__room_to_room_pairs_via_same_buildingpart",
        (
            "MATCH (r1:Room)<-[:INTERIOR_ROOM]-(bp:BuildingPart)-[:INTERIOR_ROOM]->(r2:Room) "
            "WHERE r1.id < r2.id RETURN count(*) AS count"
        ),
    ),
)

ParserFn = Callable[[Element], dict]

OBJECT_PARSERS: dict[str, tuple[NodeType, ParserFn]] = {
    "cityObjectMember": (NodeType.CITY_OBJECT_MEMBER, parse_city_object_member_element),
    "CityObjectGroup": (NodeType.CITY_OBJECT_GROUP, parse_city_object_group_element),
    "Building": (NodeType.BUILDING, parse_building_element),
    "BuildingPart": (NodeType.BUILDING_PART, parse_building_part_element),
    "Room": (NodeType.ROOM, parse_room_element),
    "BuildingInstallation": (NodeType.BUILDING_INSTALLATION, parse_building_installation_element),
    "IntBuildingInstallation": (NodeType.INT_BUILDING_INSTALLATION, parse_building_installation_element),
    "BuildingFurniture": (NodeType.BUILDING_FURNITURE, parse_building_furniture_element),
    "Address": (NodeType.ADDRESS, parse_address_element),
}
for tag in BOUNDARY_SURFACE_TAGS:
    OBJECT_PARSERS[tag] = (NodeType.BOUNDARY_SURFACE, parse_boundary_surface_element)
for tag in OPENING_TAGS:
    OBJECT_PARSERS[tag] = (NodeType.OPENING, parse_opening_element)


@dataclass(slots=True)
class ElementRecord:
    element: Element
    node_id: str
    node_type: NodeType
    properties: dict


@dataclass(slots=True)
class _StageTimeline:
    stage_index_map: dict[str, int]
    total_stages: int

    @classmethod
    def from_stage_order(cls, stage_order: tuple[str, ...]) -> "_StageTimeline":
        return cls(
            stage_index_map={name: index for index, name in enumerate(stage_order, start=1)},
            total_stages=len(stage_order),
        )

    def start(self, stage_name: str, detail: str | None = None) -> None:
        _log_stage_timeline(
            stage_name=stage_name,
            stage_index=self.stage_index_map[stage_name],
            total_stages=self.total_stages,
            event="START",
            detail=detail,
        )

    def done(self, stage_name: str, elapsed: float, detail: str | None = None) -> None:
        _log_stage_timeline(
            stage_name=stage_name,
            stage_index=self.stage_index_map[stage_name],
            total_stages=self.total_stages,
            event="DONE",
            elapsed_seconds=elapsed,
            detail=detail,
        )

    def skip(self, stage_name: str, detail: str | None = None) -> None:
        _log_stage_timeline(
            stage_name=stage_name,
            stage_index=self.stage_index_map[stage_name],
            total_stages=self.total_stages,
            event="SKIP",
            elapsed_seconds=0.0,
            detail=detail,
        )


def _fallback_id(node_type: NodeType, counters: Counter[str]) -> str:
    key = node_type.value
    counters[key] += 1
    return f"{node_type.value.lower()}_{counters[key]}"


def _coerce_property_value(value: object) -> object:
    if isinstance(value, list):
        return [_coerce_property_value(item) for item in value]
    if isinstance(value, tuple):
        return [_coerce_property_value(item) for item in value]
    return value


def _clean_properties(properties: dict) -> dict:
    cleaned: dict[str, object] = {}
    for key, value in properties.items():
        if value is None:
            continue
        cleaned[key] = _coerce_property_value(value)
    return cleaned


def _normalize_boundary_surface_type(value: object) -> str:
    surface_type = str(value or "").strip()
    if surface_type:
        return surface_type
    return "BoundarySurface"


def _boundary_surface_type_node_id(surface_type: str) -> str:
    return f"{BOUNDARY_SURFACE_TYPE_NODE_PREFIX}{surface_type}"


def _build_boundary_surface_type_nodes(graph: SceneGraph, records: list[ElementRecord]) -> int:
    added = 0
    surface_types = sorted(
        {
            _normalize_boundary_surface_type(record.properties.get("surface_type"))
            for record in records
            if record.node_type == NodeType.BOUNDARY_SURFACE
        }
    )
    for surface_type in surface_types:
        node_id = _boundary_surface_type_node_id(surface_type)
        if node_id in graph.nodes:
            continue
        graph.add_node(
            create_node(
                node_id,
                NodeType.BOUNDARY_SURFACE_TYPE,
                name=surface_type,
                surface_type=surface_type,
                object_type="BoundarySurfaceType",
                source_tag="BoundarySurfaceType",
            )
        )
        added += 1
    return added


def _collect_records(root: Element) -> tuple[list[ElementRecord], dict[Element, ElementRecord]]:
    fallback_counters: Counter[str] = Counter()
    records: list[ElementRecord] = []
    by_element: dict[Element, ElementRecord] = {}

    for element in root.iter():
        lname = local_name(element.tag)
        parser_info = OBJECT_PARSERS.get(lname)
        if parser_info is None:
            continue

        node_type, parser = parser_info
        properties = _clean_properties(parser(element))

        raw_id = properties.get("gml_id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raw_id = _fallback_id(node_type, fallback_counters)
        node_id = raw_id

        properties["gml_id"] = raw_id
        properties["source_tag"] = lname

        record = ElementRecord(element=element, node_id=node_id, node_type=node_type, properties=properties)
        records.append(record)
        by_element[element] = record

    return records, by_element


def _build_parent_map(root: Element) -> dict[Element, Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _nearest_ancestor(
    element: Element,
    parent_map: dict[Element, Element],
    by_element: dict[Element, ElementRecord],
    allowed_types: set[NodeType],
) -> ElementRecord | None:
    current = parent_map.get(element)
    while current is not None:
        record = by_element.get(current)
        if record is not None and record.node_type in allowed_types:
            return record
        current = parent_map.get(current)
    return None


def _nearest_ancestor_by_tag(
    element: Element,
    parent_map: dict[Element, Element],
    allowed_tags: set[str],
) -> Element | None:
    current = parent_map.get(element)
    while current is not None:
        if local_name(current.tag) in allowed_tags:
            return current
        current = parent_map.get(current)
    return None


def _direct_parent_tag(element: Element, parent_map: dict[Element, Element]) -> str | None:
    parent = parent_map.get(element)
    if parent is None:
        return None
    return local_name(parent.tag)


def _add_edge_if_valid(graph: SceneGraph, edge: Edge) -> None:
    try:
        graph.add_edge(edge)
    except ValueError as exc:
        LOGGER.warning(
            "Skip edge (%s -> %s %s): %s",
            edge.source_id,
            edge.target_id,
            edge.relation.value,
            exc,
        )


def _resolve_spatial_thresholds(config_path: str | Path) -> tuple[float, float, float]:
    defaults = (
        DEFAULT_SPATIAL_TOUCH_EPSILON,
        DEFAULT_SPATIAL_ADJACENT_EPSILON,
        DEFAULT_SPATIAL_INTERSECTION_EPSILON,
    )
    try:
        config = load_project_config(config_path)
    except Exception as exc:
        LOGGER.warning(
            "Failed to load spatial config from %s; falling back to defaults (%s). reason=%s",
            config_path,
            f"touch={defaults[0]}, adjacent={defaults[1]}, intersection={defaults[2]}",
            exc,
        )
        return defaults

    return (
        float(config.spatial.touch_epsilon),
        float(config.spatial.adjacent_epsilon),
        float(config.spatial.intersection_epsilon),
    )


def _build_semantic_edges(
    graph: SceneGraph,
    root: Element,
    records: list[ElementRecord],
    by_element: dict[Element, ElementRecord],
) -> None:
    parent_map = _build_parent_map(root)

    for record in records:
        direct_parent_tag = _direct_parent_tag(record.element, parent_map)

        if direct_parent_tag == "cityObjectMember" and record.node_type != NodeType.CITY_OBJECT_MEMBER:
            parent = _nearest_ancestor(record.element, parent_map, by_element, {NodeType.CITY_OBJECT_MEMBER})
            if parent and parent.node_id != record.node_id:
                _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.HAS_CITY_OBJECT))

        if direct_parent_tag == "groupMember":
            parent = _nearest_ancestor(record.element, parent_map, by_element, {NodeType.CITY_OBJECT_GROUP})
            if parent and parent.node_id != record.node_id:
                _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.HAS_GROUP_MEMBER))

        if record.node_type == NodeType.BUILDING_PART:
            parent = _nearest_ancestor(
                record.element,
                parent_map,
                by_element,
                {NodeType.BUILDING, NodeType.BUILDING_PART},
            )
            if parent:
                if direct_parent_tag == "consistsOfBuildingPart":
                    _add_edge_if_valid(
                        graph,
                        create_edge(parent.node_id, record.node_id, RelationType.CONSISTS_OF_BUILDING_PART),
                    )
                else:
                    _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.CONTAINS))

        elif record.node_type == NodeType.ROOM:
            parent = _nearest_ancestor(
                record.element,
                parent_map,
                by_element,
                {NodeType.BUILDING, NodeType.BUILDING_PART},
            )
            if parent:
                if direct_parent_tag == "interiorRoom":
                    _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.INTERIOR_ROOM))
                else:
                    _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.CONTAINS))

        elif record.node_type == NodeType.BUILDING_INSTALLATION:
            parent = _nearest_ancestor(
                record.element,
                parent_map,
                by_element,
                {NodeType.BUILDING, NodeType.BUILDING_PART},
            )
            if parent:
                if direct_parent_tag == "outerBuildingInstallation":
                    _add_edge_if_valid(
                        graph,
                        create_edge(parent.node_id, record.node_id, RelationType.OUTER_BUILDING_INSTALLATION),
                    )
                else:
                    _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.CONTAINS))

        elif record.node_type == NodeType.INT_BUILDING_INSTALLATION:
            parent = _nearest_ancestor(
                record.element,
                parent_map,
                by_element,
                {NodeType.BUILDING, NodeType.BUILDING_PART, NodeType.ROOM},
            )
            if parent:
                if direct_parent_tag == "interiorBuildingInstallation":
                    _add_edge_if_valid(
                        graph,
                        create_edge(parent.node_id, record.node_id, RelationType.INTERIOR_BUILDING_INSTALLATION),
                    )
                if direct_parent_tag == "roomInstallation":
                    _add_edge_if_valid(
                        graph,
                        create_edge(parent.node_id, record.node_id, RelationType.ROOM_INSTALLATION),
                    )
                if direct_parent_tag not in {"interiorBuildingInstallation", "roomInstallation"}:
                    _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.CONTAINS))

        elif record.node_type == NodeType.BOUNDARY_SURFACE:
            parent = _nearest_ancestor(
                record.element,
                parent_map,
                by_element,
                {
                    NodeType.BUILDING,
                    NodeType.BUILDING_PART,
                    NodeType.ROOM,
                    NodeType.BUILDING_INSTALLATION,
                    NodeType.INT_BUILDING_INSTALLATION,
                },
            )
            if parent:
                _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.BOUNDED_BY))
            surface_type = _normalize_boundary_surface_type(record.properties.get("surface_type"))
            surface_type_node_id = _boundary_surface_type_node_id(surface_type)
            if surface_type_node_id not in graph.nodes:
                graph.add_node(
                    create_node(
                        surface_type_node_id,
                        NodeType.BOUNDARY_SURFACE_TYPE,
                        name=surface_type,
                        surface_type=surface_type,
                        object_type="BoundarySurfaceType",
                        source_tag="BoundarySurfaceType",
                    )
                )
            _add_edge_if_valid(
                graph,
                create_edge(record.node_id, surface_type_node_id, RelationType.HAS_SURFACE_TYPE),
            )

        elif record.node_type == NodeType.OPENING:
            boundary = _nearest_ancestor(record.element, parent_map, by_element, {NodeType.BOUNDARY_SURFACE})
            if boundary:
                _add_edge_if_valid(graph, create_edge(boundary.node_id, record.node_id, RelationType.HAS_OPENING))
                _add_edge_if_valid(
                    graph,
                    create_edge(
                        record.node_id,
                        boundary.node_id,
                        RelationType.HOSTED_BY,
                        method="semantic_has_opening_v1",
                        source="semantic_boundary_opening",
                        confidence=1.0,
                        evidence_score=1.0,
                        computed_at=datetime.now(timezone.utc).isoformat(),
                        boundary_surface_type=str(boundary.properties.get("surface_type") or "BoundarySurface"),
                    ),
                )

            room = _nearest_ancestor(record.element, parent_map, by_element, {NodeType.ROOM})
            opening_node = graph.nodes.get(record.node_id)
            if room and opening_node is not None and _is_connects_opening(opening_node):
                _add_edge_if_valid(
                    graph,
                    create_edge(
                        record.node_id,
                        room.node_id,
                        RelationType.CONNECTS,
                        method="semantic_ancestor_room_v1",
                        source="semantic_opening_room",
                        confidence=1.0,
                        evidence_score=1.0,
                        computed_at=datetime.now(timezone.utc).isoformat(),
                    ),
                )

        elif record.node_type == NodeType.BUILDING_FURNITURE:
            parent = _nearest_ancestor(record.element, parent_map, by_element, {NodeType.ROOM})
            if parent:
                _add_edge_if_valid(graph, create_edge(record.node_id, parent.node_id, RelationType.INSIDE))
                if direct_parent_tag == "interiorFurniture":
                    _add_edge_if_valid(
                        graph,
                        create_edge(parent.node_id, record.node_id, RelationType.INTERIOR_FURNITURE),
                    )
                else:
                    _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.CONTAINS))

        elif record.node_type == NodeType.ADDRESS:
            parent = _nearest_ancestor(
                record.element,
                parent_map,
                by_element,
                {NodeType.BUILDING, NodeType.BUILDING_PART},
            )
            if parent:
                _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.HAS_ADDRESS))


def _node_position_points(
    node_id: str,
    *,
    nodes_by_id: dict[str, object],
    has_geometry_index: dict[str, list[str]],
    has_ring_index: dict[str, list[str]],
    has_pos_index: dict[str, list[str]],
) -> list[Point3D]:
    points: list[Point3D] = []
    for polygon_id in has_geometry_index.get(node_id, []):
        for ring_id in has_ring_index.get(polygon_id, []):
            for pos_id in has_pos_index.get(ring_id, []):
                pos_node = nodes_by_id.get(pos_id)
                if pos_node is None:
                    continue
                x = pos_node.properties.get("x")
                y = pos_node.properties.get("y")
                z = pos_node.properties.get("z")
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not isinstance(z, (int, float)):
                    continue
                points.append(Point3D(float(x), float(y), float(z)))
    return points


def _node_polygon_rings(
    node_id: str,
    *,
    nodes_by_id: dict[str, object],
    has_geometry_index: dict[str, list[str]],
    has_ring_index: dict[str, list[str]],
    has_pos_index: dict[str, list[str]],
) -> list[list[Point3D]]:
    rings: list[list[Point3D]] = []
    for polygon_id in has_geometry_index.get(node_id, []):
        for ring_id in has_ring_index.get(polygon_id, []):
            ring_points: list[Point3D] = []
            for pos_id in has_pos_index.get(ring_id, []):
                pos_node = nodes_by_id.get(pos_id)
                if pos_node is None:
                    continue
                x = pos_node.properties.get("x")
                y = pos_node.properties.get("y")
                z = pos_node.properties.get("z")
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not isinstance(z, (int, float)):
                    continue
                ring_points.append(Point3D(float(x), float(y), float(z)))
            if len(ring_points) >= 2:
                rings.append(ring_points)
    return rings


def _build_node_bboxes(graph: SceneGraph, target_types: set[NodeType]) -> dict[str, BBox]:
    has_geometry_index = _edge_index(graph, RelationType.HAS_GEOMETRY)
    has_ring_index = _edge_index(graph, RelationType.HAS_RING)
    has_pos_index = _edge_index(graph, RelationType.HAS_POS)
    nodes_by_id = graph.nodes

    node_bboxes: dict[str, BBox] = {}
    for node_id, node in nodes_by_id.items():
        if node.node_type not in target_types:
            continue
        points = _node_position_points(
            node_id,
            nodes_by_id=nodes_by_id,
            has_geometry_index=has_geometry_index,
            has_ring_index=has_ring_index,
            has_pos_index=has_pos_index,
        )
        bbox = extract_bbox(points)
        if bbox is not None:
            node_bboxes[node_id] = bbox
    return node_bboxes


def _build_node_points(graph: SceneGraph, target_types: set[NodeType]) -> dict[str, list[Point3D]]:
    has_geometry_index = _edge_index(graph, RelationType.HAS_GEOMETRY)
    has_ring_index = _edge_index(graph, RelationType.HAS_RING)
    has_pos_index = _edge_index(graph, RelationType.HAS_POS)
    nodes_by_id = graph.nodes

    node_points: dict[str, list[Point3D]] = {}
    for node_id, node in nodes_by_id.items():
        if node.node_type not in target_types:
            continue
        points = _node_position_points(
            node_id,
            nodes_by_id=nodes_by_id,
            has_geometry_index=has_geometry_index,
            has_ring_index=has_ring_index,
            has_pos_index=has_pos_index,
        )
        if points:
            node_points[node_id] = points
    return node_points


def _build_node_polygon_rings(graph: SceneGraph, target_types: set[NodeType]) -> dict[str, list[list[Point3D]]]:
    has_geometry_index = _edge_index(graph, RelationType.HAS_GEOMETRY)
    has_ring_index = _edge_index(graph, RelationType.HAS_RING)
    has_pos_index = _edge_index(graph, RelationType.HAS_POS)
    nodes_by_id = graph.nodes

    node_rings: dict[str, list[list[Point3D]]] = {}
    for node_id, node in nodes_by_id.items():
        if node.node_type not in target_types:
            continue
        rings = _node_polygon_rings(
            node_id,
            nodes_by_id=nodes_by_id,
            has_geometry_index=has_geometry_index,
            has_ring_index=has_ring_index,
            has_pos_index=has_pos_index,
        )
        if rings:
            node_rings[node_id] = rings
    return node_rings


def _build_graph_summary(
    graph: SceneGraph,
    input_path: Path,
    scorecard: dict | None = None,
    neo4j_export: dict | None = None,
    stage_durations: dict[str, float] | None = None,
) -> dict:
    appearance_nodes = [node for node in graph.nodes.values() if node.node_type == NodeType.APPEARANCE]
    has_appearance_edges = [edge for edge in graph.edges if edge.relation == RelationType.HAS_APPEARANCE]
    linked_appearance_ids = {edge.target_id for edge in has_appearance_edges}
    owner_resolution_counts = Counter(
        str(node.properties.get("owner_resolution", "missing")) for node in appearance_nodes
    )
    appearance_coverage_score = 100.0
    if appearance_nodes:
        appearance_coverage_score = round((len(linked_appearance_ids) / len(appearance_nodes)) * 100.0, 2)

    node_counts = Counter(node.node_type.value for node in graph.nodes.values())
    edge_counts = Counter(edge.relation.value for edge in graph.edges)

    summary = {
        "input_path": str(input_path),
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "node_type_counts": dict(node_counts),
        "relation_counts": dict(edge_counts),
        "appearance_coverage": {
            "score": appearance_coverage_score,
            "appearance_node_count": len(appearance_nodes),
            "has_appearance_edge_count": len(has_appearance_edges),
            "linked_appearance_count": len(linked_appearance_ids),
            "unresolved_appearance_count": owner_resolution_counts.get("unresolved", 0),
            "owner_resolution_counts": dict(owner_resolution_counts),
        },
    }
    if scorecard is not None:
        summary["scorecard"] = scorecard
    if neo4j_export is not None:
        summary["neo4j_export"] = neo4j_export
    if stage_durations is not None:
        summary["stage_durations"] = {key: round(float(value), 6) for key, value in stage_durations.items()}

    return summary


def _count_generic_attribute_entries(graph: SceneGraph) -> int:
    total = 0
    for node in graph.nodes.values():
        for key in node.properties:
            if key.startswith("attr_") and not key.endswith("_uom"):
                total += 1
    return total


def _write_graph_to_neo4j(graph: SceneGraph, config_path: str | Path) -> dict:
    config = load_project_config(config_path)
    neo4j = config.neo4j
    client = Neo4jClient(
        uri=neo4j.uri,
        username=neo4j.username,
        password=neo4j.password,
        database=neo4j.database,
    )
    try:
        with client.session() as session:
            for statement in CONSTRAINTS:
                session.run(statement)

        writer = Neo4jWriter(client)
        reader = Neo4jReader(client)
        nodes = list(graph.nodes.values())
        edges = list(graph.edges)
        batch_size = max(1, int(getattr(neo4j, "batch_size", 5000)))

        last_node_percent = -1
        last_edge_percent = -1

        def _log_node_progress(done: int, total: int) -> None:
            nonlocal last_node_percent
            if total <= 0:
                return
            percent = int((done * 100) / total)
            if percent == last_node_percent and done < total:
                return
            last_node_percent = percent
            LOGGER.info(
                "[Neo4j] %-10s [%s] %6.2f%% (%d/%d)",
                "nodes",
                _progress_bar(done, total, width=24),
                (done / total) * 100.0,
                done,
                total,
            )

        def _log_edge_progress(done: int, total: int) -> None:
            nonlocal last_edge_percent
            if total <= 0:
                return
            percent = int((done * 100) / total)
            if percent == last_edge_percent and done < total:
                return
            last_edge_percent = percent
            LOGGER.info(
                "[Neo4j] %-10s [%s] %6.2f%% (%d/%d)",
                "edges",
                _progress_bar(done, total, width=24),
                (done / total) * 100.0,
                done,
                total,
            )

        writer.write_nodes(nodes, progress_callback=_log_node_progress, batch_size=batch_size)
        writer.write_edges(edges, progress_callback=_log_edge_progress, batch_size=batch_size)
        db_node_count = reader.fetch_node_count()
        return {
            "enabled": True,
            "success": True,
            "config_path": str(config_path),
            "uri": neo4j.uri,
            "database": neo4j.database,
            "written_nodes": len(nodes),
            "written_edges": len(edges),
            "batch_size": batch_size,
            "db_node_count": db_node_count,
        }
    finally:
        client.close()




def _is_door_or_window_opening(node: Node) -> bool:
    opening_type = str(
        node.properties.get("opening_type")
        or node.properties.get("source_tag")
        or ""
    )
    return opening_type in SPATIAL_OPENING_TYPES


def _is_connects_opening(node: Node) -> bool:
    opening_type = str(
        node.properties.get("opening_type")
        or node.properties.get("source_tag")
        or ""
    )
    return opening_type in CONNECTS_OPENING_TYPES


def _edge_index(graph: SceneGraph, relation: RelationType) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        if edge.relation == relation:
            index[edge.source_id].append(edge.target_id)
    return index


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


def _build_import_nodes(records: list[ElementRecord]) -> tuple[SceneGraph, int]:
    graph = SceneGraph()
    for record in records:
        graph.add_node(create_node(record.node_id, record.node_type, **record.properties))
    boundary_surface_type_nodes = _build_boundary_surface_type_nodes(graph, records)
    return graph, boundary_surface_type_nodes


def _build_import_geometry_and_spatial(
    graph: SceneGraph,
    root: Element,
    by_element: dict[Element, ElementRecord],
    *,
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
) -> tuple[int, int, int, int]:
    node_before = len(graph.nodes)
    edge_before = len(graph.edges)
    polygon_memberships = _attach_lod_geometry_structure(
        graph,
        root,
        by_element,
        build_parent_map=_build_parent_map,
        nearest_ancestor=_nearest_ancestor,
        fallback_id=_fallback_id,
        add_edge_if_valid=_add_edge_if_valid,
        object_node_types=OBJECT_NODE_TYPES,
    )
    _attach_geometry_subgraph(
        graph,
        root,
        by_element,
        build_parent_map=_build_parent_map,
        nearest_ancestor=_nearest_ancestor,
        fallback_id=_fallback_id,
        add_edge_if_valid=_add_edge_if_valid,
        object_node_types=OBJECT_NODE_TYPES,
        polygon_memberships=polygon_memberships,
    )
    _attach_appearance_subgraph(
        graph,
        root,
        by_element,
        build_parent_map=_build_parent_map,
        nearest_ancestor=_nearest_ancestor,
        fallback_id=_fallback_id,
        add_edge_if_valid=_add_edge_if_valid,
        object_node_types=OBJECT_NODE_TYPES,
    )
    connects_added = _augment_connects_edges(
        graph,
        touch_epsilon=touch_epsilon,
        adjacent_epsilon=adjacent_epsilon,
        intersection_epsilon=intersection_epsilon,
        edge_index=_edge_index,
        build_node_bboxes=_build_node_bboxes,
        add_edge_if_valid=_add_edge_if_valid,
        is_connects_opening=_is_connects_opening,
        semantic_hierarchy_relations=SEMANTIC_HIERARCHY_RELATIONS,
    )
    spatial_added = _build_spatial_edges(
        graph,
        touch_epsilon=touch_epsilon,
        adjacent_epsilon=adjacent_epsilon,
        intersection_epsilon=intersection_epsilon,
        edge_index=_edge_index,
        build_node_bboxes=_build_node_bboxes,
        build_node_points=_build_node_points,
        build_node_polygon_rings=_build_node_polygon_rings,
        add_edge_if_valid=_add_edge_if_valid,
        is_door_or_window_opening=_is_door_or_window_opening,
    )
    return len(graph.nodes) - node_before, len(graph.edges) - edge_before, connects_added, spatial_added


def _build_import_scorecard(
    graph: SceneGraph,
    root: Element,
    *,
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
) -> dict:
    return _build_scorecard(
        graph,
        root,
        touch_epsilon=touch_epsilon,
        adjacent_epsilon=adjacent_epsilon,
        intersection_epsilon=intersection_epsilon,
        semantic_tag_set=set(OBJECT_PARSERS.keys()),
        boundary_surface_tags=BOUNDARY_SURFACE_TAGS,
        opening_tags=OPENING_TAGS,
        connects_opening_types=CONNECTS_OPENING_TYPES,
        appearance_fallback_owner_tags=APPEARANCE_FALLBACK_OWNER_TAGS,
        semantic_node_types=SEMANTIC_NODE_TYPES,
        geometry_node_types=GEOMETRY_NODE_TYPES,
        build_parent_map=_build_parent_map,
        nearest_ancestor_by_tag=_nearest_ancestor_by_tag,
        direct_parent_tag=_direct_parent_tag,
        iter_ring_positions=_iter_ring_positions,
        normalize_target_refs=_normalize_target_refs,
        count_generic_attribute_entries=_count_generic_attribute_entries,
        build_room_spatial_scope=_build_room_spatial_scope,
        build_node_bboxes=_build_node_bboxes,
        build_node_points=_build_node_points,
        edge_index=_edge_index,
        is_door_or_window_opening=_is_door_or_window_opening,
        is_connects_opening=_is_connects_opening,
        touch_min_contact_area=DEFAULT_TOUCH_MIN_CONTACT_AREA,
        touch_min_contact_length=DEFAULT_TOUCH_MIN_CONTACT_LENGTH,
    )


def _write_import_json_output(
    graph: SceneGraph,
    *,
    source: Path,
    output_path: str,
    scorecard: dict,
    neo4j_export: dict | None,
    stage_durations: dict[str, float],
    t0_total: float,
) -> tuple[Path, float]:
    target = Path(output_path)
    ensure_dir(target.parent)
    t0 = perf_counter()
    summary = _build_graph_summary(
        graph,
        source,
        scorecard=scorecard,
        neo4j_export=neo4j_export,
        stage_durations=stage_durations,
    )
    duration_patch_offsets = write_graph_json_stream(
        target,
        summary=summary,
        nodes=(
            {
                "id": node.node_id,
                "type": node.node_type.value,
                "properties": node.properties,
            }
            for node in graph.nodes.values()
        ),
        edges=(
            {
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "relation": edge.relation.value,
                "properties": edge.properties,
            }
            for edge in graph.edges
        ),
        patchable_stage_duration_keys=("export_json", "total"),
    )
    t_export_json = perf_counter() - t0
    t_total = perf_counter() - t0_total
    stage_durations["export_json"] = t_export_json
    stage_durations["total"] = t_total
    patch_json_number_fields(
        target,
        duration_patch_offsets,
        {
            "export_json": t_export_json,
            "total": t_total,
        },
    )
    return target, t_export_json


def run_import_pipeline(
    input_path: str,
    output_path: str = "data/output/import_summary.json",
    to_neo4j: bool = False,
    config_path: str = "configs/default.yaml",
) -> int:
    t0_total = perf_counter()
    source = Path(input_path)
    if not source.exists():
        LOGGER.error("Input file does not exist: %s", source)
        return 2
    if source.is_dir():
        LOGGER.error("Directory input is not supported yet. Provide a .gml/.xml file path.")
        return 2

    touch_epsilon, adjacent_epsilon, intersection_epsilon = _resolve_spatial_thresholds(config_path)

    LOGGER.info("Import pipeline started: %s", source)
    LOGGER.info(
        "Spatial thresholds loaded: touch=%s adjacent=%s intersection=%s (config=%s)",
        touch_epsilon,
        adjacent_epsilon,
        intersection_epsilon,
        config_path,
    )
    timeline = _StageTimeline.from_stage_order(PIPELINE_STAGE_ORDER)

    timeline.start("parse_xml")
    t0 = perf_counter()
    root = read_citygml(source)
    t_parse_xml = perf_counter() - t0
    timeline.done("parse_xml", t_parse_xml)

    timeline.start("collect_semantics")
    t0 = perf_counter()
    records, by_element = _collect_records(root)
    t_collect_semantics = perf_counter() - t0
    timeline.done("collect_semantics", t_collect_semantics, detail=f"records={len(records)}")

    timeline.start("build_nodes")
    t0 = perf_counter()
    graph, boundary_surface_type_nodes = _build_import_nodes(records)
    t_build_nodes = perf_counter() - t0
    timeline.done(
        "build_nodes",
        t_build_nodes,
        detail=f"nodes={len(graph.nodes)}, boundary_surface_types={boundary_surface_type_nodes}",
    )

    t_build_semantic_edges = 0.0
    t_build_geometry = 0.0
    if records:
        timeline.start("build_semantic_edges")
        t0 = perf_counter()
        edge_before = len(graph.edges)
        _build_semantic_edges(graph, root, records, by_element)
        t_build_semantic_edges = perf_counter() - t0
        timeline.done(
            "build_semantic_edges",
            t_build_semantic_edges,
            detail=f"edges+={len(graph.edges) - edge_before}",
        )

        timeline.start("build_geometry")
        t0 = perf_counter()
        node_delta, edge_delta, connects_added, spatial_added = _build_import_geometry_and_spatial(
            graph,
            root,
            by_element,
            touch_epsilon=touch_epsilon,
            adjacent_epsilon=adjacent_epsilon,
            intersection_epsilon=intersection_epsilon,
        )
        t_build_geometry = perf_counter() - t0
        timeline.done(
            "build_geometry",
            t_build_geometry,
            detail=(
                f"nodes+={node_delta}, "
                f"edges+={edge_delta}, "
                f"connects_fallback+={connects_added}, spatial_edges+={spatial_added}"
            ),
        )
    else:
        timeline.skip("build_semantic_edges", detail="no semantic records")
        timeline.skip("build_geometry", detail="no semantic records")

    scorecard = _build_import_scorecard(
        graph,
        root,
        touch_epsilon=touch_epsilon,
        adjacent_epsilon=adjacent_epsilon,
        intersection_epsilon=intersection_epsilon,
    )
    neo4j_export: dict | None = {"enabled": False, "success": False}
    t_export_neo4j = 0.0
    if to_neo4j:
        timeline.start("export_neo4j", detail=config_path)
        t0 = perf_counter()
        try:
            neo4j_export = _write_graph_to_neo4j(graph, config_path)
            t_export_neo4j = perf_counter() - t0
            timeline.done(
                "export_neo4j",
                t_export_neo4j,
                detail=f"nodes={neo4j_export.get('written_nodes', 0)}, edges={neo4j_export.get('written_edges', 0)}",
            )
        except Exception as exc:  # pragma: no cover - depends on external runtime/service
            t_export_neo4j = perf_counter() - t0
            neo4j_export = {
                "enabled": True,
                "success": False,
                "config_path": str(config_path),
                "error": str(exc),
            }
            timeline.done("export_neo4j", t_export_neo4j, detail="FAILED")
            LOGGER.exception("Neo4j export failed: %s", exc)
    else:
        timeline.skip("export_neo4j", detail="disabled")

    stage_durations = {
        "parse_xml": t_parse_xml,
        "collect_semantics": t_collect_semantics,
        "build_nodes": t_build_nodes,
        "build_semantic_edges": t_build_semantic_edges,
        "build_geometry": t_build_geometry,
        "export_neo4j": t_export_neo4j,
        "export_json": 0.0,
        "total": 0.0,
    }
    timeline.start("export_json")
    target, t_export_json = _write_import_json_output(
        graph,
        source=source,
        output_path=output_path,
        scorecard=scorecard,
        neo4j_export=neo4j_export,
        stage_durations=stage_durations,
        t0_total=t0_total,
    )
    timeline.done("export_json", t_export_json, detail=str(target))

    _emit_conversion_report(
        graph,
        records_count=len(records),
        output_path=target,
        stage_durations=stage_durations,
        scorecard=scorecard,
        neo4j_export=neo4j_export,
        semantic_node_types=SEMANTIC_NODE_TYPES,
        geometry_node_types=GEOMETRY_NODE_TYPES,
        semantic_relations=SEMANTIC_RELATIONS,
        spatial_relations=SPATIAL_RELATIONS,
        geometry_relations=GEOMETRY_RELATIONS,
        pipeline_stage_order=PIPELINE_STAGE_ORDER,
        count_generic_attribute_entries=_count_generic_attribute_entries,
        edge_index=_edge_index,
        descendants=_descendants,
    )
    LOGGER.info("Import complete: nodes=%d edges=%d", len(graph.nodes), len(graph.edges))
    if to_neo4j and neo4j_export and not neo4j_export.get("success"):
        return 3
    return 0


def _execute_benchmark_query(
    session: object,
    query: str,
    *,
    warmup_runs: int,
    repeat_runs: int,
) -> tuple[int, list[float]]:
    for _ in range(max(0, warmup_runs)):
        session.run(query).single()

    timings_ms: list[float] = []
    result_count = 0
    for _ in range(max(1, repeat_runs)):
        t0 = perf_counter()
        record = session.run(query).single()
        elapsed_ms = (perf_counter() - t0) * 1000.0
        timings_ms.append(elapsed_ms)
        if record is not None:
            value = None
            keys = tuple(record.keys())
            if "count" in keys:
                value = record["count"]
            elif len(record) > 0:
                value = record[0]
            try:
                if value is not None:
                    result_count = int(value)
            except (TypeError, ValueError):
                pass
    return result_count, timings_ms


def run_benchmark_pipeline(
    config_path: str = "configs/default.yaml",
    output_path: str = "data/output/benchmark_report.json",
    *,
    warmup_runs: int = 1,
    repeat_runs: int = 3,
) -> int:
    LOGGER.info("Benchmark pipeline started")
    if repeat_runs <= 0:
        LOGGER.error("repeat_runs must be >= 1")
        return 2
    if warmup_runs < 0:
        LOGGER.error("warmup_runs must be >= 0")
        return 2

    config = load_project_config(config_path)
    neo4j = config.neo4j

    client = Neo4jClient(neo4j.uri, neo4j.username, neo4j.password, database=neo4j.database)
    reader = Neo4jReader(client)

    started_at = datetime.now(timezone.utc).isoformat()
    query_results: list[dict[str, object]] = []

    try:
        db_node_count = reader.fetch_node_count()
        LOGGER.info(
            "Benchmark target: uri=%s db=%s city_objects=%d warmup=%d repeat=%d",
            neo4j.uri,
            neo4j.database,
            db_node_count,
            warmup_runs,
            repeat_runs,
        )
        with client.session() as session:
            for query_id, name, query in BENCHMARK_QUERY_SET:
                try:
                    result_count, timings_ms = _execute_benchmark_query(
                        session,
                        query,
                        warmup_runs=warmup_runs,
                        repeat_runs=repeat_runs,
                    )
                    avg_ms = mean(timings_ms)
                    std_ms = pstdev(timings_ms) if len(timings_ms) > 1 else 0.0
                    result_entry = {
                        "id": query_id,
                        "name": name,
                        "query": query,
                        "result_count": int(result_count),
                        "timings_ms": [round(value, 3) for value in timings_ms],
                        "avg_ms": round(avg_ms, 3),
                        "min_ms": round(min(timings_ms), 3),
                        "max_ms": round(max(timings_ms), 3),
                        "std_ms": round(std_ms, 3),
                    }
                    query_results.append(result_entry)
                    LOGGER.info(
                        "[Benchmark] %s %-40s count=%d avg=%.3fms min=%.3fms max=%.3fms",
                        query_id,
                        name,
                        result_count,
                        avg_ms,
                        min(timings_ms),
                        max(timings_ms),
                    )
                except Exception as exc:  # pragma: no cover - external DB/runtime dependent
                    query_results.append(
                        {
                            "id": query_id,
                            "name": name,
                            "query": query,
                            "error": str(exc),
                        }
                    )
                    LOGGER.exception("[Benchmark] %s %s FAILED: %s", query_id, name, exc)

        successful_results = [entry for entry in query_results if "avg_ms" in entry]
        report = {
            "summary": {
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "config_path": str(config_path),
                "output_path": str(output_path),
                "neo4j_uri": neo4j.uri,
                "neo4j_database": neo4j.database,
                "city_object_count": int(db_node_count),
                "warmup_runs": int(warmup_runs),
                "repeat_runs": int(repeat_runs),
                "query_total": len(BENCHMARK_QUERY_SET),
                "query_success": len(successful_results),
                "query_failed": len(BENCHMARK_QUERY_SET) - len(successful_results),
                "avg_query_time_ms": round(
                    mean(float(entry["avg_ms"]) for entry in successful_results), 3
                )
                if successful_results
                else 0.0,
            },
            "queries": query_results,
        }

        output = Path(output_path)
        ensure_dir(output.parent)
        write_json(output, report)
        LOGGER.info("Benchmark report written: %s", output)
        return 0 if report["summary"]["query_failed"] == 0 else 3
    except Exception as exc:  # pragma: no cover - external DB/runtime dependent
        LOGGER.exception("Benchmark pipeline failed: %s", exc)
        return 3
    finally:
        client.close()
