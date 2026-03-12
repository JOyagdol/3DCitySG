"""Top-level pipeline orchestration."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable, Iterator
from xml.etree.ElementTree import Element

from citygml_sg.domain.edge import Edge
from citygml_sg.domain.enums import NodeType, RelationType
from citygml_sg.graph.edge_factory import create_edge
from citygml_sg.graph.graph_builder import SceneGraph
from citygml_sg.graph.graph_schema import OBJECT_NODE_TYPES
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
from citygml_sg.utils.xml import get_gml_id, local_name

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

SEMANTIC_NODE_TYPES: set[NodeType] = {
    NodeType.BUILDING,
    NodeType.BUILDING_PART,
    NodeType.ROOM,
    NodeType.BOUNDARY_SURFACE,
    NodeType.OPENING,
    NodeType.BUILDING_FURNITURE,
}
GEOMETRY_NODE_TYPES: set[NodeType] = {
    NodeType.POLYGON,
    NodeType.LINEAR_RING,
    NodeType.POSITION,
}
SEMANTIC_RELATIONS: set[RelationType] = {
    RelationType.CONTAINS,
    RelationType.BOUNDED_BY,
    RelationType.HAS_OPENING,
}
SPATIAL_RELATIONS: set[RelationType] = {
    RelationType.INSIDE,
    RelationType.CONNECTS,
    RelationType.ADJACENT_TO,
    RelationType.TOUCHES,
}
GEOMETRY_RELATIONS: set[RelationType] = {
    RelationType.HAS_GEOMETRY,
    RelationType.HAS_RING,
    RelationType.HAS_POS,
}

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


def _attach_geometry_subgraph(
    graph: SceneGraph,
    root: Element,
    by_element: dict[Element, ElementRecord],
) -> None:
    parent_map = _build_parent_map(root)
    fallback_counters: Counter[str] = Counter()

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


def _build_semantic_edges(
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
            boundary = _nearest_ancestor(record.element, parent_map, by_element, {NodeType.BOUNDARY_SURFACE})
            if boundary:
                _add_edge_if_valid(graph, create_edge(boundary.node_id, record.node_id, RelationType.HAS_OPENING))

            room = _nearest_ancestor(record.element, parent_map, by_element, {NodeType.ROOM})
            if room:
                _add_edge_if_valid(graph, create_edge(record.node_id, room.node_id, RelationType.CONNECTS))

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


def _count_generic_attribute_entries(graph: SceneGraph) -> int:
    total = 0
    for node in graph.nodes.values():
        for key in node.properties:
            if key.startswith("attr_") and not key.endswith("_uom"):
                total += 1
    return total


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


def _emit_conversion_report(
    graph: SceneGraph,
    records_count: int,
    output_path: Path,
    stage_durations: dict[str, float],
) -> None:
    node_counts = Counter(node.node_type for node in graph.nodes.values())
    edge_counts = Counter(edge.relation for edge in graph.edges)
    nodes_by_id = graph.nodes

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

    _log_section("Distribution")
    _log_metric("Node type counts", node_counts_fmt)
    _log_metric("Relation counts", relation_counts_fmt)
    _log_metric(
        "Object counts",
        (
            "Building=%d BuildingPart=%d Room=%d BoundarySurface=%d Opening=%d "
            "BuildingFurniture=%d Polygon=%d LinearRing=%d Position=%d"
        )
        % (
            node_counts[NodeType.BUILDING],
            node_counts[NodeType.BUILDING_PART],
            node_counts[NodeType.ROOM],
            node_counts[NodeType.BOUNDARY_SURFACE],
            node_counts[NodeType.OPENING],
            node_counts[NodeType.BUILDING_FURNITURE],
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

    _log_section("Geometry Density")
    _log_metric("avg rings / polygon", f"{_avg(rings_per_polygon):.2f}")
    _log_metric("avg positions / ring", f"{_avg(pos_per_ring):.2f}")
    _log_metric("max positions / ring", max(pos_per_ring) if pos_per_ring else 0)

    contains_index = _edge_index(graph, RelationType.CONTAINS)
    bounded_by_index = _edge_index(graph, RelationType.BOUNDED_BY)
    has_opening_index = _edge_index(graph, RelationType.HAS_OPENING)
    has_geometry_index = _edge_index(graph, RelationType.HAS_GEOMETRY)

    building_ids = sorted(
        [node_id for node_id, node in nodes_by_id.items() if node.node_type == NodeType.BUILDING],
    )
    _log_section("Building Breakdown")
    _log_metric("Building breakdown count", len(building_ids))
    for building_id in building_ids:
        semantic_desc = _descendants(building_id, contains_index)
        semantic_scope = {building_id, *semantic_desc}

        part_ids = [n for n in semantic_scope if nodes_by_id.get(n) and nodes_by_id[n].node_type == NodeType.BUILDING_PART]
        room_ids = [n for n in semantic_scope if nodes_by_id.get(n) and nodes_by_id[n].node_type == NodeType.ROOM]

        boundary_ids: set[str] = set()
        furniture_ids: set[str] = set()
        for room_id in room_ids:
            boundary_ids.update(bounded_by_index.get(room_id, []))
            for child_id in contains_index.get(room_id, []):
                child_node = nodes_by_id.get(child_id)
                if child_node and child_node.node_type == NodeType.BUILDING_FURNITURE:
                    furniture_ids.add(child_id)

        opening_ids: set[str] = set()
        for boundary_id in boundary_ids:
            opening_ids.update(has_opening_index.get(boundary_id, []))

        polygon_ids: set[str] = set()
        for semantic_id in semantic_scope:
            polygon_ids.update(has_geometry_index.get(semantic_id, []))

        ring_ids: set[str] = set()
        for polygon_id in polygon_ids:
            ring_ids.update(has_ring_index.get(polygon_id, []))

        pos_ids: set[str] = set()
        for ring_id in ring_ids:
            pos_ids.update(has_pos_index.get(ring_id, []))

        name_nodes = sum(
            1
            for nid in semantic_scope
            if nodes_by_id.get(nid) is not None and "gml_name" in nodes_by_id[nid].properties
        )
        attr_entries = 0
        for nid in semantic_scope:
            node = nodes_by_id.get(nid)
            if node is None:
                continue
            attr_entries += sum(1 for key in node.properties if key.startswith("attr_") and not key.endswith("_uom"))

        _log_metric(
            f"Building[{building_id}]",
            (
                "parts=%d rooms=%d boundaries=%d openings=%d furniture=%d "
                "polygons=%d rings=%d positions=%d named_nodes=%d attr_entries=%d"
            )
            % (
                len(part_ids),
                len(room_ids),
                len(boundary_ids),
                len(opening_ids),
                len(furniture_ids),
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
        "Stage 5 JSON export",
        f"{'DONE' if output_path.exists() else 'NONE'} ({output_path})",
    )

    _log_section("Stage Durations (seconds)")
    _log_metric("parse_xml", f"{stage_durations.get('parse_xml', 0.0):.3f}")
    _log_metric("collect_semantics", f"{stage_durations.get('collect_semantics', 0.0):.3f}")
    _log_metric("build_nodes", f"{stage_durations.get('build_nodes', 0.0):.3f}")
    _log_metric("build_semantic_edges", f"{stage_durations.get('build_semantic_edges', 0.0):.3f}")
    _log_metric("build_geometry", f"{stage_durations.get('build_geometry', 0.0):.3f}")
    _log_metric("export_json", f"{stage_durations.get('export_json', 0.0):.3f}")
    _log_metric("total", f"{stage_durations.get('total', 0.0):.3f}")
    LOGGER.info("")
    _log_separator("=")


def run_import_pipeline(input_path: str, output_path: str = "data/output/import_summary.json") -> int:
    t0_total = perf_counter()
    source = Path(input_path)
    if not source.exists():
        LOGGER.error("Input file does not exist: %s", source)
        return 2
    if source.is_dir():
        LOGGER.error("Directory input is not supported yet. Provide a .gml/.xml file path.")
        return 2

    LOGGER.info("Import pipeline started: %s", source)
    t0 = perf_counter()
    root = read_citygml(source)
    t_parse_xml = perf_counter() - t0

    t0 = perf_counter()
    records, by_element = _collect_records(root)
    t_collect_semantics = perf_counter() - t0
    graph = SceneGraph()

    t0 = perf_counter()
    for record in records:
        graph.add_node(create_node(record.node_id, record.node_type, **record.properties))
    t_build_nodes = perf_counter() - t0

    t_build_semantic_edges = 0.0
    t_build_geometry = 0.0
    if records:
        t0 = perf_counter()
        _build_semantic_edges(graph, root, records, by_element)
        t_build_semantic_edges = perf_counter() - t0
        t0 = perf_counter()
        _attach_geometry_subgraph(graph, root, by_element)
        t_build_geometry = perf_counter() - t0

    payload = _graph_to_payload(graph, source)

    target = Path(output_path)
    ensure_dir(target.parent)
    t0 = perf_counter()
    write_json(target, payload)
    t_export_json = perf_counter() - t0
    t_total = perf_counter() - t0_total

    _emit_conversion_report(
        graph,
        records_count=len(records),
        output_path=target,
        stage_durations={
            "parse_xml": t_parse_xml,
            "collect_semantics": t_collect_semantics,
            "build_nodes": t_build_nodes,
            "build_semantic_edges": t_build_semantic_edges,
            "build_geometry": t_build_geometry,
            "export_json": t_export_json,
            "total": t_total,
        },
    )
    LOGGER.info("Import complete: nodes=%d edges=%d", payload["summary"]["node_count"], payload["summary"]["edge_count"])
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
