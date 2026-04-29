"""Top-level pipeline orchestration."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from time import perf_counter
from typing import Callable, Iterator
from xml.etree.ElementTree import Element

from citygml_sg.domain.edge import Edge
from citygml_sg.domain.bbox import BBox
from citygml_sg.domain.enums import NodeType, RelationType
from citygml_sg.domain.geometry import Point3D
from citygml_sg.domain.node import Node
from citygml_sg.extractors.bbox_extractor import extract_bbox
from citygml_sg.graph.edge_factory import create_edge
from citygml_sg.graph.graph_builder import SceneGraph
from citygml_sg.graph.graph_schema import ALLOWED_RELATIONS, OBJECT_NODE_TYPES
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
from citygml_sg.config.settings import load_project_config
from citygml_sg.storage.json.writer import write_json
from citygml_sg.storage.neo4j.client import Neo4jClient
from citygml_sg.storage.neo4j.constraints import CONSTRAINTS
from citygml_sg.storage.neo4j.reader import Neo4jReader
from citygml_sg.storage.neo4j.writer import Neo4jWriter
from citygml_sg.relations.spatial_inference import infer_spatial_relation
from citygml_sg.relations.spatial_priority import normalize_spatial_precedence
from citygml_sg.utils.io import ensure_dir
from citygml_sg.utils.logging import get_logger
from citygml_sg.utils.xml import GENERIC_ATTRIBUTE_TAGS, get_gml_id, local_name

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
BOUNDARY_SURFACE_TYPE_NODE_PREFIX = "boundary_surface_type::"
APPEARANCE_FALLBACK_OWNER_PRIORITY: tuple[NodeType, ...] = (
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
)
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
}
SPATIAL_INFERRED_RELATIONS: set[RelationType] = {
    RelationType.ADJACENT_TO,
    RelationType.TOUCHES,
    RelationType.INTERSECTS,
}
SPATIAL_REQUIRED_METADATA_KEYS: tuple[str, ...] = (
    "method",
    "distance",
    "epsilon_touch",
    "epsilon_adjacent",
    "epsilon_intersection",
    "confidence",
    "computed_at",
)
GEOMETRY_RELATIONS: set[RelationType] = {
    RelationType.HAS_LOD_GEOMETRY,
    RelationType.HAS_GEOMETRY_COMPONENT,
    RelationType.HAS_GEOMETRY_MEMBER,
    RelationType.HAS_GEOMETRY,
    RelationType.HAS_RING,
    RelationType.HAS_POS,
}

# Score criteria (v1, CityGML 2.0 baseline)
SCORE_NODE_WEIGHT = 0.40
SCORE_RELATION_WEIGHT = 0.30
SCORE_PROPERTY_WEIGHT = 0.30
SCORE_CRITERIA_COMMENT = "overall=0.40*node + 0.30*relation + 0.30*property"
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
        "Q1",
        "furniture_furniture_intersects_pairs",
        (
            "MATCH (f1:BuildingFurniture)-[:INTERSECTS]->(f2:BuildingFurniture) "
            "WHERE f1.id < f2.id RETURN count(*) AS count"
        ),
    ),
    (
        "Q2",
        "furniture_opening_touches",
        "MATCH (:BuildingFurniture)-[:TOUCHES]->(:Opening) RETURN count(*) AS count",
    ),
    (
        "Q3",
        "furniture_boundary_adjacent",
        "MATCH (:BuildingFurniture)-[:ADJACENT_TO]->(:BoundarySurface) RETURN count(*) AS count",
    ),
    (
        "Q4",
        "opening_room_connects",
        "MATCH (:Opening)-[:CONNECTS]->(:Room) RETURN count(*) AS count",
    ),
    (
        "Q5",
        "room_internal_furniture_touching_opening",
        (
            "MATCH (f:BuildingFurniture)-[:INSIDE]->(r:Room)<-[:CONNECTS]-(o:Opening) "
            "MATCH (f)-[:TOUCHES]->(o) RETURN count(DISTINCT f) AS count"
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


def _parse_pos_text(text: str | None) -> list[float] | None:
    if not text:
        return None
    tokens = text.strip().split()
    values: list[float] = []
    for token in tokens:
        try:
            values.append(float(token))
        except ValueError:
            return None
    if not values:
        return None
    if len(values) == 1:
        return [values[0], 0.0, 0.0]
    if len(values) == 2:
        return [values[0], values[1], 0.0]
    return values[:3]


def _parse_pos_list(text: str | None, srs_dimension: str | None) -> list[list[float]]:
    if not text:
        return []

    raw_values: list[float] = []
    for token in text.strip().split():
        try:
            raw_values.append(float(token))
        except ValueError:
            return []

    if not raw_values:
        return []

    dimension = 3
    if srs_dimension and srs_dimension.isdigit():
        dimension = max(2, int(srs_dimension))

    if len(raw_values) % dimension != 0 and len(raw_values) % 3 == 0:
        dimension = 3

    positions: list[list[float]] = []
    for i in range(0, len(raw_values), dimension):
        chunk = raw_values[i : i + dimension]
        if len(chunk) < 2:
            continue
        if len(chunk) == 2:
            chunk.append(0.0)
        positions.append(chunk[:3])
    return positions


def _iter_ring_positions(ring_element: Element) -> Iterator[list[float]]:
    for child in list(ring_element):
        lname = local_name(child.tag)
        if lname == "pos":
            position = _parse_pos_text(child.text)
            if position is not None:
                yield position
        elif lname == "posList":
            for position in _parse_pos_list(child.text, child.get("srsDimension")):
                yield position


def _infer_lod_context(element: Element, parent_map: dict[Element, Element]) -> tuple[str | None, str | None]:
    current: Element | None = element
    while current is not None:
        lname = local_name(current.tag)
        lower = lname.lower()
        if lower.startswith("lod") and len(lower) >= 4 and lower[3].isdigit():
            return f"LoD{lower[3]}", lname
        current = parent_map.get(current)
    return None, None


def _attach_lod_geometry_structure(
    graph: SceneGraph,
    root: Element,
    by_element: dict[Element, ElementRecord],
) -> dict[Element, list[str]]:
    parent_map = _build_parent_map(root)
    fallback_counters: Counter[str] = Counter()
    concrete_geometry_node_by_element: dict[Element, tuple[str, NodeType]] = {}
    polygon_memberships: dict[Element, list[str]] = defaultdict(list)
    xlink_href_key = "{http://www.w3.org/1999/xlink}href"

    geometry_tag_to_type: dict[str, NodeType] = {
        "Solid": NodeType.SOLID,
        "MultiSurface": NodeType.MULTI_SURFACE,
        "MultiCurve": NodeType.MULTI_CURVE,
    }

    for element in root.iter():
        node_type = geometry_tag_to_type.get(local_name(element.tag))
        if node_type is None:
            continue

        owner = _nearest_ancestor(element, parent_map, by_element, OBJECT_NODE_TYPES)
        if owner is None:
            continue

        raw_id = get_gml_id(element) or _fallback_id(node_type, fallback_counters)
        concrete_node_id = f"{node_type.value.lower()}:{raw_id}"
        geometry_node_id = f"geometry:{node_type.value.lower()}:{raw_id}"
        lod_label, lod_source_tag = _infer_lod_context(element, parent_map)

        concrete_properties: dict[str, object] = {
            "gml_id": raw_id,
            "source_tag": local_name(element.tag),
        }
        if lod_label:
            concrete_properties["lod"] = lod_label
        if lod_source_tag:
            concrete_properties["lod_source_tag"] = lod_source_tag

        graph.add_node(create_node(concrete_node_id, node_type, **concrete_properties))

        geometry_properties: dict[str, object] = {
            "gml_id": raw_id,
            "source_tag": "Geometry",
            "geometry_type": local_name(element.tag),
        }
        if lod_label:
            geometry_properties["lod"] = lod_label
        if lod_source_tag:
            geometry_properties["lod_source_tag"] = lod_source_tag

        graph.add_node(create_node(geometry_node_id, NodeType.GEOMETRY, **geometry_properties))

        edge_props: dict[str, object] = {}
        if lod_label:
            edge_props["lod"] = lod_label
        if lod_source_tag:
            edge_props["lod_source_tag"] = lod_source_tag
        _add_edge_if_valid(
            graph,
            create_edge(owner.node_id, geometry_node_id, RelationType.HAS_LOD_GEOMETRY, **edge_props),
        )
        _add_edge_if_valid(
            graph,
            create_edge(geometry_node_id, concrete_node_id, RelationType.HAS_GEOMETRY_COMPONENT, **edge_props),
        )
        concrete_geometry_node_by_element[element] = (concrete_node_id, node_type)

    for element in root.iter():
        if local_name(element.tag) != "ImplicitGeometry":
            continue
        owner = _nearest_ancestor(element, parent_map, by_element, OBJECT_NODE_TYPES)
        if owner is None:
            continue

        raw_id = get_gml_id(element) or _fallback_id(NodeType.IMPLICIT_GEOMETRY, fallback_counters)
        implicit_node_id = f"implicit_geometry:{raw_id}"
        lod_label, lod_source_tag = _infer_lod_context(element, parent_map)

        properties: dict[str, object] = {
            "gml_id": raw_id,
            "source_tag": "ImplicitGeometry",
        }

        transformation_matrix: str | None = None
        relative_geometry_href: str | None = None
        reference_point: list[float] | None = None
        for child in element.iter():
            child_tag = local_name(child.tag)
            if transformation_matrix is None and child_tag == "transformationMatrix":
                transformation_matrix = child.text.strip() if child.text else None
            if relative_geometry_href is None and child_tag == "relativeGMLGeometry":
                relative_geometry_href = child.get(xlink_href_key) or child.get("href")
            if reference_point is None and child_tag == "pos":
                reference_point = _parse_pos_text(child.text)

        if lod_label:
            properties["lod"] = lod_label
        if lod_source_tag:
            properties["lod_source_tag"] = lod_source_tag
        if transformation_matrix:
            properties["transformation_matrix"] = transformation_matrix
        if relative_geometry_href:
            properties["relative_geometry_href"] = relative_geometry_href
        if reference_point:
            properties["reference_point"] = reference_point

        graph.add_node(create_node(implicit_node_id, NodeType.IMPLICIT_GEOMETRY, **properties))

        edge_props: dict[str, object] = {}
        if lod_label:
            edge_props["lod"] = lod_label
        if lod_source_tag:
            edge_props["lod_source_tag"] = lod_source_tag
        _add_edge_if_valid(
            graph,
            create_edge(owner.node_id, implicit_node_id, RelationType.HAS_LOD_GEOMETRY, **edge_props),
        )

    for geom_element, (geom_node_id, geom_node_type) in concrete_geometry_node_by_element.items():
        if geom_node_type not in {NodeType.SOLID, NodeType.MULTI_SURFACE}:
            continue
        for candidate in geom_element.iter():
            if local_name(candidate.tag) != "Polygon":
                continue
            memberships = polygon_memberships[candidate]
            if geom_node_id not in memberships:
                memberships.append(geom_node_id)

    return polygon_memberships


def _attach_geometry_subgraph(
    graph: SceneGraph,
    root: Element,
    by_element: dict[Element, ElementRecord],
    polygon_memberships: dict[Element, list[str]] | None = None,
) -> None:
    parent_map = _build_parent_map(root)
    fallback_counters: Counter[str] = Counter()
    added_geometry_members: set[tuple[str, str]] = set()

    for element in root.iter():
        if local_name(element.tag) != "Polygon":
            continue

        owner = _nearest_ancestor(element, parent_map, by_element, OBJECT_NODE_TYPES)
        if owner is None:
            continue

        raw_polygon_id = get_gml_id(element) or _fallback_id(NodeType.POLYGON, fallback_counters)
        polygon_node_id = f"polygon:{raw_polygon_id}"

        graph.add_node(
            create_node(
                polygon_node_id,
                NodeType.POLYGON,
                gml_id=raw_polygon_id,
                source_tag="Polygon",
            )
        )
        _add_edge_if_valid(
            graph,
            create_edge(owner.node_id, polygon_node_id, RelationType.HAS_GEOMETRY),
        )
        for geometry_node_id in (polygon_memberships or {}).get(element, []):
            key = (geometry_node_id, polygon_node_id)
            if key in added_geometry_members:
                continue
            _add_edge_if_valid(
                graph,
                create_edge(
                    geometry_node_id,
                    polygon_node_id,
                    RelationType.HAS_GEOMETRY_MEMBER,
                ),
            )
            added_geometry_members.add(key)

        ring_seq = 0
        for boundary in list(element):
            boundary_tag = local_name(boundary.tag)
            if boundary_tag not in {"exterior", "interior"}:
                continue

            for ring in list(boundary):
                if local_name(ring.tag) != "LinearRing":
                    continue

                raw_ring_id = get_gml_id(ring) or f"{raw_polygon_id}_ring_{ring_seq}"
                ring_seq += 1
                ring_node_id = f"ring:{raw_ring_id}"

                graph.add_node(
                    create_node(
                        ring_node_id,
                        NodeType.LINEAR_RING,
                        gml_id=raw_ring_id,
                        ring_type=boundary_tag,
                        source_tag="LinearRing",
                    )
                )
                _add_edge_if_valid(
                    graph,
                    create_edge(
                        polygon_node_id,
                        ring_node_id,
                        RelationType.HAS_RING,
                        ring_type=boundary_tag,
                    ),
                )

                for pos_index, coords in enumerate(_iter_ring_positions(ring)):
                    pos_node_id = f"pos:{raw_ring_id}:{pos_index}"
                    graph.add_node(
                        create_node(
                            pos_node_id,
                            NodeType.POSITION,
                            x=coords[0],
                            y=coords[1],
                            z=coords[2],
                            coordinates=coords,
                            order=pos_index,
                        )
                    )
                    _add_edge_if_valid(
                        graph,
                        create_edge(
                            ring_node_id,
                            pos_node_id,
                            RelationType.HAS_POS,
                            order=pos_index,
                        ),
                    )


def _normalize_target_refs(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    refs: list[str] = []
    for token in raw_value.strip().split():
        candidate = token.strip()
        if not candidate:
            continue
        if "#" in candidate:
            candidate = candidate.split("#", 1)[1]
        candidate = candidate.strip()
        if candidate:
            refs.append(candidate)
    return refs


def _first_direct_child_text(element: Element, child_name: str) -> str | None:
    for child in list(element):
        if local_name(child.tag) == child_name and child.text and child.text.strip():
            return child.text.strip()
    return None


def _attach_appearance_subgraph(
    graph: SceneGraph,
    root: Element,
    by_element: dict[Element, ElementRecord],
) -> None:
    parent_map = _build_parent_map(root)
    fallback_counters: Counter[str] = Counter()
    xlink_href_key = "{http://www.w3.org/1999/xlink}href"

    gml_id_to_node_ids: dict[str, list[str]] = defaultdict(list)
    for node_id, node in graph.nodes.items():
        raw_gml_id = node.properties.get("gml_id")
        if isinstance(raw_gml_id, str) and raw_gml_id.strip():
            gml_id_to_node_ids[raw_gml_id.strip()].append(node_id)

    fallback_owner: ElementRecord | None = None
    for owner_type in APPEARANCE_FALLBACK_OWNER_PRIORITY:
        for candidate_element in root.iter():
            candidate_record = by_element.get(candidate_element)
            if candidate_record is not None and candidate_record.node_type == owner_type:
                fallback_owner = candidate_record
                break
        if fallback_owner is not None:
            break

    for element in root.iter():
        if local_name(element.tag) != "Appearance":
            continue

        raw_appearance_id = get_gml_id(element) or _fallback_id(NodeType.APPEARANCE, fallback_counters)
        appearance_node_id = f"appearance:{raw_appearance_id}"
        theme = _first_direct_child_text(element, "theme")
        owner_resolution = "unresolved"
        owner = _nearest_ancestor(element, parent_map, by_element, OBJECT_NODE_TYPES)
        if owner is not None:
            owner_resolution = "ancestor"
        elif fallback_owner is not None:
            owner = fallback_owner
            owner_resolution = f"fallback:{fallback_owner.node_type.value}"
        appearance_properties: dict[str, object] = {
            "gml_id": raw_appearance_id,
            "source_tag": "Appearance",
            "owner_resolution": owner_resolution,
        }
        if theme:
            appearance_properties["theme"] = theme
        graph.add_node(create_node(appearance_node_id, NodeType.APPEARANCE, **appearance_properties))

        if owner is not None:
            _add_edge_if_valid(graph, create_edge(owner.node_id, appearance_node_id, RelationType.HAS_APPEARANCE))

        for surface_data_member in list(element):
            if local_name(surface_data_member.tag) != "surfaceDataMember":
                continue

            for surface_data in list(surface_data_member):
                surface_data_tag = local_name(surface_data.tag)
                raw_surface_data_id = get_gml_id(surface_data) or _fallback_id(NodeType.SURFACE_DATA, fallback_counters)
                surface_data_node_id = f"surface_data:{raw_surface_data_id}"

                surface_data_properties: dict[str, object] = {
                    "gml_id": raw_surface_data_id,
                    "source_tag": surface_data_tag,
                    "surface_data_type": surface_data_tag,
                }
                is_front_text = _first_direct_child_text(surface_data, "isFront")
                if is_front_text:
                    surface_data_properties["is_front"] = is_front_text.lower() == "true"

                for color_key, xml_key in {
                    "diffuse_color": "diffuseColor",
                    "specular_color": "specularColor",
                    "emissive_color": "emissiveColor",
                }.items():
                    color_text = _first_direct_child_text(surface_data, xml_key)
                    if color_text:
                        try:
                            surface_data_properties[color_key] = [float(token) for token in color_text.split()]
                        except ValueError:
                            surface_data_properties[color_key] = color_text

                for scalar_key, xml_key in {
                    "ambient_intensity": "ambientIntensity",
                    "shininess": "shininess",
                    "transparency": "transparency",
                }.items():
                    scalar_text = _first_direct_child_text(surface_data, xml_key)
                    if not scalar_text:
                        continue
                    try:
                        surface_data_properties[scalar_key] = float(scalar_text)
                    except ValueError:
                        surface_data_properties[scalar_key] = scalar_text

                image_uri = _first_direct_child_text(surface_data, "imageURI")
                if image_uri:
                    surface_data_properties["image_uri"] = image_uri

                target_refs: list[str] = []
                for child in surface_data.iter():
                    child_name = local_name(child.tag)
                    if child_name == "target":
                        target_refs.extend(_normalize_target_refs(child.text))
                    elif child_name == "targetUri":
                        target_refs.extend(_normalize_target_refs(child.text))
                    elif child_name in {"surfaceGeometry", "surfaceGeometryRef"}:
                        href_value = child.get(xlink_href_key) or child.get("href")
                        target_refs.extend(_normalize_target_refs(href_value))

                unique_target_refs = sorted(set(target_refs))
                if unique_target_refs:
                    surface_data_properties["target_count"] = len(unique_target_refs)
                    surface_data_properties["target_refs"] = unique_target_refs

                graph.add_node(create_node(surface_data_node_id, NodeType.SURFACE_DATA, **surface_data_properties))
                _add_edge_if_valid(
                    graph,
                    create_edge(appearance_node_id, surface_data_node_id, RelationType.HAS_SURFACE_DATA),
                )

                unmatched_target_refs: list[str] = []
                for target_ref in unique_target_refs:
                    target_node_ids = gml_id_to_node_ids.get(target_ref, [])
                    if not target_node_ids:
                        unmatched_target_refs.append(target_ref)
                        continue
                    for target_node_id in target_node_ids:
                        _add_edge_if_valid(
                            graph,
                            create_edge(
                                surface_data_node_id,
                                target_node_id,
                                RelationType.APPLIES_TO,
                                target_ref=target_ref,
                            ),
                        )

                if unmatched_target_refs:
                    node = graph.nodes.get(surface_data_node_id)
                    if node is not None:
                        node.properties["unmatched_target_count"] = len(unmatched_target_refs)
                        node.properties["unmatched_targets"] = unmatched_target_refs


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

            room = _nearest_ancestor(record.element, parent_map, by_element, {NodeType.ROOM})
            if room:
                _add_edge_if_valid(graph, create_edge(record.node_id, room.node_id, RelationType.CONNECTS))

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


def _add_spatial_edges_for_pairs(
    graph: SceneGraph,
    source_ids: list[str],
    target_ids: list[str],
    *,
    node_bboxes: dict[str, BBox],
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
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
            )
            if relation is None:
                continue
            before = len(graph.edges)
            _add_edge_if_valid(graph, create_edge(source_id, target_id, relation, **props))
            if len(graph.edges) > before:
                added += 1
    return added


def _build_spatial_edges(
    graph: SceneGraph,
    *,
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
) -> int:
    edge_count_before = len(graph.edges)
    nodes_by_id = graph.nodes
    inside_index = _edge_index(graph, RelationType.INSIDE)  # furniture -> room
    bounded_by_index = _edge_index(graph, RelationType.BOUNDED_BY)  # room -> boundary surface
    connects_index = _edge_index(graph, RelationType.CONNECTS)  # opening -> room

    room_to_furniture: dict[str, list[str]] = defaultdict(list)
    for furniture_id, room_ids in inside_index.items():
        if nodes_by_id.get(furniture_id) is None or nodes_by_id[furniture_id].node_type != NodeType.BUILDING_FURNITURE:
            continue
        for room_id in room_ids:
            if nodes_by_id.get(room_id) is None or nodes_by_id[room_id].node_type != NodeType.ROOM:
                continue
            room_to_furniture[room_id].append(furniture_id)

    room_to_opening: dict[str, list[str]] = defaultdict(list)
    for opening_id, room_ids in connects_index.items():
        opening_node = nodes_by_id.get(opening_id)
        if opening_node is None or opening_node.node_type != NodeType.OPENING:
            continue
        opening_type = str(
            opening_node.properties.get("opening_type")
            or opening_node.properties.get("source_tag")
            or ""
        )
        if opening_type not in SPATIAL_OPENING_TYPES:
            continue
        for room_id in room_ids:
            if nodes_by_id.get(room_id) is None or nodes_by_id[room_id].node_type != NodeType.ROOM:
                continue
            room_to_opening[room_id].append(opening_id)

    room_to_boundary: dict[str, list[str]] = defaultdict(list)
    for room_id, boundary_ids in bounded_by_index.items():
        if nodes_by_id.get(room_id) is None or nodes_by_id[room_id].node_type != NodeType.ROOM:
            continue
        room_to_boundary[room_id].extend(
            [
                boundary_id
                for boundary_id in boundary_ids
                if nodes_by_id.get(boundary_id) is not None
                and nodes_by_id[boundary_id].node_type == NodeType.BOUNDARY_SURFACE
            ]
        )

    target_types = {NodeType.BUILDING_FURNITURE, NodeType.BOUNDARY_SURFACE, NodeType.OPENING}
    node_bboxes = _build_node_bboxes(graph, target_types=target_types)

    for room_id, furniture_ids in room_to_furniture.items():
        unique_furniture_ids = sorted(set(furniture_ids))
        if not unique_furniture_ids:
            continue

        boundary_ids = sorted(set(room_to_boundary.get(room_id, [])))
        opening_ids = sorted(set(room_to_opening.get(room_id, [])))

        _add_spatial_edges_for_pairs(
            graph,
            unique_furniture_ids,
            boundary_ids,
            node_bboxes=node_bboxes,
            touch_epsilon=touch_epsilon,
            adjacent_epsilon=adjacent_epsilon,
            intersection_epsilon=intersection_epsilon,
        )
        _add_spatial_edges_for_pairs(
            graph,
            boundary_ids,
            unique_furniture_ids,
            node_bboxes=node_bboxes,
            touch_epsilon=touch_epsilon,
            adjacent_epsilon=adjacent_epsilon,
            intersection_epsilon=intersection_epsilon,
        )
        _add_spatial_edges_for_pairs(
            graph,
            unique_furniture_ids,
            opening_ids,
            node_bboxes=node_bboxes,
            touch_epsilon=touch_epsilon,
            adjacent_epsilon=adjacent_epsilon,
            intersection_epsilon=intersection_epsilon,
        )
        _add_spatial_edges_for_pairs(
            graph,
            opening_ids,
            unique_furniture_ids,
            node_bboxes=node_bboxes,
            touch_epsilon=touch_epsilon,
            adjacent_epsilon=adjacent_epsilon,
            intersection_epsilon=intersection_epsilon,
        )

        for i in range(len(unique_furniture_ids)):
            for j in range(i + 1, len(unique_furniture_ids)):
                first_id = unique_furniture_ids[i]
                second_id = unique_furniture_ids[j]
                _add_spatial_edges_for_pairs(
                    graph,
                    [first_id],
                    [second_id],
                    node_bboxes=node_bboxes,
                    touch_epsilon=touch_epsilon,
                    adjacent_epsilon=adjacent_epsilon,
                    intersection_epsilon=intersection_epsilon,
                )
                _add_spatial_edges_for_pairs(
                    graph,
                    [second_id],
                    [first_id],
                    node_bboxes=node_bboxes,
                    touch_epsilon=touch_epsilon,
                    adjacent_epsilon=adjacent_epsilon,
                    intersection_epsilon=intersection_epsilon,
                )

    normalized_edges, removed = normalize_spatial_precedence(graph.edges)
    if removed > 0:
        graph.replace_edges(normalized_edges)
        LOGGER.info(
            "[Spatial] precedence normalization applied: removed_weaker_edges=%d rule=INTERSECTS>TOUCHES>ADJACENT_TO",
            removed,
        )
    return len(graph.edges) - edge_count_before


def _graph_to_payload(
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

    return {
        "summary": {
            **summary,
        },
        "nodes": [
            {
                "id": node.node_id,
                "type": node.node_type.value,
                "properties": node.properties,
            }
            for node in graph.nodes.values()
        ],
        "edges": [
            {
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "relation": edge.relation.value,
                "properties": edge.properties,
            }
            for edge in graph.edges
        ],
    }


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


def _safe_ratio(actual: int, expected: int) -> float:
    if expected <= 0:
        return 1.0
    return min(actual / expected, 1.0)


def _is_door_or_window_opening(node: Node) -> bool:
    opening_type = str(
        node.properties.get("opening_type")
        or node.properties.get("source_tag")
        or ""
    )
    return opening_type in SPATIAL_OPENING_TYPES


def _spatial_pair_family(source_node: Node, target_node: Node) -> str | None:
    source_type = source_node.node_type
    target_type = target_node.node_type

    if {source_type, target_type} == {NodeType.BUILDING_FURNITURE, NodeType.BOUNDARY_SURFACE}:
        return "furniture_boundary_surface"
    if {source_type, target_type} == {NodeType.BUILDING_FURNITURE, NodeType.OPENING}:
        opening_node = source_node if source_type == NodeType.OPENING else target_node
        if not _is_door_or_window_opening(opening_node):
            return None
        return "furniture_opening"
    if source_type == NodeType.BUILDING_FURNITURE and target_type == NodeType.BUILDING_FURNITURE:
        return "furniture_furniture"
    return None


def _build_spatial_score_metrics(graph: SceneGraph) -> dict[str, object]:
    nodes_by_id = graph.nodes
    inside_index = _edge_index(graph, RelationType.INSIDE)  # furniture -> room
    bounded_by_index = _edge_index(graph, RelationType.BOUNDED_BY)  # room -> boundary surface
    connects_index = _edge_index(graph, RelationType.CONNECTS)  # opening -> room

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

    room_to_opening: dict[str, list[str]] = defaultdict(list)
    for opening_id, room_ids in connects_index.items():
        opening_node = nodes_by_id.get(opening_id)
        if opening_node is None or opening_node.node_type != NodeType.OPENING:
            continue
        if not _is_door_or_window_opening(opening_node):
            continue
        for room_id in room_ids:
            room_node = nodes_by_id.get(room_id)
            if room_node is None or room_node.node_type != NodeType.ROOM:
                continue
            room_to_opening[room_id].append(opening_id)

    target_types = {NodeType.BUILDING_FURNITURE, NodeType.BOUNDARY_SURFACE, NodeType.OPENING}
    node_bboxes = _build_node_bboxes(graph, target_types=target_types)

    candidate_counts: dict[str, int] = {
        "furniture_boundary_surface": 0,
        "furniture_opening": 0,
        "furniture_furniture": 0,
    }
    for room_id, furniture_ids in room_to_furniture.items():
        furniture_bbox_ids = sorted({node_id for node_id in furniture_ids if node_id in node_bboxes})
        boundary_bbox_ids = sorted({node_id for node_id in room_to_boundary.get(room_id, []) if node_id in node_bboxes})
        opening_bbox_ids = sorted({node_id for node_id in room_to_opening.get(room_id, []) if node_id in node_bboxes})

        candidate_counts["furniture_boundary_surface"] += len(furniture_bbox_ids) * len(boundary_bbox_ids) * 2
        candidate_counts["furniture_opening"] += len(furniture_bbox_ids) * len(opening_bbox_ids) * 2
        candidate_counts["furniture_furniture"] += len(furniture_bbox_ids) * max(len(furniture_bbox_ids) - 1, 0)

    family_relation_counts: dict[str, Counter[str]] = {
        "furniture_boundary_surface": Counter(),
        "furniture_opening": Counter(),
        "furniture_furniture": Counter(),
    }
    inferred_total = 0
    metadata_valid_total = 0
    schema_valid_total = 0
    pair_relations: dict[tuple[str, str], set[RelationType]] = defaultdict(set)

    for edge in graph.edges:
        if edge.relation not in SPATIAL_INFERRED_RELATIONS:
            continue
        source_node = nodes_by_id.get(edge.source_id)
        target_node = nodes_by_id.get(edge.target_id)
        if source_node is None or target_node is None:
            continue
        family = _spatial_pair_family(source_node, target_node)
        if family is None:
            continue

        inferred_total += 1
        family_relation_counts[family][edge.relation.value] += 1
        pair_relations[(edge.source_id, edge.target_id)].add(edge.relation)

        metadata = edge.properties
        has_required_keys = all(key in metadata for key in SPATIAL_REQUIRED_METADATA_KEYS)
        has_numeric_fields = (
            isinstance(metadata.get("distance"), (int, float))
            and isinstance(metadata.get("epsilon_touch"), (int, float))
            and isinstance(metadata.get("epsilon_adjacent"), (int, float))
            and isinstance(metadata.get("epsilon_intersection"), (int, float))
            and isinstance(metadata.get("confidence"), (int, float))
        )
        confidence = metadata.get("confidence")
        confidence_in_range = isinstance(confidence, (int, float)) and 0.0 <= float(confidence) <= 1.0
        method_is_string = isinstance(metadata.get("method"), str) and bool(str(metadata.get("method")).strip())
        computed_at_is_string = isinstance(metadata.get("computed_at"), str) and bool(
            str(metadata.get("computed_at")).strip()
        )
        if (
            has_required_keys
            and has_numeric_fields
            and confidence_in_range
            and method_is_string
            and computed_at_is_string
        ):
            metadata_valid_total += 1

        triple = (source_node.node_type, edge.relation, target_node.node_type)
        if triple in ALLOWED_RELATIONS:
            schema_valid_total += 1

    pair_count = len(pair_relations)
    precedence_valid_pairs = sum(1 for relations in pair_relations.values() if len(relations) <= 1)
    pair_conflict_count = sum(max(0, len(relations) - 1) for relations in pair_relations.values())

    metadata_ratio = _safe_ratio(metadata_valid_total, inferred_total)
    schema_ratio = _safe_ratio(schema_valid_total, inferred_total)
    precedence_ratio = _safe_ratio(precedence_valid_pairs, pair_count)
    precision_like_ratio = (metadata_ratio + schema_ratio + precedence_ratio) / 3.0

    expected_total = int(sum(candidate_counts.values()))

    pair_stats: dict[str, dict[str, object]] = {}
    for family, candidate_total in candidate_counts.items():
        relation_counts = family_relation_counts[family]
        pair_stats[family] = {
            "candidate_pairs": int(candidate_total),
            "inferred_total": int(sum(relation_counts.values())),
            "relation_counts": dict(relation_counts),
        }

    return {
        "spatial_coverage": {
            "score": round(_safe_ratio(inferred_total, expected_total) * 100.0, 2),
            "actual_total": int(inferred_total),
            "expected_total": int(expected_total),
            "definition": "candidate-hit-rate over directed candidate pairs in v1 scope",
        },
        "spatial_precision_sanity": {
            "score": round(precision_like_ratio * 100.0, 2),
            "inferred_total": int(inferred_total),
            "metadata_valid_total": int(metadata_valid_total),
            "schema_valid_total": int(schema_valid_total),
            "directed_pair_count": int(pair_count),
            "precedence_valid_pairs": int(precedence_valid_pairs),
            "pair_conflict_count": int(pair_conflict_count),
        },
        "spatial_pair_stats": pair_stats,
    }


def _build_scorecard(graph: SceneGraph, root: Element) -> dict:
    node_counts = Counter(node.node_type for node in graph.nodes.values())
    edge_counts = Counter(edge.relation for edge in graph.edges)
    parent_map = _build_parent_map(root)

    semantic_tag_set = set(OBJECT_PARSERS.keys())
    source_semantic_elements = [element for element in root.iter() if local_name(element.tag) in semantic_tag_set]
    source_boundary_elements = [element for element in root.iter() if local_name(element.tag) in BOUNDARY_SURFACE_TAGS]
    source_opening_elements = [element for element in root.iter() if local_name(element.tag) in OPENING_TAGS]
    source_appearance_elements = [element for element in root.iter() if local_name(element.tag) == "Appearance"]
    source_polygon_elements = [element for element in root.iter() if local_name(element.tag) == "Polygon"]
    source_lod_geometry_elements = [
        element for element in root.iter() if local_name(element.tag) in {"Solid", "MultiSurface", "MultiCurve"}
    ]
    source_implicit_geometry_elements = [element for element in root.iter() if local_name(element.tag) == "ImplicitGeometry"]

    expected_semantic_nodes = len(source_semantic_elements)
    actual_semantic_nodes = sum(node_counts[node_type] for node_type in SEMANTIC_NODE_TYPES)

    expected_has_geometry = 0
    expected_has_ring = 0
    expected_has_pos = 0
    expected_has_lod_geometry = 0
    expected_has_geometry_component = 0
    expected_has_geometry_member = 0
    for geometry_element in source_lod_geometry_elements:
        if _nearest_ancestor_by_tag(geometry_element, parent_map, semantic_tag_set) is None:
            continue
        expected_has_lod_geometry += 1
        expected_has_geometry_component += 1
        geometry_tag = local_name(geometry_element.tag)
        if geometry_tag not in {"Solid", "MultiSurface"}:
            continue
        expected_has_geometry_member += sum(
            1 for candidate in geometry_element.iter() if local_name(candidate.tag) == "Polygon"
        )
    for implicit_geometry in source_implicit_geometry_elements:
        if _nearest_ancestor_by_tag(implicit_geometry, parent_map, semantic_tag_set) is None:
            continue
        expected_has_lod_geometry += 1

    for polygon in source_polygon_elements:
        if _nearest_ancestor_by_tag(polygon, parent_map, semantic_tag_set) is None:
            continue
        expected_has_geometry += 1
        for boundary in list(polygon):
            if local_name(boundary.tag) not in {"exterior", "interior"}:
                continue
            for ring in list(boundary):
                if local_name(ring.tag) != "LinearRing":
                    continue
                expected_has_ring += 1
                expected_has_pos += sum(1 for _ in _iter_ring_positions(ring))

    expected_geometry_nodes = (
        expected_has_lod_geometry
        + expected_has_geometry_component
        + expected_has_geometry
        + expected_has_ring
        + expected_has_pos
    )
    actual_geometry_nodes = sum(node_counts[node_type] for node_type in GEOMETRY_NODE_TYPES)

    # Fair scoring policy (CityGML 2.0, current supported scope):
    # 1) Expected counts are computed only from object/relation/property channels that
    #    are explicitly supported by this pipeline (not from all possible XML elements).
    # 2) Expected relation counts follow schema-allowed structural links reconstructed
    #    from source hierarchy.
    # 3) Property expectations are counted only on semantic target elements where the
    #    corresponding direct child tags actually exist.
    node_coverage_ratio = _safe_ratio(
        actual_semantic_nodes + actual_geometry_nodes,
        expected_semantic_nodes + expected_geometry_nodes,
    )

    expected_bounded_by = sum(
        1
        for boundary in source_boundary_elements
        if _nearest_ancestor_by_tag(
            boundary,
            parent_map,
            {"Building", "BuildingPart", "Room", "BuildingInstallation", "IntBuildingInstallation"},
        )
        is not None
    )
    expected_has_surface_type = len(source_boundary_elements)
    expected_has_opening = sum(
        1
        for opening in source_opening_elements
        if _nearest_ancestor_by_tag(opening, parent_map, BOUNDARY_SURFACE_TAGS) is not None
    )
    expected_connects = sum(
        1
        for opening in source_opening_elements
        if _nearest_ancestor_by_tag(opening, parent_map, {"Room"}) is not None
    )
    expected_has_city_object = sum(
        1
        for element in source_semantic_elements
        if _direct_parent_tag(element, parent_map) == "cityObjectMember"
        and _nearest_ancestor_by_tag(element, parent_map, {"cityObjectMember"}) is not None
    )
    expected_has_group_member = sum(
        1
        for element in source_semantic_elements
        if _direct_parent_tag(element, parent_map) == "groupMember"
        and _nearest_ancestor_by_tag(element, parent_map, {"CityObjectGroup"}) is not None
    )
    has_appearance_fallback_owner = any(
        local_name(element.tag) in APPEARANCE_FALLBACK_OWNER_TAGS for element in source_semantic_elements
    )
    expected_has_appearance = sum(
        1
        for appearance in source_appearance_elements
        if _nearest_ancestor_by_tag(appearance, parent_map, semantic_tag_set) is not None or has_appearance_fallback_owner
    )
    expected_has_surface_data = sum(
        1
        for appearance in source_appearance_elements
        for member in list(appearance)
        if local_name(member.tag) == "surfaceDataMember"
        for surface_data in list(member)
        if isinstance(surface_data.tag, str)
    )
    expected_applies_to = sum(
        len(
            set(
                ref
                for child in surface_data.iter()
                if local_name(child.tag) in {"target", "targetUri"}
                for ref in _normalize_target_refs(child.text)
            )
        )
        for appearance in source_appearance_elements
        for member in list(appearance)
        if local_name(member.tag) == "surfaceDataMember"
        for surface_data in list(member)
        if isinstance(surface_data.tag, str)
    )
    expected_consists_of_building_part = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "BuildingPart"
        and _direct_parent_tag(element, parent_map) == "consistsOfBuildingPart"
        and _nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
    )
    expected_interior_room = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "Room"
        and _direct_parent_tag(element, parent_map) == "interiorRoom"
        and _nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
    )
    expected_interior_furniture = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "BuildingFurniture"
        and _direct_parent_tag(element, parent_map) == "interiorFurniture"
        and _nearest_ancestor_by_tag(element, parent_map, {"Room"}) is not None
    )
    expected_outer_building_installation = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "BuildingInstallation"
        and _direct_parent_tag(element, parent_map) == "outerBuildingInstallation"
        and _nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
    )
    expected_interior_building_installation = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "IntBuildingInstallation"
        and _direct_parent_tag(element, parent_map) == "interiorBuildingInstallation"
        and _nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
    )
    expected_room_installation = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "IntBuildingInstallation"
        and _direct_parent_tag(element, parent_map) == "roomInstallation"
        and _nearest_ancestor_by_tag(element, parent_map, {"Room"}) is not None
    )
    expected_contains = (
        sum(
            1
            for element in source_semantic_elements
            if local_name(element.tag) == "BuildingPart"
            and _direct_parent_tag(element, parent_map) != "consistsOfBuildingPart"
            and _nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
        )
        + sum(
            1
            for element in source_semantic_elements
            if local_name(element.tag) == "Room"
            and _direct_parent_tag(element, parent_map) != "interiorRoom"
            and _nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
        )
        + sum(
            1
            for element in source_semantic_elements
            if local_name(element.tag) == "BuildingFurniture"
            and _direct_parent_tag(element, parent_map) != "interiorFurniture"
            and _nearest_ancestor_by_tag(element, parent_map, {"Room"}) is not None
        )
        + sum(
            1
            for element in source_semantic_elements
            if local_name(element.tag) == "BuildingInstallation"
            and _direct_parent_tag(element, parent_map) != "outerBuildingInstallation"
            and _nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
        )
        + sum(
            1
            for element in source_semantic_elements
            if local_name(element.tag) == "IntBuildingInstallation"
            and _direct_parent_tag(element, parent_map) not in {"interiorBuildingInstallation", "roomInstallation"}
            and _nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart", "Room"}) is not None
        )
    )
    expected_inside = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "BuildingFurniture"
        and _nearest_ancestor_by_tag(element, parent_map, {"Room"}) is not None
    )
    expected_has_address = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "Address"
        and _nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
    )

    relation_expectations: dict[RelationType, int] = {
        RelationType.HAS_CITY_OBJECT: expected_has_city_object,
        RelationType.HAS_GROUP_MEMBER: expected_has_group_member,
        RelationType.HAS_APPEARANCE: expected_has_appearance,
        RelationType.HAS_SURFACE_DATA: expected_has_surface_data,
        RelationType.APPLIES_TO: expected_applies_to,
        RelationType.CONTAINS: expected_contains,
        RelationType.CONSISTS_OF_BUILDING_PART: expected_consists_of_building_part,
        RelationType.INTERIOR_ROOM: expected_interior_room,
        RelationType.OUTER_BUILDING_INSTALLATION: expected_outer_building_installation,
        RelationType.INTERIOR_BUILDING_INSTALLATION: expected_interior_building_installation,
        RelationType.ROOM_INSTALLATION: expected_room_installation,
        RelationType.INTERIOR_FURNITURE: expected_interior_furniture,
        RelationType.INSIDE: expected_inside,
        RelationType.BOUNDED_BY: expected_bounded_by,
        RelationType.HAS_SURFACE_TYPE: expected_has_surface_type,
        RelationType.HAS_OPENING: expected_has_opening,
        RelationType.HAS_ADDRESS: expected_has_address,
        RelationType.HAS_LOD_GEOMETRY: expected_has_lod_geometry,
        RelationType.HAS_GEOMETRY_COMPONENT: expected_has_geometry_component,
        RelationType.HAS_GEOMETRY_MEMBER: expected_has_geometry_member,
        RelationType.CONNECTS: expected_connects,
        RelationType.HAS_GEOMETRY: expected_has_geometry,
        RelationType.HAS_RING: expected_has_ring,
        RelationType.HAS_POS: expected_has_pos,
    }
    relation_scores = [
        _safe_ratio(edge_counts[relation], expected)
        for relation, expected in relation_expectations.items()
        if expected > 0
    ]
    relation_coverage_ratio = (sum(relation_scores) / len(relation_scores)) if relation_scores else 1.0

    semantic_nodes = [node for node in graph.nodes.values() if node.node_type in SEMANTIC_NODE_TYPES]

    def _has_direct_child(element: Element, child_tag: str) -> bool:
        return any(local_name(child.tag) == child_tag for child in list(element))

    expected_property_counts = {
        "gml_name": sum(1 for element in source_semantic_elements if _has_direct_child(element, "name")),
        "gml_description": sum(1 for element in source_semantic_elements if _has_direct_child(element, "description")),
        "creation_date": sum(1 for element in source_semantic_elements if _has_direct_child(element, "creationDate")),
        "relative_to_terrain": sum(1 for element in source_semantic_elements if _has_direct_child(element, "relativeToTerrain")),
        "class_code": sum(1 for element in source_semantic_elements if _has_direct_child(element, "class")),
        "function_code": sum(1 for element in source_semantic_elements if _has_direct_child(element, "function")),
        "usage_code": sum(1 for element in source_semantic_elements if _has_direct_child(element, "usage")),
        "year_of_construction": sum(1 for element in source_semantic_elements if _has_direct_child(element, "yearOfConstruction")),
        "roof_type_code": sum(1 for element in source_semantic_elements if _has_direct_child(element, "roofType")),
        "measured_height": sum(1 for element in source_semantic_elements if _has_direct_child(element, "measuredHeight")),
        "storeys_above_ground": sum(1 for element in source_semantic_elements if _has_direct_child(element, "storeysAboveGround")),
        "storeys_below_ground": sum(1 for element in source_semantic_elements if _has_direct_child(element, "storeysBelowGround")),
        "generic_attributes": sum(
            1
            for element in source_semantic_elements
            for child in list(element)
            if local_name(child.tag) in GENERIC_ATTRIBUTE_TAGS
        ),
    }
    actual_property_counts = {
        "gml_name": sum(1 for node in semantic_nodes if "gml_name" in node.properties),
        "gml_description": sum(1 for node in semantic_nodes if "gml_description" in node.properties),
        "creation_date": sum(1 for node in semantic_nodes if "creation_date" in node.properties),
        "relative_to_terrain": sum(1 for node in semantic_nodes if "relative_to_terrain" in node.properties),
        "class_code": sum(1 for node in semantic_nodes if "class_code" in node.properties),
        "function_code": sum(1 for node in semantic_nodes if "function_code" in node.properties),
        "usage_code": sum(1 for node in semantic_nodes if "usage_code" in node.properties),
        "year_of_construction": sum(1 for node in semantic_nodes if "year_of_construction" in node.properties),
        "roof_type_code": sum(1 for node in semantic_nodes if "roof_type_code" in node.properties),
        "measured_height": sum(1 for node in semantic_nodes if "measured_height" in node.properties),
        "storeys_above_ground": sum(1 for node in semantic_nodes if "storeys_above_ground" in node.properties),
        "storeys_below_ground": sum(1 for node in semantic_nodes if "storeys_below_ground" in node.properties),
        "generic_attributes": _count_generic_attribute_entries(graph),
    }
    expected_properties_total = sum(expected_property_counts.values())
    actual_properties_total = sum(actual_property_counts.values())
    property_coverage_ratio = _safe_ratio(actual_properties_total, expected_properties_total)

    overall_score = (
        node_coverage_ratio * SCORE_NODE_WEIGHT
        + relation_coverage_ratio * SCORE_RELATION_WEIGHT
        + property_coverage_ratio * SCORE_PROPERTY_WEIGHT
    ) * 100.0
    spatial_metrics = _build_spatial_score_metrics(graph)

    return {
        "overall_score": round(overall_score, 2),
        "node_coverage": {
            "score": round(node_coverage_ratio * 100.0, 2),
            "actual_total": actual_semantic_nodes + actual_geometry_nodes,
            "expected_total": expected_semantic_nodes + expected_geometry_nodes,
        },
        "relation_coverage": {
            "score": round(relation_coverage_ratio * 100.0, 2),
            "actual_total": int(sum(edge_counts[relation] for relation in relation_expectations)),
            "expected_total": int(sum(relation_expectations.values())),
        },
        "property_coverage": {
            "score": round(property_coverage_ratio * 100.0, 2),
            "actual_total": int(actual_properties_total),
            "expected_total": int(expected_properties_total),
        },
        **spatial_metrics,
        "criteria_comment": SCORE_CRITERIA_COMMENT,
    }


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


def _format_counter(counter: Counter) -> str:
    items = sorted(counter.items(), key=lambda item: (str(item[0]), item[1]))
    return ", ".join(f"{key}={value}" for key, value in items)


def _avg(values: list[int]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _log_separator(char: str = "-", width: int = 72) -> None:
    LOGGER.info(char * width)


def _log_metric(label: str, value: object) -> None:
    LOGGER.info("  %-36s : %s", label, value)


def _log_section(title: str) -> None:
    LOGGER.info("")
    _log_separator("-")
    LOGGER.info("%s", title)
    _log_separator("-")


def _progress_bar(done: int, total: int, width: int = 26) -> str:
    if total <= 0:
        return "-" * width
    ratio = max(0.0, min(done / total, 1.0))
    filled = int(round(width * ratio))
    return "#" * filled + "-" * (width - filled)


def _duration_bar(seconds: float, max_seconds: float, width: int = 26) -> str:
    if max_seconds <= 0.0:
        return "-" * width
    ratio = max(0.0, min(seconds / max_seconds, 1.0))
    filled = int(round(width * ratio))
    return "#" * filled + "-" * (width - filled)


def _log_stage_timeline(
    stage_name: str,
    stage_index: int,
    total_stages: int,
    event: str,
    elapsed_seconds: float | None = None,
    detail: str | None = None,
) -> None:
    done = stage_index if event in {"DONE", "SKIP"} else max(stage_index - 1, 0)
    bar = _progress_bar(done, total_stages)
    suffix_parts: list[str] = []
    if elapsed_seconds is not None:
        suffix_parts.append(f"{elapsed_seconds:.3f}s")
    if detail:
        suffix_parts.append(detail)
    suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
    LOGGER.info(
        "[Timeline] [%d/%d] [%s] %s %s%s",
        stage_index,
        total_stages,
        bar,
        stage_name,
        event,
        suffix,
    )


def _emit_conversion_report(
    graph: SceneGraph,
    records_count: int,
    output_path: Path,
    stage_durations: dict[str, float],
    scorecard: dict,
    neo4j_export: dict | None = None,
) -> None:
    node_counts = Counter(node.node_type for node in graph.nodes.values())
    edge_counts = Counter(edge.relation for edge in graph.edges)
    nodes_by_id = graph.nodes
    appearance_nodes = [node for node in graph.nodes.values() if node.node_type == NodeType.APPEARANCE]
    has_appearance_edges = [edge for edge in graph.edges if edge.relation == RelationType.HAS_APPEARANCE]
    linked_appearance_ids = {edge.target_id for edge in has_appearance_edges}
    owner_resolution_counts = Counter(
        str(node.properties.get("owner_resolution", "missing")) for node in appearance_nodes
    )

    building_count = node_counts[NodeType.BUILDING]
    semantic_node_count = sum(node_counts[node_type] for node_type in SEMANTIC_NODE_TYPES)
    geometry_node_count = sum(node_counts[node_type] for node_type in GEOMETRY_NODE_TYPES)
    semantic_relation_count = sum(edge_counts[relation] for relation in SEMANTIC_RELATIONS)
    spatial_relation_count = sum(edge_counts[relation] for relation in SPATIAL_RELATIONS)
    geometry_relation_count = sum(edge_counts[relation] for relation in GEOMETRY_RELATIONS)

    nodes_with_gml_name = sum(1 for node in graph.nodes.values() if "gml_name" in node.properties)
    nodes_with_generic_attributes = sum(
        1
        for node in graph.nodes.values()
        if any(key.startswith("attr_") and not key.endswith("_uom") for key in node.properties)
    )
    generic_attribute_entries = _count_generic_attribute_entries(graph)

    theme_coverage = sum(
        1
        for value in [
            semantic_node_count > 0,
            geometry_node_count > 0,
            semantic_relation_count > 0,
            spatial_relation_count > 0,
            geometry_relation_count > 0,
        ]
        if value
    )

    rings_per_polygon: list[int] = []
    pos_per_ring: list[int] = []
    has_ring_index = _edge_index(graph, RelationType.HAS_RING)
    has_pos_index = _edge_index(graph, RelationType.HAS_POS)
    for polygon_id, rings in has_ring_index.items():
        rings_per_polygon.append(len(rings))
        for ring_id in rings:
            pos_per_ring.append(len(has_pos_index.get(ring_id, [])))

    relation_counts_fmt = _format_counter(Counter({k.value: v for k, v in edge_counts.items()}))
    node_counts_fmt = _format_counter(Counter({k.value: v for k, v in node_counts.items()}))

    LOGGER.info("")
    _log_separator("=")
    LOGGER.info("CITYGML SCENE GRAPH CONVERSION REPORT (BUILDING-CENTRIC)")
    _log_separator("=")

    _log_section("Summary")
    _log_metric("Main feature count (Building)", building_count)
    _log_metric("Theme coverage", f"{theme_coverage}/5")
    _log_metric("Semantic nodes", semantic_node_count)
    _log_metric("Geometry nodes", geometry_node_count)
    _log_metric("Semantic relations", semantic_relation_count)
    _log_metric("Spatial relations", spatial_relation_count)
    _log_metric("Geometry relations", geometry_relation_count)
    _log_metric("Total nodes", len(graph.nodes))
    _log_metric("Total edges", len(graph.edges))
    _log_metric(
        "Scorecard",
        (
            "overall=%.2f node=%.2f(%d/%d) relation=%.2f(%d/%d) property=%.2f(%d/%d)"
            % (
                scorecard["overall_score"],
                scorecard["node_coverage"]["score"],
                scorecard["node_coverage"]["actual_total"],
                scorecard["node_coverage"]["expected_total"],
                scorecard["relation_coverage"]["score"],
                scorecard["relation_coverage"]["actual_total"],
                scorecard["relation_coverage"]["expected_total"],
                scorecard["property_coverage"]["score"],
                scorecard["property_coverage"]["actual_total"],
                scorecard["property_coverage"]["expected_total"],
            )
        ),
    )
    _log_metric("Score criteria", scorecard["criteria_comment"])
    if "spatial_coverage" in scorecard:
        spatial_coverage = scorecard["spatial_coverage"]
        _log_metric(
            "Spatial coverage",
            "score=%.2f(%d/%d)"
            % (
                spatial_coverage.get("score", 0.0),
                spatial_coverage.get("actual_total", 0),
                spatial_coverage.get("expected_total", 0),
            ),
        )
    if "spatial_precision_sanity" in scorecard:
        spatial_sanity = scorecard["spatial_precision_sanity"]
        _log_metric(
            "Spatial precision-like sanity",
            "score=%.2f inferred=%d metadata_valid=%d schema_valid=%d pair_conflicts=%d"
            % (
                spatial_sanity.get("score", 0.0),
                spatial_sanity.get("inferred_total", 0),
                spatial_sanity.get("metadata_valid_total", 0),
                spatial_sanity.get("schema_valid_total", 0),
                spatial_sanity.get("pair_conflict_count", 0),
            ),
        )
    if "spatial_pair_stats" in scorecard:
        pair_stats = scorecard["spatial_pair_stats"]
        _log_metric(
            "Spatial pair stats",
            ", ".join(
                "%s(candidates=%d,inferred=%d)"
                % (
                    name,
                    stats.get("candidate_pairs", 0),
                    stats.get("inferred_total", 0),
                )
                for name, stats in pair_stats.items()
            ),
        )

    _log_section("Distribution")
    _log_metric("Node type counts", node_counts_fmt)
    _log_metric("Relation counts", relation_counts_fmt)
    _log_metric(
        "Object counts",
        (
            "CityObjectMember=%d CityObjectGroup=%d "
            "Building=%d BuildingPart=%d Room=%d BuildingInstallation=%d IntBuildingInstallation=%d "
            "BoundarySurface=%d BoundarySurfaceType=%d Opening=%d BuildingFurniture=%d Address=%d Appearance=%d SurfaceData=%d "
            "Geometry=%d ImplicitGeometry=%d Solid=%d MultiSurface=%d MultiCurve=%d Polygon=%d LinearRing=%d Position=%d"
        )
        % (
            node_counts[NodeType.CITY_OBJECT_MEMBER],
            node_counts[NodeType.CITY_OBJECT_GROUP],
            node_counts[NodeType.BUILDING],
            node_counts[NodeType.BUILDING_PART],
            node_counts[NodeType.ROOM],
            node_counts[NodeType.BUILDING_INSTALLATION],
            node_counts[NodeType.INT_BUILDING_INSTALLATION],
            node_counts[NodeType.BOUNDARY_SURFACE],
            node_counts[NodeType.BOUNDARY_SURFACE_TYPE],
            node_counts[NodeType.OPENING],
            node_counts[NodeType.BUILDING_FURNITURE],
            node_counts[NodeType.ADDRESS],
            node_counts[NodeType.APPEARANCE],
            node_counts[NodeType.SURFACE_DATA],
            node_counts[NodeType.GEOMETRY],
            node_counts[NodeType.IMPLICIT_GEOMETRY],
            node_counts[NodeType.SOLID],
            node_counts[NodeType.MULTI_SURFACE],
            node_counts[NodeType.MULTI_CURVE],
            node_counts[NodeType.POLYGON],
            node_counts[NodeType.LINEAR_RING],
            node_counts[NodeType.POSITION],
        ),
    )

    _log_section("Property Enrichment")
    _log_metric("Nodes with gml_name", nodes_with_gml_name)
    _log_metric("Nodes with generic attributes", nodes_with_generic_attributes)
    _log_metric("Generic attribute entries", generic_attribute_entries)
    _log_metric(
        "gml_name coverage",
        f"{((nodes_with_gml_name / semantic_node_count * 100.0) if semantic_node_count else 0.0):.2f}%",
    )
    _log_metric(
        "generic attribute coverage",
        f"{((nodes_with_generic_attributes / semantic_node_count * 100.0) if semantic_node_count else 0.0):.2f}%",
    )
    _log_metric(
        "avg attr entries / attr node",
        f"{((generic_attribute_entries / nodes_with_generic_attributes) if nodes_with_generic_attributes else 0.0):.2f}",
    )

    _log_section("Appearance Coverage")
    _log_metric("Appearance nodes", len(appearance_nodes))
    _log_metric("HAS_APPEARANCE edges", len(has_appearance_edges))
    _log_metric("Linked appearances", len(linked_appearance_ids))
    _log_metric("Unresolved appearances", owner_resolution_counts.get("unresolved", 0))
    _log_metric(
        "Owner resolution counts",
        ", ".join(f"{k}={v}" for k, v in sorted(owner_resolution_counts.items())),
    )

    _log_section("Geometry Density")
    _log_metric("avg rings / polygon", f"{_avg(rings_per_polygon):.2f}")
    _log_metric("avg positions / ring", f"{_avg(pos_per_ring):.2f}")
    _log_metric("max positions / ring", max(pos_per_ring) if pos_per_ring else 0)

    contains_index = _edge_index(graph, RelationType.CONTAINS)
    consists_of_building_part_index = _edge_index(graph, RelationType.CONSISTS_OF_BUILDING_PART)
    interior_room_index = _edge_index(graph, RelationType.INTERIOR_ROOM)
    outer_building_installation_index = _edge_index(graph, RelationType.OUTER_BUILDING_INSTALLATION)
    interior_building_installation_index = _edge_index(graph, RelationType.INTERIOR_BUILDING_INSTALLATION)
    room_installation_index = _edge_index(graph, RelationType.ROOM_INSTALLATION)
    interior_furniture_index = _edge_index(graph, RelationType.INTERIOR_FURNITURE)
    bounded_by_index = _edge_index(graph, RelationType.BOUNDED_BY)
    has_opening_index = _edge_index(graph, RelationType.HAS_OPENING)
    has_address_index = _edge_index(graph, RelationType.HAS_ADDRESS)
    has_lod_geometry_index = _edge_index(graph, RelationType.HAS_LOD_GEOMETRY)
    has_geometry_component_index = _edge_index(graph, RelationType.HAS_GEOMETRY_COMPONENT)
    has_geometry_index = _edge_index(graph, RelationType.HAS_GEOMETRY)

    hierarchy_index: dict[str, list[str]] = defaultdict(list)
    for index in [
        contains_index,
        consists_of_building_part_index,
        interior_room_index,
        outer_building_installation_index,
        interior_building_installation_index,
        room_installation_index,
        interior_furniture_index,
    ]:
        for source_id, target_ids in index.items():
            hierarchy_index[source_id].extend(target_ids)

    building_ids = sorted(
        [node_id for node_id, node in nodes_by_id.items() if node.node_type == NodeType.BUILDING],
    )
    _log_section("Building Breakdown")
    _log_metric("Building breakdown count", len(building_ids))
    for building_id in building_ids:
        semantic_desc = _descendants(building_id, hierarchy_index)
        semantic_scope = {building_id, *semantic_desc}

        part_ids = [n for n in semantic_scope if nodes_by_id.get(n) and nodes_by_id[n].node_type == NodeType.BUILDING_PART]
        room_ids = [n for n in semantic_scope if nodes_by_id.get(n) and nodes_by_id[n].node_type == NodeType.ROOM]
        installation_ids = [
            n for n in semantic_scope if nodes_by_id.get(n) and nodes_by_id[n].node_type == NodeType.BUILDING_INSTALLATION
        ]
        int_installation_ids = [
            n
            for n in semantic_scope
            if nodes_by_id.get(n) and nodes_by_id[n].node_type == NodeType.INT_BUILDING_INSTALLATION
        ]

        boundary_ids: set[str] = set()
        furniture_ids: set[str] = set()
        for source_id in {building_id, *part_ids, *room_ids, *installation_ids, *int_installation_ids}:
            boundary_ids.update(bounded_by_index.get(source_id, []))
        address_ids: set[str] = set()
        for source_id in {building_id, *part_ids}:
            address_ids.update(has_address_index.get(source_id, []))
        for room_id in room_ids:
            room_children = [*contains_index.get(room_id, []), *interior_furniture_index.get(room_id, [])]
            for child_id in room_children:
                child_node = nodes_by_id.get(child_id)
                if child_node and child_node.node_type == NodeType.BUILDING_FURNITURE:
                    furniture_ids.add(child_id)

        opening_ids: set[str] = set()
        for boundary_id in boundary_ids:
            opening_ids.update(has_opening_index.get(boundary_id, []))

        polygon_ids: set[str] = set()
        geometry_owner_ids = semantic_scope | boundary_ids | opening_ids | furniture_ids
        for semantic_id in geometry_owner_ids:
            polygon_ids.update(has_geometry_index.get(semantic_id, []))

        ring_ids: set[str] = set()
        for polygon_id in polygon_ids:
            ring_ids.update(has_ring_index.get(polygon_id, []))

        pos_ids: set[str] = set()
        for ring_id in ring_ids:
            pos_ids.update(has_pos_index.get(ring_id, []))

        lod_geometry_ids: set[str] = set()
        for semantic_id in geometry_owner_ids:
            lod_geometry_ids.update(has_lod_geometry_index.get(semantic_id, []))

        geometry_ids = {
            nid for nid in lod_geometry_ids if nodes_by_id.get(nid) and nodes_by_id[nid].node_type == NodeType.GEOMETRY
        }
        implicit_geometry_ids = {
            nid for nid in lod_geometry_ids if nodes_by_id.get(nid) and nodes_by_id[nid].node_type == NodeType.IMPLICIT_GEOMETRY
        }
        concrete_lod_geometry_ids: set[str] = set()
        for geometry_id in geometry_ids:
            concrete_lod_geometry_ids.update(has_geometry_component_index.get(geometry_id, []))

        solid_ids = {
            nid
            for nid in concrete_lod_geometry_ids
            if nodes_by_id.get(nid) and nodes_by_id[nid].node_type == NodeType.SOLID
        }
        multi_surface_ids = {
            nid
            for nid in concrete_lod_geometry_ids
            if nodes_by_id.get(nid) and nodes_by_id[nid].node_type == NodeType.MULTI_SURFACE
        }
        multi_curve_ids = {
            nid
            for nid in concrete_lod_geometry_ids
            if nodes_by_id.get(nid) and nodes_by_id[nid].node_type == NodeType.MULTI_CURVE
        }

        stats_scope = semantic_scope | boundary_ids | opening_ids | furniture_ids | address_ids
        name_nodes = sum(
            1
            for nid in stats_scope
            if nodes_by_id.get(nid) is not None and "gml_name" in nodes_by_id[nid].properties
        )
        attr_entries = 0
        for nid in stats_scope:
            node = nodes_by_id.get(nid)
            if node is None:
                continue
            attr_entries += sum(1 for key in node.properties if key.startswith("attr_") and not key.endswith("_uom"))

        _log_metric(
            f"Building[{building_id}]",
            (
                "parts=%d rooms=%d installations=%d int_installations=%d boundaries=%d openings=%d "
                "furniture=%d addresses=%d geometry=%d implicit_geometry=%d solid=%d multisurface=%d multicurve=%d "
                "polygons=%d rings=%d positions=%d named_nodes=%d attr_entries=%d"
            )
            % (
                len(part_ids),
                len(room_ids),
                len(installation_ids),
                len(int_installation_ids),
                len(boundary_ids),
                len(opening_ids),
                len(furniture_ids),
                len(address_ids),
                len(geometry_ids),
                len(implicit_geometry_ids),
                len(solid_ids),
                len(multi_surface_ids),
                len(multi_curve_ids),
                len(polygon_ids),
                len(ring_ids),
                len(pos_ids),
                name_nodes,
                attr_entries,
            ),
        )

    _log_section("Stage Checklist")
    _log_metric(
        "Stage 1 Semantic object parsing",
        f"{'DONE' if records_count > 0 else 'NONE'} (records={records_count})",
    )
    _log_metric(
        "Stage 2 Node attribute enrichment",
        f"{'DONE' if (nodes_with_gml_name > 0 or generic_attribute_entries > 0) else 'NONE'} "
        f"(gml_name_nodes={nodes_with_gml_name}, generic_attr_entries={generic_attribute_entries})",
    )
    _log_metric(
        "Stage 3 Semantic relations",
        f"{'DONE' if semantic_relation_count > 0 else 'NONE'} (edges={semantic_relation_count})",
    )
    _log_metric(
        "Stage 4 Geometry subgraph",
        f"{'DONE' if geometry_node_count > 0 else 'NONE'} "
        f"(nodes={geometry_node_count}, edges={geometry_relation_count})",
    )
    _log_metric(
        "Stage 5 Neo4j export",
        (
            "NONE (disabled)"
            if not (neo4j_export and neo4j_export.get("enabled"))
            else (
                f"{'DONE' if neo4j_export.get('success') else 'FAILED'} "
                f"(uri={neo4j_export.get('uri')}, db={neo4j_export.get('database')}, "
                f"nodes={neo4j_export.get('written_nodes', 0)}, edges={neo4j_export.get('written_edges', 0)})"
            )
        ),
    )
    _log_metric(
        "Stage 6 JSON export",
        f"{'DONE' if output_path.exists() else 'NONE'} ({output_path})",
    )
    if neo4j_export is not None and neo4j_export.get("enabled") and not neo4j_export.get("success"):
        _log_metric(
            "Neo4j export error",
            neo4j_export.get("error", "unknown error"),
        )

    _log_section("Stage Timeline")
    stage_items = [(stage, stage_durations.get(stage, 0.0)) for stage in PIPELINE_STAGE_ORDER]
    max_stage_seconds = max((seconds for _, seconds in stage_items), default=0.0)
    for stage, seconds in stage_items:
        _log_metric(stage, f"{seconds:.3f}s [{_duration_bar(seconds, max_stage_seconds)}]")
    _log_metric("total", f"{stage_durations.get('total', 0.0):.3f}s")
    LOGGER.info("")
    _log_separator("=")


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
    total_stages = len(PIPELINE_STAGE_ORDER)
    stage_index_map = {name: index for index, name in enumerate(PIPELINE_STAGE_ORDER, start=1)}

    def _stage_start(stage_name: str, detail: str | None = None) -> None:
        _log_stage_timeline(
            stage_name=stage_name,
            stage_index=stage_index_map[stage_name],
            total_stages=total_stages,
            event="START",
            detail=detail,
        )

    def _stage_done(stage_name: str, elapsed: float, detail: str | None = None) -> None:
        _log_stage_timeline(
            stage_name=stage_name,
            stage_index=stage_index_map[stage_name],
            total_stages=total_stages,
            event="DONE",
            elapsed_seconds=elapsed,
            detail=detail,
        )

    def _stage_skip(stage_name: str, detail: str | None = None) -> None:
        _log_stage_timeline(
            stage_name=stage_name,
            stage_index=stage_index_map[stage_name],
            total_stages=total_stages,
            event="SKIP",
            elapsed_seconds=0.0,
            detail=detail,
        )

    _stage_start("parse_xml")
    t0 = perf_counter()
    root = read_citygml(source)
    t_parse_xml = perf_counter() - t0
    _stage_done("parse_xml", t_parse_xml)

    _stage_start("collect_semantics")
    t0 = perf_counter()
    records, by_element = _collect_records(root)
    t_collect_semantics = perf_counter() - t0
    _stage_done("collect_semantics", t_collect_semantics, detail=f"records={len(records)}")
    graph = SceneGraph()

    _stage_start("build_nodes")
    t0 = perf_counter()
    for record in records:
        graph.add_node(create_node(record.node_id, record.node_type, **record.properties))
    boundary_surface_type_nodes = _build_boundary_surface_type_nodes(graph, records)
    t_build_nodes = perf_counter() - t0
    _stage_done(
        "build_nodes",
        t_build_nodes,
        detail=f"nodes={len(graph.nodes)}, boundary_surface_types={boundary_surface_type_nodes}",
    )

    t_build_semantic_edges = 0.0
    t_build_geometry = 0.0
    if records:
        _stage_start("build_semantic_edges")
        t0 = perf_counter()
        edge_before = len(graph.edges)
        _build_semantic_edges(graph, root, records, by_element)
        t_build_semantic_edges = perf_counter() - t0
        _stage_done(
            "build_semantic_edges",
            t_build_semantic_edges,
            detail=f"edges+={len(graph.edges) - edge_before}",
        )

        _stage_start("build_geometry")
        t0 = perf_counter()
        node_before = len(graph.nodes)
        edge_before = len(graph.edges)
        polygon_memberships = _attach_lod_geometry_structure(graph, root, by_element)
        _attach_geometry_subgraph(graph, root, by_element, polygon_memberships=polygon_memberships)
        _attach_appearance_subgraph(graph, root, by_element)
        spatial_added = _build_spatial_edges(
            graph,
            touch_epsilon=touch_epsilon,
            adjacent_epsilon=adjacent_epsilon,
            intersection_epsilon=intersection_epsilon,
        )
        t_build_geometry = perf_counter() - t0
        _stage_done(
            "build_geometry",
            t_build_geometry,
            detail=(
                f"nodes+={len(graph.nodes) - node_before}, "
                f"edges+={len(graph.edges) - edge_before}, spatial_edges+={spatial_added}"
            ),
        )
    else:
        _stage_skip("build_semantic_edges", detail="no semantic records")
        _stage_skip("build_geometry", detail="no semantic records")

    scorecard = _build_scorecard(graph, root)
    neo4j_export: dict | None = {"enabled": False, "success": False}
    t_export_neo4j = 0.0
    if to_neo4j:
        _stage_start("export_neo4j", detail=config_path)
        t0 = perf_counter()
        try:
            neo4j_export = _write_graph_to_neo4j(graph, config_path)
            t_export_neo4j = perf_counter() - t0
            _stage_done(
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
            _stage_done("export_neo4j", t_export_neo4j, detail="FAILED")
            LOGGER.exception("Neo4j export failed: %s", exc)
    else:
        _stage_skip("export_neo4j", detail="disabled")

    target = Path(output_path)
    _stage_start("export_json")
    ensure_dir(target.parent)
    t0 = perf_counter()
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
    payload = _graph_to_payload(
        graph,
        source,
        scorecard=scorecard,
        neo4j_export=neo4j_export,
        stage_durations=stage_durations,
    )
    write_json(target, payload)
    t_export_json = perf_counter() - t0
    t_total = perf_counter() - t0_total
    stage_durations["export_json"] = t_export_json
    stage_durations["total"] = t_total
    payload["summary"]["stage_durations"] = {key: round(float(value), 6) for key, value in stage_durations.items()}
    write_json(target, payload)
    _stage_done("export_json", t_export_json, detail=str(target))

    _emit_conversion_report(
        graph,
        records_count=len(records),
        output_path=target,
        stage_durations=stage_durations,
        scorecard=scorecard,
        neo4j_export=neo4j_export,
    )
    LOGGER.info("Import complete: nodes=%d edges=%d", payload["summary"]["node_count"], payload["summary"]["edge_count"])
    if to_neo4j and neo4j_export and not neo4j_export.get("success"):
        return 3
    return 0


def run_relation_pipeline() -> int:
    LOGGER.info("Relation extraction pipeline started")
    LOGGER.info("Planned pipeline stub: candidate search + rule-based relation extraction is not wired yet.")
    return 0


def run_export_pipeline() -> int:
    LOGGER.info("Graph export pipeline started")
    LOGGER.info("Planned pipeline stub: additional export adapters are not wired yet.")
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
        if record is not None and "count" in record:
            result_count = int(record["count"])
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
