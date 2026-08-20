"""Geometry subgraph builders for CityGML world-graph import."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable, Iterator
from xml.etree.ElementTree import Element

from citygml_sg.domain.edge import Edge
from citygml_sg.domain.enums import NodeType, RelationType
from citygml_sg.graph.edge_factory import create_edge
from citygml_sg.graph.graph_builder import SceneGraph
from citygml_sg.graph.node_factory import create_node
from citygml_sg.utils.xml import get_gml_id, local_name

BuildParentMapFn = Callable[[Element], dict[Element, Element]]
FallbackIdFn = Callable[[NodeType, Counter[str]], str]
NearestAncestorFn = Callable[[Element, dict[Element, Element], dict[Element, Any], set[NodeType]], Any | None]
AddEdgeIfValidFn = Callable[[SceneGraph, Edge], None]


def _parse_pos_text(text: str | None) -> list[float] | None:
    if not text:
        return None
    values: list[float] = []
    for token in text.strip().split():
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


def iter_ring_positions(ring_element: Element) -> Iterator[list[float]]:
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


def attach_lod_geometry_structure(
    graph: SceneGraph,
    root: Element,
    by_element: dict[Element, Any],
    *,
    build_parent_map: BuildParentMapFn,
    nearest_ancestor: NearestAncestorFn,
    fallback_id: FallbackIdFn,
    add_edge_if_valid: AddEdgeIfValidFn,
    object_node_types: set[NodeType],
) -> dict[Element, list[str]]:
    parent_map = build_parent_map(root)
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

        owner = nearest_ancestor(element, parent_map, by_element, object_node_types)
        if owner is None:
            continue

        raw_id = get_gml_id(element) or fallback_id(node_type, fallback_counters)
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
        add_edge_if_valid(
            graph,
            create_edge(owner.node_id, geometry_node_id, RelationType.HAS_LOD_GEOMETRY, **edge_props),
        )
        add_edge_if_valid(
            graph,
            create_edge(geometry_node_id, concrete_node_id, RelationType.HAS_GEOMETRY_COMPONENT, **edge_props),
        )
        concrete_geometry_node_by_element[element] = (concrete_node_id, node_type)

    for element in root.iter():
        if local_name(element.tag) != "ImplicitGeometry":
            continue
        owner = nearest_ancestor(element, parent_map, by_element, object_node_types)
        if owner is None:
            continue

        raw_id = get_gml_id(element) or fallback_id(NodeType.IMPLICIT_GEOMETRY, fallback_counters)
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
        add_edge_if_valid(
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


def attach_geometry_subgraph(
    graph: SceneGraph,
    root: Element,
    by_element: dict[Element, Any],
    *,
    build_parent_map: BuildParentMapFn,
    nearest_ancestor: NearestAncestorFn,
    fallback_id: FallbackIdFn,
    add_edge_if_valid: AddEdgeIfValidFn,
    object_node_types: set[NodeType],
    polygon_memberships: dict[Element, list[str]] | None = None,
) -> None:
    parent_map = build_parent_map(root)
    fallback_counters: Counter[str] = Counter()
    added_geometry_members: set[tuple[str, str]] = set()

    for element in root.iter():
        if local_name(element.tag) != "Polygon":
            continue

        owner = nearest_ancestor(element, parent_map, by_element, object_node_types)
        if owner is None:
            continue

        raw_polygon_id = get_gml_id(element) or fallback_id(NodeType.POLYGON, fallback_counters)
        polygon_node_id = f"polygon:{raw_polygon_id}"

        graph.add_node(
            create_node(
                polygon_node_id,
                NodeType.POLYGON,
                gml_id=raw_polygon_id,
                source_tag="Polygon",
            )
        )
        add_edge_if_valid(
            graph,
            create_edge(owner.node_id, polygon_node_id, RelationType.HAS_GEOMETRY),
        )
        for geometry_node_id in (polygon_memberships or {}).get(element, []):
            key = (geometry_node_id, polygon_node_id)
            if key in added_geometry_members:
                continue
            add_edge_if_valid(
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
                add_edge_if_valid(
                    graph,
                    create_edge(
                        polygon_node_id,
                        ring_node_id,
                        RelationType.HAS_RING,
                        ring_type=boundary_tag,
                    ),
                )

                for pos_index, coords in enumerate(iter_ring_positions(ring)):
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
                    add_edge_if_valid(
                        graph,
                        create_edge(
                            ring_node_id,
                            pos_node_id,
                            RelationType.HAS_POS,
                            order=pos_index,
                        ),
                    )