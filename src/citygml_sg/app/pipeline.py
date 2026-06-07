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
from citygml_sg.storage.json.writer import write_graph_json_stream, write_json
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
CONNECTS_OPENING_TYPES = {"Door"}
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
    RelationType.ABOVE,
    RelationType.BELOW,
    RelationType.ADJACENT_SURFACE,
    RelationType.ATTACHED_TO,
    RelationType.HOSTED_BY,
}
SPATIAL_INFERRED_RELATIONS: set[RelationType] = {
    RelationType.ADJACENT_TO,
    RelationType.TOUCHES,
    RelationType.INTERSECTS,
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
SPATIAL_FAMILY_WEIGHTS: dict[str, float] = {
    "furniture_boundary_surface": 0.30,
    "furniture_opening": 0.25,
    "furniture_furniture": 0.25,
    "opening_room_connects": 0.20,
}
DEFAULT_SPATIAL_TOUCH_EPSILON = 0.05
DEFAULT_SPATIAL_ADJACENT_EPSILON = 0.50
DEFAULT_SPATIAL_INTERSECTION_EPSILON = 1e-6
DEFAULT_ATTACHMENT_VERTICAL_GAP_EPSILON = 0.10
DEFAULT_BOUNDARY_LAYER_GAP_EPSILON = 0.25
DEFAULT_BOUNDARY_LAYER_OVERLAP_RATIO = 0.85
VERTICAL_RELATION_OBJECT_TYPES: set[NodeType] = {NodeType.BUILDING_FURNITURE, NodeType.OPENING}
FLOOR_LIKE_SURFACE_TYPES: set[str] = {"FloorSurface", "OuterFloorSurface", "GroundSurface"}
WALL_LIKE_SURFACE_TYPES: set[str] = {"WallSurface", "InteriorWallSurface"}
FLOOR_FINISH_KEYWORDS: tuple[str, ...] = ("마감", "마루", "타일", "tile", "finish", "finishing")
FLOOR_SUBSTRATE_KEYWORDS: tuple[str, ...] = ("단열", "insulation", "foam", "substrate")
DEFAULT_TOUCH_MIN_CONTACT_AREA = 0.01
DEFAULT_TOUCH_MIN_CONTACT_LENGTH = 0.10
DEFAULT_ADJACENT_SURFACE_MIN_SHARED_EDGE_LENGTH = 0.10
DEFAULT_ADJACENT_SURFACE_EDGE_LINE_TOLERANCE = 0.01
EXTERNAL_FLAG_KEYS: tuple[str, ...] = (
    "is_external",
    "attr_pset_wallcommon_isexternal",
    "attr_pset_buildingelementproxycommon_isexternal",
)

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
            _add_edge_if_valid(graph, create_edge(source_id, target_id, relation, **props))
            if len(graph.edges) > before:
                added += 1
    return added


def _bbox_axis_span(bbox: BBox, axis: int) -> float:
    if axis == 0:
        return float(bbox.max_point.x - bbox.min_point.x)
    if axis == 1:
        return float(bbox.max_point.y - bbox.min_point.y)
    return float(bbox.max_point.z - bbox.min_point.z)


def _bbox_axis_center(bbox: BBox, axis: int) -> float:
    if axis == 0:
        return float((bbox.min_point.x + bbox.max_point.x) / 2.0)
    if axis == 1:
        return float((bbox.min_point.y + bbox.max_point.y) / 2.0)
    return float((bbox.min_point.z + bbox.max_point.z) / 2.0)


def _bbox_axis_overlap(bbox_a: BBox, bbox_b: BBox, axis: int) -> float:
    if axis == 0:
        return float(min(bbox_a.max_point.x, bbox_b.max_point.x) - max(bbox_a.min_point.x, bbox_b.min_point.x))
    if axis == 1:
        return float(min(bbox_a.max_point.y, bbox_b.max_point.y) - max(bbox_a.min_point.y, bbox_b.min_point.y))
    return float(min(bbox_a.max_point.z, bbox_b.max_point.z) - max(bbox_a.min_point.z, bbox_b.min_point.z))


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
    parallel_error = (cross_uv_x * cross_uv_x + cross_uv_y * cross_uv_y + cross_uv_z * cross_uv_z) ** 0.5
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

    if point_line_distance(second_start) > line_tolerance or point_line_distance(second_end) > line_tolerance:
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


def _boundary_plane_axis(bbox: BBox) -> int:
    spans = [_bbox_axis_span(bbox, 0), _bbox_axis_span(bbox, 1), _bbox_axis_span(bbox, 2)]
    min_axis = 0
    min_value = spans[0]
    for axis, span in enumerate(spans[1:], start=1):
        if span < min_value:
            min_axis = axis
            min_value = span
    return min_axis


def _boundary_projected_area(bbox: BBox, normal_axis: int) -> float:
    tangent_axes = [axis for axis in (0, 1, 2) if axis != normal_axis]
    return max(_bbox_axis_span(bbox, tangent_axes[0]), 0.0) * max(_bbox_axis_span(bbox, tangent_axes[1]), 0.0)


def _node_keyword_text(node: Node) -> str:
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


def _floor_finish_priority(node: Node) -> float:
    text = _node_keyword_text(node)
    priority = 0.0
    if str(node.properties.get("attr_is_walkable") or "").lower() == "true":
        priority += 1.0
    if any(keyword in text for keyword in FLOOR_FINISH_KEYWORDS):
        priority += 2.0
    if any(keyword in text for keyword in FLOOR_SUBSTRATE_KEYWORDS):
        priority -= 3.0
    return priority


def _boundary_representation_score(
    node: Node,
    bbox: BBox,
    *,
    surface_type: str,
    normal_axis: int,
) -> tuple[float, float, float]:
    projected_area = _boundary_projected_area(bbox, normal_axis)
    if surface_type in FLOOR_LIKE_SURFACE_TYPES:
        # Furniture should attach to the usable top finish, not lower insulation/slab layers.
        return (round(float(bbox.max_point.z), 6), _floor_finish_priority(node), projected_area)
    return (projected_area, 0.0, 0.0)


def _boundaries_are_layered_duplicates(
    first_bbox: BBox,
    second_bbox: BBox,
    *,
    normal_axis: int,
    gap_epsilon: float,
    overlap_ratio_threshold: float,
) -> bool:
    normal_gap = abs(_bbox_axis_center(first_bbox, normal_axis) - _bbox_axis_center(second_bbox, normal_axis))
    if normal_gap > gap_epsilon:
        return False

    tangent_axes = [axis for axis in (0, 1, 2) if axis != normal_axis]
    for axis in tangent_axes:
        overlap = _bbox_axis_overlap(first_bbox, second_bbox, axis)
        if overlap <= 0.0:
            return False
        min_span = min(_bbox_axis_span(first_bbox, axis), _bbox_axis_span(second_bbox, axis))
        if min_span <= 0.0:
            return False
        overlap_ratio = overlap / min_span
        if overlap_ratio < overlap_ratio_threshold:
            return False
    return True


def _collapse_layered_boundary_ids(
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
        normal_axis = _boundary_plane_axis(bbox)
        merged = False
        for group in groups:
            if group["surface_type"] != surface_type:
                continue
            if group["normal_axis"] != normal_axis:
                continue
            rep_bbox: BBox = group["rep_bbox"]  # type: ignore[assignment]
            if not _boundaries_are_layered_duplicates(
                rep_bbox,
                bbox,
                normal_axis=normal_axis,
                gap_epsilon=DEFAULT_BOUNDARY_LAYER_GAP_EPSILON,
                overlap_ratio_threshold=DEFAULT_BOUNDARY_LAYER_OVERLAP_RATIO,
            ):
                continue
            candidate_score = _boundary_representation_score(
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
                "rep_score": _boundary_representation_score(
                    node,
                    bbox,
                    surface_type=surface_type,
                    normal_axis=normal_axis,
                ),
            }
        )

    return sorted(str(group["rep_id"]) for group in groups)


def _build_room_spatial_scope(
    graph: SceneGraph,
    *,
    include_container_fallback: bool,
    collapse_layered_fallback: bool = False,
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]], dict[str, int]]:
    """Build room-scoped furniture/boundary/opening maps.

    When include_container_fallback is True, rooms without direct BOUNDED_BY links
    inherit boundary surfaces from their parent BuildingPart/Building containers.
    """
    nodes_by_id = graph.nodes
    inside_index = _edge_index(graph, RelationType.INSIDE)  # furniture -> room
    bounded_by_index = _edge_index(graph, RelationType.BOUNDED_BY)  # room|building|buildingpart -> boundary surface
    has_opening_index = _edge_index(graph, RelationType.HAS_OPENING)  # boundary surface -> opening

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
        boundary_bboxes = _build_node_bboxes(graph, target_types={NodeType.BOUNDARY_SURFACE})
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

        all_room_ids = [node_id for node_id, node in nodes_by_id.items() if node.node_type == NodeType.ROOM]
        for room_id in sorted(all_room_ids):
            if room_to_boundary.get(room_id):
                continue
            fallback_boundary_ids: set[str] = set()
            for container_id in sorted(room_to_containers.get(room_id, set())):
                for boundary_id in bounded_by_index.get(container_id, []):
                    boundary_node = nodes_by_id.get(boundary_id)
                    if boundary_node is None or boundary_node.node_type != NodeType.BOUNDARY_SURFACE:
                        continue
                    fallback_boundary_ids.add(boundary_id)
            if not fallback_boundary_ids:
                continue
            raw_count = len(fallback_boundary_ids)
            selected_boundary_ids = sorted(fallback_boundary_ids)
            if collapse_layered_fallback and raw_count > 1:
                selected_boundary_ids = _collapse_layered_boundary_ids(
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
                if not _is_door_or_window_opening(opening_node):
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


def _bbox_xy_overlaps(first: BBox, second: BBox, *, intersection_epsilon: float) -> bool:
    overlap_x = min(first.max_point.x, second.max_point.x) - max(first.min_point.x, second.min_point.x)
    overlap_y = min(first.max_point.y, second.max_point.y) - max(first.min_point.y, second.min_point.y)
    return overlap_x >= -intersection_epsilon and overlap_y >= -intersection_epsilon


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
    if not _bbox_xy_overlaps(first, second, intersection_epsilon=intersection_epsilon):
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


def _build_spatial_edges(
    graph: SceneGraph,
    *,
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
) -> int:
    edge_count_before = len(graph.edges)
    nodes_by_id = graph.nodes
    room_to_furniture, room_to_boundary, room_to_opening, scope_stats = _build_room_spatial_scope(
        graph,
        include_container_fallback=True,
        collapse_layered_fallback=True,
    )
    if scope_stats["fallback_room_count"] > 0:
        LOGGER.info(
            "[SpatialScope] room boundary fallback used: rooms=%d raw_links=%d collapsed_links=%d reduced=%d",
            scope_stats["fallback_room_count"],
            scope_stats["fallback_boundary_link_count"],
            scope_stats["fallback_boundary_collapsed_link_count"],
            scope_stats["fallback_boundary_reduced_link_count"],
        )

    target_types = {NodeType.BUILDING_FURNITURE, NodeType.BOUNDARY_SURFACE, NodeType.OPENING}
    node_bboxes = _build_node_bboxes(graph, target_types=target_types)
    node_points = _build_node_points(graph, target_types=target_types)
    boundary_polygon_rings = _build_node_polygon_rings(graph, target_types={NodeType.BOUNDARY_SURFACE})

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
            nodes_by_id=nodes_by_id,
            node_bboxes=node_bboxes,
            node_points=node_points,
            touch_epsilon=touch_epsilon,
            adjacent_epsilon=adjacent_epsilon,
            intersection_epsilon=intersection_epsilon,
            use_two_stage_refinement=True,
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
                first_surface_type = str((first_node.properties.get("surface_type") if first_node else "") or "")
                second_surface_type = str((second_node.properties.get("surface_type") if second_node else "") or "")
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
                    if _boundary_plane_axis(first_bbox) == _boundary_plane_axis(second_bbox):
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
                base_props["min_shared_edge_length"] = DEFAULT_ADJACENT_SURFACE_MIN_SHARED_EDGE_LENGTH
                base_props["shared_edge_line_tolerance"] = DEFAULT_ADJACENT_SURFACE_EDGE_LINE_TOLERANCE
                base_props["adjacent_surface_method"] = "polygon_shared_edge_v1"
                _add_edge_if_valid(graph, create_edge(first_id, second_id, RelationType.ADJACENT_SURFACE, **base_props))
                _add_edge_if_valid(graph, create_edge(second_id, first_id, RelationType.ADJACENT_SURFACE, **base_props))

    processed_vertical_pairs: set[tuple[str, str]] = set()
    for room_id in sorted(set(room_to_furniture.keys()) | set(room_to_opening.keys())):
        candidate_ids = sorted(set(room_to_furniture.get(room_id, []) + room_to_opening.get(room_id, [])))
        scoped_ids: list[str] = []
        for node_id in candidate_ids:
            node = nodes_by_id.get(node_id)
            if node is None or node.node_type not in VERTICAL_RELATION_OBJECT_TYPES:
                continue
            if node.node_type == NodeType.OPENING and not _is_door_or_window_opening(node):
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

                inverse_relation = RelationType.BELOW if relation == RelationType.ABOVE else RelationType.ABOVE
                _add_edge_if_valid(graph, create_edge(first_id, second_id, relation, **props))
                _add_edge_if_valid(graph, create_edge(second_id, first_id, inverse_relation, **props))

    normalized_edges, removed = normalize_spatial_precedence(graph.edges)
    if removed > 0:
        graph.replace_edges(normalized_edges)
        LOGGER.info(
            "[Spatial] precedence normalization applied: removed_weaker_edges=%d rule=INTERSECTS>TOUCHES>ADJACENT_TO",
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
        if source_node.node_type == NodeType.BUILDING_FURNITURE and target_node.node_type == NodeType.BOUNDARY_SURFACE:
            furniture_id = edge.source_id
            boundary_id = edge.target_id
        elif source_node.node_type == NodeType.BOUNDARY_SURFACE and target_node.node_type == NodeType.BUILDING_FURNITURE:
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
                if not _bbox_xy_overlaps(furniture_bbox, boundary_bbox, intersection_epsilon=intersection_epsilon):
                    continue
                vertical_gap = abs(float(furniture_bbox.min_point.z) - float(boundary_bbox.max_point.z))
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
                    "evidence_score": round(max(0.75, 0.92 - min(0.15, vertical_gap / max(attachment_gap_epsilon, 1e-9) * 0.15)), 4),
                }

    for furniture_id, boundary_id in sorted(attached_candidates):
        boundary_node = nodes_by_id.get(boundary_id)
        boundary_surface_type = "BoundarySurface"
        if boundary_node is not None:
            boundary_surface_type = str(boundary_node.properties.get("surface_type") or "BoundarySurface")
        attachment_props = attached_candidates[(furniture_id, boundary_id)]
        _add_edge_if_valid(
            graph,
            create_edge(
                furniture_id,
                boundary_id,
                RelationType.ATTACHED_TO,
                method=str(attachment_props.get("method") or "touch_attachment_v1"),
                source=str(attachment_props.get("source") or "touches_relation"),
                boundary_surface_type=boundary_surface_type,
                confidence=float(attachment_props.get("confidence") or 0.9),
                evidence_score=float(attachment_props.get("evidence_score") or attachment_props.get("confidence") or 0.9),
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


def _augment_connects_edges(
    graph: SceneGraph,
    *,
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
) -> int:
    nodes_by_id = graph.nodes
    connects_index = _edge_index(graph, RelationType.CONNECTS)
    reverse_hierarchy = _reverse_edge_index(graph, SEMANTIC_HIERARCHY_RELATIONS)
    forward_hierarchy = _edge_index(graph, RelationType.CONTAINS)

    for relation in (
        RelationType.CONSISTS_OF_BUILDING_PART,
        RelationType.INTERIOR_ROOM,
        RelationType.HAS_CITY_OBJECT,
        RelationType.HAS_GROUP_MEMBER,
        RelationType.OUTER_BUILDING_INSTALLATION,
        RelationType.INTERIOR_BUILDING_INSTALLATION,
        RelationType.ROOM_INSTALLATION,
    ):
        for source_id, target_ids in _edge_index(graph, relation).items():
            forward_hierarchy[source_id].extend(target_ids)

    opening_and_room_bboxes = _build_node_bboxes(
        graph,
        target_types={NodeType.OPENING, NodeType.ROOM},
    )
    added = 0

    opening_ids = [
        node_id
        for node_id, node in nodes_by_id.items()
        if node.node_type == NodeType.OPENING and _is_connects_opening(node)
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
            if nodes_by_id.get(node_id) is not None and nodes_by_id[node_id].node_type == NodeType.ROOM
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
            _add_edge_if_valid(
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


def _is_connects_opening(node: Node) -> bool:
    opening_type = str(
        node.properties.get("opening_type")
        or node.properties.get("source_tag")
        or ""
    )
    return opening_type in CONNECTS_OPENING_TYPES


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


def _build_spatial_score_metrics(
    graph: SceneGraph,
    *,
    expected_connects_total: int = 0,
    touch_epsilon: float = DEFAULT_SPATIAL_TOUCH_EPSILON,
    adjacent_epsilon: float = DEFAULT_SPATIAL_ADJACENT_EPSILON,
    intersection_epsilon: float = DEFAULT_SPATIAL_INTERSECTION_EPSILON,
) -> dict[str, object]:
    nodes_by_id = graph.nodes
    connects_index = _edge_index(graph, RelationType.CONNECTS)  # opening -> room
    room_to_furniture, room_to_boundary, room_to_opening, scope_stats = _build_room_spatial_scope(
        graph,
        include_container_fallback=True,
        collapse_layered_fallback=True,
    )
    room_to_boundary_for_connects = room_to_boundary
    if scope_stats["fallback_room_count"] > 0:
        LOGGER.info(
            "[ScoreScope] room boundary fallback used: rooms=%d raw_links=%d collapsed_links=%d reduced=%d",
            scope_stats["fallback_room_count"],
            scope_stats["fallback_boundary_link_count"],
            scope_stats["fallback_boundary_collapsed_link_count"],
            scope_stats["fallback_boundary_reduced_link_count"],
        )
    has_opening_index = _edge_index(graph, RelationType.HAS_OPENING)  # boundary surface -> opening

    target_types = {NodeType.BUILDING_FURNITURE, NodeType.BOUNDARY_SURFACE, NodeType.OPENING}
    node_bboxes = _build_node_bboxes(graph, target_types=target_types)
    node_points = _build_node_points(graph, target_types=target_types)

    candidate_pair_keys: dict[str, set[tuple[str, str]]] = {
        "furniture_boundary_surface": set(),
        "furniture_opening": set(),
        "furniture_furniture": set(),
        "opening_room_connects": set(),
    }
    candidate_pair_counts: dict[str, int] = {
        "furniture_boundary_surface": 0,
        "furniture_opening": 0,
        "furniture_furniture": 0,
        "opening_room_connects": 0,
    }
    candidate_pair_counts_directed: dict[str, int] = {
        "furniture_boundary_surface": 0,
        "furniture_opening": 0,
        "furniture_furniture": 0,
        "opening_room_connects": 0,
    }
    for room_id, furniture_ids in room_to_furniture.items():
        furniture_bbox_ids = sorted({node_id for node_id in furniture_ids if node_id in node_bboxes})
        boundary_bbox_ids = sorted({node_id for node_id in room_to_boundary.get(room_id, []) if node_id in node_bboxes})
        opening_bbox_ids = sorted({node_id for node_id in room_to_opening.get(room_id, []) if node_id in node_bboxes})

        for furniture_id in furniture_bbox_ids:
            for boundary_id in boundary_bbox_ids:
                candidate_pair_keys["furniture_boundary_surface"].add(tuple(sorted((furniture_id, boundary_id))))

        for furniture_id in furniture_bbox_ids:
            for opening_id in opening_bbox_ids:
                candidate_pair_keys["furniture_opening"].add(tuple(sorted((furniture_id, opening_id))))

        for index, source_id in enumerate(furniture_bbox_ids):
            for target_id in furniture_bbox_ids[index + 1 :]:
                candidate_pair_keys["furniture_furniture"].add(tuple(sorted((source_id, target_id))))

    for family in ("furniture_boundary_surface", "furniture_opening", "furniture_furniture"):
        candidate_pair_counts[family] = len(candidate_pair_keys[family])
        candidate_pair_counts_directed[family] = len(candidate_pair_keys[family]) * 2

    family_relation_counts: dict[str, Counter[str]] = {
        "furniture_boundary_surface": Counter(),
        "furniture_opening": Counter(),
        "furniture_furniture": Counter(),
        "opening_room_connects": Counter(),
    }
    inferred_total = 0
    metadata_valid_total = 0
    schema_valid_total = 0
    pair_relations: dict[tuple[str, str], set[RelationType]] = defaultdict(set)
    family_inferred_pair_keys: dict[str, set[tuple[str, str]]] = {
        "furniture_boundary_surface": set(),
        "furniture_opening": set(),
        "furniture_furniture": set(),
        "opening_room_connects": set(),
    }

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
        undirected_pair_key = tuple(sorted((edge.source_id, edge.target_id)))
        family_inferred_pair_keys[family].add(undirected_pair_key)

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

    # Connectivity family (CONNECTS): derive candidates from room-boundary-opening structural chain.
    opening_room_candidate_pairs: set[tuple[str, str]] = set()
    for room_id, boundary_ids in room_to_boundary_for_connects.items():
        for boundary_id in boundary_ids:
            for opening_id in has_opening_index.get(boundary_id, []):
                opening_node = nodes_by_id.get(opening_id)
                if opening_node is None or opening_node.node_type != NodeType.OPENING:
                    continue
                if not _is_connects_opening(opening_node):
                    continue
                opening_room_candidate_pairs.add((opening_id, room_id))

    candidate_pair_keys["opening_room_connects"] = set(opening_room_candidate_pairs)
    connects_candidate_from_structure = len(candidate_pair_keys["opening_room_connects"])
    for edge in graph.edges:
        if edge.relation != RelationType.CONNECTS:
            continue
        source_node = nodes_by_id.get(edge.source_id)
        target_node = nodes_by_id.get(edge.target_id)
        if source_node is None or target_node is None:
            continue
        if source_node.node_type != NodeType.OPENING or target_node.node_type != NodeType.ROOM:
            continue
        if not _is_connects_opening(source_node):
            continue
        family_relation_counts["opening_room_connects"][edge.relation.value] += 1
        family_inferred_pair_keys["opening_room_connects"].add((edge.source_id, edge.target_id))

    connects_inferred_pair_total = len(family_inferred_pair_keys["opening_room_connects"])
    connects_candidate_floor = max(int(expected_connects_total), connects_candidate_from_structure)
    # Ensure candidate count never becomes zero while inferred CONNECTS exists.
    # This avoids expected=0 / actual>0 inconsistency in sparse or non-nested source structures.
    connects_candidate_total = max(connects_candidate_floor, connects_inferred_pair_total)
    if connects_candidate_total > len(candidate_pair_keys["opening_room_connects"]):
        for opening_id, room_ids in connects_index.items():
            opening_node = nodes_by_id.get(opening_id)
            if opening_node is None or opening_node.node_type != NodeType.OPENING:
                continue
            if not _is_connects_opening(opening_node):
                continue
            for room_id in room_ids:
                room_node = nodes_by_id.get(room_id)
                if room_node is None or room_node.node_type != NodeType.ROOM:
                    continue
                candidate_pair_keys["opening_room_connects"].add((opening_id, room_id))
    candidate_pair_counts["opening_room_connects"] = max(
        connects_candidate_total, len(candidate_pair_keys["opening_room_connects"])
    )
    candidate_pair_counts_directed["opening_room_connects"] = candidate_pair_counts["opening_room_connects"]

    plausible_pair_counts: dict[str, int] = {
        "furniture_boundary_surface": 0,
        "furniture_opening": 0,
        "furniture_furniture": 0,
        "opening_room_connects": 0,
    }
    for family, pairs in candidate_pair_keys.items():
        if family == "opening_room_connects":
            plausible_pair_counts[family] = candidate_pair_counts[family]
            continue
        plausible = 0
        for source_id, target_id in pairs:
            source_bbox = node_bboxes.get(source_id)
            target_bbox = node_bboxes.get(target_id)
            if source_bbox is None or target_bbox is None:
                continue
            relation, _ = infer_spatial_relation(
                source_bbox,
                target_bbox,
                touch_epsilon=touch_epsilon,
                adjacent_epsilon=adjacent_epsilon,
                intersection_epsilon=intersection_epsilon,
                first_points=node_points.get(source_id),
                second_points=node_points.get(target_id),
                use_two_stage_refinement=True,
                touch_min_contact_area=DEFAULT_TOUCH_MIN_CONTACT_AREA,
                touch_min_contact_length=DEFAULT_TOUCH_MIN_CONTACT_LENGTH,
            )
            if relation is not None:
                plausible += 1
        plausible_pair_counts[family] = plausible

    pair_count = len(pair_relations)
    precedence_valid_pairs = sum(1 for relations in pair_relations.values() if len(relations) <= 1)
    pair_conflict_count = sum(max(0, len(relations) - 1) for relations in pair_relations.values())

    metadata_ratio = _safe_ratio(metadata_valid_total, inferred_total)
    schema_ratio = _safe_ratio(schema_valid_total, inferred_total)
    precedence_ratio = _safe_ratio(precedence_valid_pairs, pair_count)
    precision_like_ratio = (metadata_ratio + schema_ratio + precedence_ratio) / 3.0

    active_families = [family for family, total in candidate_pair_counts.items() if total > 0]
    inferred_pair_total = int(sum(len(family_inferred_pair_keys[family]) for family in active_families))
    expected_pair_total = int(sum(candidate_pair_counts[family] for family in active_families))
    plausible_expected_total = int(sum(plausible_pair_counts[family] for family in active_families))
    expected_directed_total = int(sum(candidate_pair_counts_directed[family] for family in active_families))
    inferred_directed_total_coverage = int(
        sum(sum(family_relation_counts[family].values()) for family in active_families)
    )

    pair_stats: dict[str, dict[str, object]] = {}
    pair_family_scores: dict[str, dict[str, object]] = {}
    family_coverage_ratios: dict[str, float] = {}
    weighted_score_sum = 0.0
    weighted_score_weight_sum = 0.0

    for family, candidate_total in candidate_pair_counts.items():
        relation_counts = family_relation_counts[family]
        family_inferred_total = int(sum(relation_counts.values()))
        family_inferred_pair_total = int(len(family_inferred_pair_keys[family]))
        family_coverage_ratio: float | None = None
        if candidate_total > 0:
            family_coverage_ratio = _safe_ratio(family_inferred_pair_total, int(candidate_total))
            family_coverage_ratios[family] = family_coverage_ratio
        family_weight = float(SPATIAL_FAMILY_WEIGHTS.get(family, 1.0))

        if candidate_total > 0 and family_coverage_ratio is not None:
            weighted_score_sum += family_coverage_ratio * family_weight
            weighted_score_weight_sum += family_weight

        pair_stats[family] = {
            "candidate_pairs": int(candidate_total),
            "plausible_candidate_pairs": int(plausible_pair_counts[family]),
            "candidate_pairs_directed": int(candidate_pair_counts_directed[family]),
            "inferred_total": family_inferred_total,
            "inferred_pair_total": family_inferred_pair_total,
            "coverage_score": round(family_coverage_ratio * 100.0, 2) if family_coverage_ratio is not None else None,
            "relation_counts": dict(relation_counts),
        }
        pair_family_scores[family] = {
            "score": round(family_coverage_ratio * 100.0, 2) if family_coverage_ratio is not None else None,
            "actual_total": family_inferred_pair_total,
            "expected_total": int(candidate_total),
            "weight": family_weight,
            "weighted_score_contribution": (
                round(family_coverage_ratio * family_weight * 100.0, 2) if family_coverage_ratio is not None else None
            ),
            "definition": (
                "family-level candidate-hit-rate over undirected candidate pairs"
                if family_coverage_ratio is not None
                else "N/A (no candidates in this run)"
            ),
        }

    family_unweighted_ratio = (
        sum(family_coverage_ratios[family] for family in active_families) / len(active_families)
        if active_families
        else 1.0
    )
    family_weighted_ratio = (weighted_score_sum / weighted_score_weight_sum) if weighted_score_weight_sum > 0 else 1.0
    raw_coverage_ratio = _safe_ratio(inferred_pair_total, expected_pair_total)
    plausible_coverage_ratio = _safe_ratio(inferred_pair_total, plausible_expected_total)
    density_ratio = family_weighted_ratio

    return {
        "spatial_coverage": {
            "score": round(raw_coverage_ratio * 100.0, 2),
            "actual_total": int(inferred_pair_total),
            "expected_total": int(expected_pair_total),
            "actual_directed_total": int(inferred_directed_total_coverage),
            "expected_directed_total": int(expected_directed_total),
            "definition": "raw candidate-hit-rate over active undirected candidate pairs in v1 scope",
        },
        "spatial_plausible_coverage": {
            "score": round(plausible_coverage_ratio * 100.0, 2),
            "actual_total": int(inferred_pair_total),
            "plausible_expected_total": int(plausible_expected_total),
            "expected_total": int(expected_pair_total),
            "definition": "epsilon-aware plausible candidate hit-rate over active undirected candidate pairs in v1 scope",
        },
        "spatial_density": {
            "score": round(density_ratio * 100.0, 2),
            "actual_total": int(inferred_pair_total),
            "expected_total": int(expected_pair_total),
            "family_unweighted_score": round(family_unweighted_ratio * 100.0, 2),
            "family_weighted_score": round(family_weighted_ratio * 100.0, 2),
            "active_family_count": int(len(active_families)),
            "actual_directed_total": int(inferred_directed_total_coverage),
            "expected_directed_total": int(expected_directed_total),
            "definition": "density-only spatial coverage metric (pair hit-rate), separated from quality sanity",
        },
        "spatial_precision_sanity": {
            "score": round(precision_like_ratio * 100.0, 2),
            "inferred_total": int(inferred_total),
            "metadata_valid_total": int(metadata_valid_total),
            "schema_valid_total": int(schema_valid_total),
            "directed_pair_count": int(pair_count),
            "precedence_valid_pairs": int(precedence_valid_pairs),
            "pair_conflict_count": int(pair_conflict_count),
            "metadata_score": round(metadata_ratio * 100.0, 2),
            "schema_score": round(schema_ratio * 100.0, 2),
            "precedence_score": round(precedence_ratio * 100.0, 2),
            "definition": "quality-only sanity metric over inferred spatial relations",
        },
        "spatial_quality": {
            "score": round(precision_like_ratio * 100.0, 2),
            "metadata_score": round(metadata_ratio * 100.0, 2),
            "schema_score": round(schema_ratio * 100.0, 2),
            "precedence_score": round(precedence_ratio * 100.0, 2),
            "inferred_total": int(inferred_total),
            "pair_conflict_count": int(pair_conflict_count),
            "definition": "quality-only sanity metric over inferred spatial relations",
        },
        "spatial_pair_stats": pair_stats,
        "spatial_pair_family_scores": pair_family_scores,
        "spatial_family_normalized_coverage": {
            "score": round(family_weighted_ratio * 100.0, 2),
            "family_unweighted_score": round(family_unweighted_ratio * 100.0, 2),
            "family_weighted_score": round(family_weighted_ratio * 100.0, 2),
            "weights": {family: float(weight) for family, weight in SPATIAL_FAMILY_WEIGHTS.items()},
            "active_family_count": int(len(active_families)),
            "definition": "family-level normalized coverage score with explicit weights",
        },
        "spatial_coverage_policy": {
            "include_connects_family": True,
            "connects_family_name": "opening_room_connects",
            "zero_candidate_score_policy": "N/A(null)",
            "connects_candidate_strategy": "max(source_expected, structural_chain, inferred_pairs_floor)",
            "plausible_expected_policy": "epsilon-aware plausible candidates reported as supplementary denominator",
        },
    }


def _build_scorecard(
    graph: SceneGraph,
    root: Element,
    *,
    touch_epsilon: float = DEFAULT_SPATIAL_TOUCH_EPSILON,
    adjacent_epsilon: float = DEFAULT_SPATIAL_ADJACENT_EPSILON,
    intersection_epsilon: float = DEFAULT_SPATIAL_INTERSECTION_EPSILON,
) -> dict:
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
        if local_name(opening.tag) in CONNECTS_OPENING_TYPES
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
    spatial_metrics = _build_spatial_score_metrics(
        graph,
        expected_connects_total=expected_connects,
        touch_epsilon=touch_epsilon,
        adjacent_epsilon=adjacent_epsilon,
        intersection_epsilon=intersection_epsilon,
    )

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
            "score=%.2f(%d/%d) directed=%d/%d"
            % (
                spatial_coverage.get("score", 0.0),
                spatial_coverage.get("actual_total", 0),
                spatial_coverage.get("expected_total", 0),
                spatial_coverage.get("actual_directed_total", 0),
                spatial_coverage.get("expected_directed_total", 0),
            ),
        )
    if "spatial_plausible_coverage" in scorecard:
        plausible_coverage = scorecard["spatial_plausible_coverage"]
        _log_metric(
            "Spatial plausible coverage",
            "score=%.2f actual=%d plausible_expected=%d (raw_expected=%d)"
            % (
                plausible_coverage.get("score", 0.0),
                plausible_coverage.get("actual_total", 0),
                plausible_coverage.get("plausible_expected_total", 0),
                plausible_coverage.get("expected_total", 0),
            ),
        )
    if "spatial_density" in scorecard:
        spatial_density = scorecard["spatial_density"]
        _log_metric(
            "Spatial density",
            "score=%.2f family_weighted=%.2f family_unweighted=%.2f active_families=%d"
            % (
                spatial_density.get("score", 0.0),
                spatial_density.get("family_weighted_score", 0.0),
                spatial_density.get("family_unweighted_score", 0.0),
                spatial_density.get("active_family_count", 0),
            ),
        )
    if "spatial_precision_sanity" in scorecard:
        spatial_sanity = scorecard["spatial_precision_sanity"]
        _log_metric(
            "Spatial precision-like sanity",
            "score=%.2f metadata=%.2f schema=%.2f precedence=%.2f inferred=%d pair_conflicts=%d"
            % (
                spatial_sanity.get("score", 0.0),
                spatial_sanity.get("metadata_score", 0.0),
                spatial_sanity.get("schema_score", 0.0),
                spatial_sanity.get("precedence_score", 0.0),
                spatial_sanity.get("inferred_total", 0),
                spatial_sanity.get("pair_conflict_count", 0),
            ),
        )
    if "spatial_quality" in scorecard:
        spatial_quality = scorecard["spatial_quality"]
        _log_metric(
            "Spatial quality",
            "score=%.2f metadata=%.2f schema=%.2f precedence=%.2f"
            % (
                spatial_quality.get("score", 0.0),
                spatial_quality.get("metadata_score", 0.0),
                spatial_quality.get("schema_score", 0.0),
                spatial_quality.get("precedence_score", 0.0),
            ),
        )
    if "spatial_pair_stats" in scorecard:
        pair_stats = scorecard["spatial_pair_stats"]
        _log_metric(
            "Spatial pair stats",
            ", ".join(
                "%s(candidates=%d,inferred=%d,score=%s)"
                % (
                    name,
                    stats.get("candidate_pairs", 0),
                    stats.get("inferred_pair_total", stats.get("inferred_total", 0)),
                    (
                        ("%.2f" % float(stats["coverage_score"]))
                        if stats.get("coverage_score") is not None
                        else "N/A"
                    ),
                )
                for name, stats in pair_stats.items()
            ),
        )
    if "spatial_pair_family_scores" in scorecard:
        family_scores = scorecard["spatial_pair_family_scores"]
        _log_metric(
            "Spatial pair family scores",
            ", ".join(
                "%s(score=%s,%d/%d)"
                % (
                    name,
                    (("%.2f" % float(stats["score"])) if stats.get("score") is not None else "N/A"),
                    int(stats.get("actual_total", 0)),
                    int(stats.get("expected_total", 0)),
                )
                for name, stats in family_scores.items()
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
        connects_added = _augment_connects_edges(
            graph,
            touch_epsilon=touch_epsilon,
            adjacent_epsilon=adjacent_epsilon,
            intersection_epsilon=intersection_epsilon,
        )
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
                f"edges+={len(graph.edges) - edge_before}, "
                f"connects_fallback+={connects_added}, spatial_edges+={spatial_added}"
            ),
        )
    else:
        _stage_skip("build_semantic_edges", detail="no semantic records")
        _stage_skip("build_geometry", detail="no semantic records")

    scorecard = _build_scorecard(
        graph,
        root,
        touch_epsilon=touch_epsilon,
        adjacent_epsilon=adjacent_epsilon,
        intersection_epsilon=intersection_epsilon,
    )
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
    summary = _build_graph_summary(
        graph,
        source,
        scorecard=scorecard,
        neo4j_export=neo4j_export,
        stage_durations=stage_durations,
    )
    write_graph_json_stream(
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
    )
    t_export_json = perf_counter() - t0
    t_total = perf_counter() - t0_total
    stage_durations["export_json"] = t_export_json
    stage_durations["total"] = t_total
    _stage_done("export_json", t_export_json, detail=str(target))

    _emit_conversion_report(
        graph,
        records_count=len(records),
        output_path=target,
        stage_durations=stage_durations,
        scorecard=scorecard,
        neo4j_export=neo4j_export,
    )
    LOGGER.info("Import complete: nodes=%d edges=%d", len(graph.nodes), len(graph.edges))
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
