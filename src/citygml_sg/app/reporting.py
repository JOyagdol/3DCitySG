"""Terminal reporting helpers for the import pipeline."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable

from citygml_sg.domain.enums import NodeType, RelationType
from citygml_sg.graph.graph_builder import SceneGraph
from citygml_sg.utils.logging import get_logger

LOGGER = get_logger("citygml_sg.app.pipeline")


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
    *,
    semantic_node_types: set[NodeType],
    geometry_node_types: set[NodeType],
    semantic_relations: set[RelationType],
    spatial_relations: set[RelationType],
    geometry_relations: set[RelationType],
    pipeline_stage_order: tuple[str, ...],
    count_generic_attribute_entries: Callable[[SceneGraph], int],
    edge_index: Callable[[SceneGraph, RelationType], dict[str, list[str]]],
    descendants: Callable[[str, dict[str, list[str]]], set[str]],
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
    semantic_node_count = sum(node_counts[node_type] for node_type in semantic_node_types)
    geometry_node_count = sum(node_counts[node_type] for node_type in geometry_node_types)
    semantic_relation_count = sum(edge_counts[relation] for relation in semantic_relations)
    spatial_relation_count = sum(edge_counts[relation] for relation in spatial_relations)
    geometry_relation_count = sum(edge_counts[relation] for relation in geometry_relations)

    nodes_with_gml_name = sum(1 for node in graph.nodes.values() if "gml_name" in node.properties)
    nodes_with_generic_attributes = sum(
        1
        for node in graph.nodes.values()
        if any(key.startswith("attr_") and not key.endswith("_uom") for key in node.properties)
    )
    generic_attribute_entries = count_generic_attribute_entries(graph)

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
    has_ring_index = edge_index(graph, RelationType.HAS_RING)
    has_pos_index = edge_index(graph, RelationType.HAS_POS)
    for _polygon_id, rings in has_ring_index.items():
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

    contains_index = edge_index(graph, RelationType.CONTAINS)
    consists_of_building_part_index = edge_index(graph, RelationType.CONSISTS_OF_BUILDING_PART)
    interior_room_index = edge_index(graph, RelationType.INTERIOR_ROOM)
    outer_building_installation_index = edge_index(graph, RelationType.OUTER_BUILDING_INSTALLATION)
    interior_building_installation_index = edge_index(graph, RelationType.INTERIOR_BUILDING_INSTALLATION)
    room_installation_index = edge_index(graph, RelationType.ROOM_INSTALLATION)
    interior_furniture_index = edge_index(graph, RelationType.INTERIOR_FURNITURE)
    bounded_by_index = edge_index(graph, RelationType.BOUNDED_BY)
    has_opening_index = edge_index(graph, RelationType.HAS_OPENING)
    has_address_index = edge_index(graph, RelationType.HAS_ADDRESS)
    has_lod_geometry_index = edge_index(graph, RelationType.HAS_LOD_GEOMETRY)
    has_geometry_component_index = edge_index(graph, RelationType.HAS_GEOMETRY_COMPONENT)
    has_geometry_index = edge_index(graph, RelationType.HAS_GEOMETRY)

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
        semantic_desc = descendants(building_id, hierarchy_index)
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
    stage_items = [(stage, stage_durations.get(stage, 0.0)) for stage in pipeline_stage_order]
    max_stage_seconds = max((seconds for _, seconds in stage_items), default=0.0)
    for stage, seconds in stage_items:
        _log_metric(stage, f"{seconds:.3f}s [{_duration_bar(seconds, max_stage_seconds)}]")
    _log_metric("total", f"{stage_durations.get('total', 0.0):.3f}s")
    LOGGER.info("")
    _log_separator("=")
