"""Scorecard construction for CityGML scene graph imports."""

from __future__ import annotations

from collections import Counter
from typing import Callable, Iterator
from xml.etree.ElementTree import Element

from citygml_sg.domain.bbox import BBox
from citygml_sg.domain.enums import NodeType, RelationType
from citygml_sg.domain.geometry import Point3D
from citygml_sg.domain.node import Node
from citygml_sg.graph.graph_builder import SceneGraph
from citygml_sg.utils.xml import GENERIC_ATTRIBUTE_TAGS, local_name
from citygml_sg.evaluation.spatial_metrics import build_spatial_score_metrics, safe_ratio

SCORE_NODE_WEIGHT = 0.40
SCORE_RELATION_WEIGHT = 0.30
SCORE_PROPERTY_WEIGHT = 0.30
SCORE_CRITERIA_COMMENT = "overall=0.40*node + 0.30*relation + 0.30*property"


def build_scorecard(
    graph: SceneGraph,
    root: Element,
    *,
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
    semantic_tag_set: set[str],
    boundary_surface_tags: set[str],
    opening_tags: set[str],
    connects_opening_types: set[str],
    appearance_fallback_owner_tags: set[str],
    semantic_node_types: set[NodeType],
    geometry_node_types: set[NodeType],
    build_parent_map: Callable[[Element], dict[Element, Element]],
    nearest_ancestor_by_tag: Callable[[Element, dict[Element, Element], set[str]], Element | None],
    direct_parent_tag: Callable[[Element, dict[Element, Element]], str | None],
    iter_ring_positions: Callable[[Element], Iterator[list[float]]],
    normalize_target_refs: Callable[[str | None], list[str]],
    count_generic_attribute_entries: Callable[[SceneGraph], int],
    build_room_spatial_scope: Callable[..., tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]], dict[str, int]]],
    build_node_bboxes: Callable[..., dict[str, BBox]],
    build_node_points: Callable[..., dict[str, list[Point3D]]],
    edge_index: Callable[[SceneGraph, RelationType], dict[str, list[str]]],
    is_door_or_window_opening: Callable[[Node], bool],
    is_connects_opening: Callable[[Node], bool],
    touch_min_contact_area: float,
    touch_min_contact_length: float,
) -> dict:
    node_counts = Counter(node.node_type for node in graph.nodes.values())
    edge_counts = Counter(edge.relation for edge in graph.edges)
    parent_map = build_parent_map(root)

    source_semantic_elements = [element for element in root.iter() if local_name(element.tag) in semantic_tag_set]
    source_boundary_elements = [element for element in root.iter() if local_name(element.tag) in boundary_surface_tags]
    source_opening_elements = [element for element in root.iter() if local_name(element.tag) in opening_tags]
    source_appearance_elements = [element for element in root.iter() if local_name(element.tag) == "Appearance"]
    source_polygon_elements = [element for element in root.iter() if local_name(element.tag) == "Polygon"]
    source_lod_geometry_elements = [
        element for element in root.iter() if local_name(element.tag) in {"Solid", "MultiSurface", "MultiCurve"}
    ]
    source_implicit_geometry_elements = [element for element in root.iter() if local_name(element.tag) == "ImplicitGeometry"]

    expected_semantic_nodes = len(source_semantic_elements)
    actual_semantic_nodes = sum(node_counts[node_type] for node_type in semantic_node_types)

    expected_has_geometry = 0
    expected_has_ring = 0
    expected_has_pos = 0
    expected_has_lod_geometry = 0
    expected_has_geometry_component = 0
    expected_has_geometry_member = 0
    for geometry_element in source_lod_geometry_elements:
        if nearest_ancestor_by_tag(geometry_element, parent_map, semantic_tag_set) is None:
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
        if nearest_ancestor_by_tag(implicit_geometry, parent_map, semantic_tag_set) is None:
            continue
        expected_has_lod_geometry += 1

    for polygon in source_polygon_elements:
        if nearest_ancestor_by_tag(polygon, parent_map, semantic_tag_set) is None:
            continue
        expected_has_geometry += 1
        for boundary in list(polygon):
            if local_name(boundary.tag) not in {"exterior", "interior"}:
                continue
            for ring in list(boundary):
                if local_name(ring.tag) != "LinearRing":
                    continue
                expected_has_ring += 1
                expected_has_pos += sum(1 for _ in iter_ring_positions(ring))

    expected_geometry_nodes = (
        expected_has_lod_geometry
        + expected_has_geometry_component
        + expected_has_geometry
        + expected_has_ring
        + expected_has_pos
    )
    actual_geometry_nodes = sum(node_counts[node_type] for node_type in geometry_node_types)

    # Fair scoring policy (CityGML 2.0, current supported scope):
    # 1) Expected counts are computed only from object/relation/property channels that
    #    are explicitly supported by this pipeline (not from all possible XML elements).
    # 2) Expected relation counts follow schema-allowed structural links reconstructed
    #    from source hierarchy.
    # 3) Property expectations are counted only on semantic target elements where the
    #    corresponding direct child tags actually exist.
    node_coverage_ratio = safe_ratio(
        actual_semantic_nodes + actual_geometry_nodes,
        expected_semantic_nodes + expected_geometry_nodes,
    )

    expected_bounded_by = sum(
        1
        for boundary in source_boundary_elements
        if nearest_ancestor_by_tag(
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
        if nearest_ancestor_by_tag(opening, parent_map, boundary_surface_tags) is not None
    )
    expected_connects = sum(
        1
        for opening in source_opening_elements
        if local_name(opening.tag) in connects_opening_types
        if nearest_ancestor_by_tag(opening, parent_map, {"Room"}) is not None
    )
    expected_has_city_object = sum(
        1
        for element in source_semantic_elements
        if direct_parent_tag(element, parent_map) == "cityObjectMember"
        and nearest_ancestor_by_tag(element, parent_map, {"cityObjectMember"}) is not None
    )
    expected_has_group_member = sum(
        1
        for element in source_semantic_elements
        if direct_parent_tag(element, parent_map) == "groupMember"
        and nearest_ancestor_by_tag(element, parent_map, {"CityObjectGroup"}) is not None
    )
    has_appearance_fallback_owner = any(
        local_name(element.tag) in appearance_fallback_owner_tags for element in source_semantic_elements
    )
    expected_has_appearance = sum(
        1
        for appearance in source_appearance_elements
        if nearest_ancestor_by_tag(appearance, parent_map, semantic_tag_set) is not None or has_appearance_fallback_owner
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
                for ref in normalize_target_refs(child.text)
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
        and direct_parent_tag(element, parent_map) == "consistsOfBuildingPart"
        and nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
    )
    expected_interior_room = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "Room"
        and direct_parent_tag(element, parent_map) == "interiorRoom"
        and nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
    )
    expected_interior_furniture = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "BuildingFurniture"
        and direct_parent_tag(element, parent_map) == "interiorFurniture"
        and nearest_ancestor_by_tag(element, parent_map, {"Room"}) is not None
    )
    expected_outer_building_installation = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "BuildingInstallation"
        and direct_parent_tag(element, parent_map) == "outerBuildingInstallation"
        and nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
    )
    expected_interior_building_installation = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "IntBuildingInstallation"
        and direct_parent_tag(element, parent_map) == "interiorBuildingInstallation"
        and nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
    )
    expected_room_installation = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "IntBuildingInstallation"
        and direct_parent_tag(element, parent_map) == "roomInstallation"
        and nearest_ancestor_by_tag(element, parent_map, {"Room"}) is not None
    )
    expected_contains = (
        sum(
            1
            for element in source_semantic_elements
            if local_name(element.tag) == "BuildingPart"
            and direct_parent_tag(element, parent_map) != "consistsOfBuildingPart"
            and nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
        )
        + sum(
            1
            for element in source_semantic_elements
            if local_name(element.tag) == "Room"
            and direct_parent_tag(element, parent_map) != "interiorRoom"
            and nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
        )
        + sum(
            1
            for element in source_semantic_elements
            if local_name(element.tag) == "BuildingFurniture"
            and direct_parent_tag(element, parent_map) != "interiorFurniture"
            and nearest_ancestor_by_tag(element, parent_map, {"Room"}) is not None
        )
        + sum(
            1
            for element in source_semantic_elements
            if local_name(element.tag) == "BuildingInstallation"
            and direct_parent_tag(element, parent_map) != "outerBuildingInstallation"
            and nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
        )
        + sum(
            1
            for element in source_semantic_elements
            if local_name(element.tag) == "IntBuildingInstallation"
            and direct_parent_tag(element, parent_map) not in {"interiorBuildingInstallation", "roomInstallation"}
            and nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart", "Room"}) is not None
        )
    )
    expected_inside = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "BuildingFurniture"
        and nearest_ancestor_by_tag(element, parent_map, {"Room"}) is not None
    )
    expected_has_address = sum(
        1
        for element in source_semantic_elements
        if local_name(element.tag) == "Address"
        and nearest_ancestor_by_tag(element, parent_map, {"Building", "BuildingPart"}) is not None
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
        safe_ratio(edge_counts[relation], expected)
        for relation, expected in relation_expectations.items()
        if expected > 0
    ]
    relation_coverage_ratio = (sum(relation_scores) / len(relation_scores)) if relation_scores else 1.0

    semantic_nodes = [node for node in graph.nodes.values() if node.node_type in semantic_node_types]

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
        "generic_attributes": count_generic_attribute_entries(graph),
    }
    expected_properties_total = sum(expected_property_counts.values())
    actual_properties_total = sum(actual_property_counts.values())
    property_coverage_ratio = safe_ratio(actual_properties_total, expected_properties_total)

    overall_score = (
        node_coverage_ratio * SCORE_NODE_WEIGHT
        + relation_coverage_ratio * SCORE_RELATION_WEIGHT
        + property_coverage_ratio * SCORE_PROPERTY_WEIGHT
    ) * 100.0
    spatial_metrics = build_spatial_score_metrics(
        graph,
        expected_connects_total=expected_connects,
        touch_epsilon=touch_epsilon,
        adjacent_epsilon=adjacent_epsilon,
        intersection_epsilon=intersection_epsilon,
        build_room_spatial_scope=build_room_spatial_scope,
        edge_index=edge_index,
        build_node_bboxes=build_node_bboxes,
        build_node_points=build_node_points,
        is_door_or_window_opening=is_door_or_window_opening,
        is_connects_opening=is_connects_opening,
        touch_min_contact_area=touch_min_contact_area,
        touch_min_contact_length=touch_min_contact_length,
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
