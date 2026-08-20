"""Appearance subgraph builders for CityGML world-graph import."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable
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


def normalize_target_refs(raw_value: str | None) -> list[str]:
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


def attach_appearance_subgraph(
    graph: SceneGraph,
    root: Element,
    by_element: dict[Element, Any],
    *,
    build_parent_map: BuildParentMapFn,
    nearest_ancestor: NearestAncestorFn,
    fallback_id: FallbackIdFn,
    add_edge_if_valid: AddEdgeIfValidFn,
    object_node_types: set[NodeType],
) -> None:
    parent_map = build_parent_map(root)
    fallback_counters: Counter[str] = Counter()
    xlink_href_key = "{http://www.w3.org/1999/xlink}href"

    gml_id_to_node_ids: dict[str, list[str]] = defaultdict(list)
    for node_id, node in graph.nodes.items():
        raw_gml_id = node.properties.get("gml_id")
        if isinstance(raw_gml_id, str) and raw_gml_id.strip():
            gml_id_to_node_ids[raw_gml_id.strip()].append(node_id)

    fallback_owner: Any | None = None
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

        raw_appearance_id = get_gml_id(element) or fallback_id(NodeType.APPEARANCE, fallback_counters)
        appearance_node_id = f"appearance:{raw_appearance_id}"
        theme = _first_direct_child_text(element, "theme")
        owner_resolution = "unresolved"
        owner = nearest_ancestor(element, parent_map, by_element, object_node_types)
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
            add_edge_if_valid(graph, create_edge(owner.node_id, appearance_node_id, RelationType.HAS_APPEARANCE))

        for surface_data_member in list(element):
            if local_name(surface_data_member.tag) != "surfaceDataMember":
                continue

            for surface_data in list(surface_data_member):
                surface_data_tag = local_name(surface_data.tag)
                raw_surface_data_id = get_gml_id(surface_data) or fallback_id(NodeType.SURFACE_DATA, fallback_counters)
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
                        target_refs.extend(normalize_target_refs(child.text))
                    elif child_name == "targetUri":
                        target_refs.extend(normalize_target_refs(child.text))
                    elif child_name in {"surfaceGeometry", "surfaceGeometryRef"}:
                        href_value = child.get(xlink_href_key) or child.get("href")
                        target_refs.extend(normalize_target_refs(href_value))

                unique_target_refs = sorted(set(target_refs))
                if unique_target_refs:
                    surface_data_properties["target_count"] = len(unique_target_refs)
                    surface_data_properties["target_refs"] = unique_target_refs

                graph.add_node(create_node(surface_data_node_id, NodeType.SURFACE_DATA, **surface_data_properties))
                add_edge_if_valid(
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
                        add_edge_if_valid(
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
