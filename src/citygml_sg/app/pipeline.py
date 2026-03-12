"""Top-level pipeline orchestration."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from xml.etree.ElementTree import Element

from citygml_sg.domain.edge import Edge
from citygml_sg.domain.enums import NodeType, RelationType
from citygml_sg.graph.edge_factory import create_edge
from citygml_sg.graph.graph_builder import SceneGraph
from citygml_sg.graph.node_factory import create_node
from citygml_sg.modules.boundary_surface.parser import parse_boundary_surface_element
from citygml_sg.modules.building.parser import parse_building_element
from citygml_sg.modules.building_furniture.parser import parse_building_furniture_element
from citygml_sg.modules.building_part.parser import parse_building_part_element
from citygml_sg.modules.opening.parser import parse_opening_element
from citygml_sg.modules.room.parser import parse_room_element
from citygml_sg.parsers.citygml.reader import read_citygml
from citygml_sg.storage.json.writer import write_json
from citygml_sg.utils.io import ensure_dir
from citygml_sg.utils.logging import get_logger
from citygml_sg.utils.xml import local_name

LOGGER = get_logger(__name__)

BOUNDARY_SURFACE_TAGS = {
    "WallSurface",
    "RoofSurface",
    "GroundSurface",
    "InteriorWallSurface",
    "FloorSurface",
    "CeilingSurface",
    "ClosureSurface",
}
OPENING_TAGS = {"Door", "Window"}

ParserFn = Callable[[Element], dict]

OBJECT_PARSERS: dict[str, tuple[NodeType, ParserFn]] = {
    "Building": (NodeType.BUILDING, parse_building_element),
    "BuildingPart": (NodeType.BUILDING_PART, parse_building_part_element),
    "Room": (NodeType.ROOM, parse_room_element),
    "BuildingFurniture": (NodeType.BUILDING_FURNITURE, parse_building_furniture_element),
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
        properties = parser(element)
        node_id = properties.get("gml_id") or _fallback_id(node_type, fallback_counters)
        properties["gml_id"] = node_id
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


def _build_edges(
    graph: SceneGraph,
    root: Element,
    records: list[ElementRecord],
    by_element: dict[Element, ElementRecord],
) -> None:
    parent_map = _build_parent_map(root)

    for record in records:
        if record.node_type == NodeType.BUILDING_PART:
            parent = _nearest_ancestor(record.element, parent_map, by_element, {NodeType.BUILDING})
            if parent:
                _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.CONTAINS))

        elif record.node_type == NodeType.ROOM:
            parent = _nearest_ancestor(
                record.element,
                parent_map,
                by_element,
                {NodeType.BUILDING, NodeType.BUILDING_PART},
            )
            if parent:
                _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.CONTAINS))

        elif record.node_type == NodeType.BOUNDARY_SURFACE:
            parent = _nearest_ancestor(record.element, parent_map, by_element, {NodeType.ROOM})
            if parent:
                _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.BOUNDED_BY))

        elif record.node_type == NodeType.OPENING:
            parent = _nearest_ancestor(record.element, parent_map, by_element, {NodeType.ROOM})
            if parent:
                _add_edge_if_valid(graph, create_edge(record.node_id, parent.node_id, RelationType.CONNECTS))

        elif record.node_type == NodeType.BUILDING_FURNITURE:
            parent = _nearest_ancestor(record.element, parent_map, by_element, {NodeType.ROOM})
            if parent:
                _add_edge_if_valid(graph, create_edge(parent.node_id, record.node_id, RelationType.CONTAINS))
                _add_edge_if_valid(graph, create_edge(record.node_id, parent.node_id, RelationType.INSIDE))


def _graph_to_payload(graph: SceneGraph, input_path: Path) -> dict:
    node_counts = Counter(node.node_type.value for node in graph.nodes.values())
    edge_counts = Counter(edge.relation.value for edge in graph.edges)

    return {
        "summary": {
            "input_path": str(input_path),
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "node_type_counts": dict(node_counts),
            "relation_counts": dict(edge_counts),
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


def run_import_pipeline(input_path: str, output_path: str = "data/output/import_summary.json") -> int:
    source = Path(input_path)
    if not source.exists():
        LOGGER.error("Input file does not exist: %s", source)
        return 2
    if source.is_dir():
        LOGGER.error("Directory input is not supported yet. Provide a .gml/.xml file path.")
        return 2

    LOGGER.info("Import pipeline started: %s", source)
    root = read_citygml(source)

    records, by_element = _collect_records(root)
    graph = SceneGraph()

    for record in records:
        graph.add_node(create_node(record.node_id, record.node_type, **record.properties))

    if records:
        _build_edges(graph, root, records, by_element)

    payload = _graph_to_payload(graph, source)

    target = Path(output_path)
    ensure_dir(target.parent)
    write_json(target, payload)

    LOGGER.info(
        "Import complete: nodes=%d edges=%d output=%s",
        payload["summary"]["node_count"],
        payload["summary"]["edge_count"],
        target,
    )
    return 0


def run_relation_pipeline() -> int:
    LOGGER.info("Relation extraction pipeline started")
    LOGGER.info("TODO: wire candidate search + rule-based relation extraction")
    return 0


def run_export_pipeline() -> int:
    LOGGER.info("Graph export pipeline started")
    LOGGER.info("TODO: support Neo4j/JSON/Parquet export adapters")
    return 0


def run_benchmark_pipeline() -> int:
    LOGGER.info("Benchmark pipeline started")
    LOGGER.info("TODO: add benchmark query cases")
    return 0
