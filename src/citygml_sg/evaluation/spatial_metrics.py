"""Spatial score metrics for scene graph evaluation."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable

from citygml_sg.domain.bbox import BBox
from citygml_sg.domain.enums import NodeType, RelationType
from citygml_sg.domain.geometry import Point3D
from citygml_sg.domain.node import Node
from citygml_sg.graph.graph_builder import SceneGraph
from citygml_sg.graph.graph_schema import ALLOWED_RELATIONS
from citygml_sg.relations.spatial_inference import infer_spatial_relation
from citygml_sg.utils.logging import get_logger

LOGGER = get_logger("citygml_sg.app.pipeline")

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
SPATIAL_FAMILY_WEIGHTS: dict[str, float] = {
    "furniture_boundary_surface": 0.30,
    "furniture_opening": 0.25,
    "furniture_furniture": 0.25,
    "opening_room_connects": 0.20,
}


def safe_ratio(actual: int, expected: int) -> float:
    if expected <= 0:
        return 1.0
    return min(actual / expected, 1.0)


def spatial_pair_family(
    source_node: Node,
    target_node: Node,
    *,
    is_door_or_window_opening: Callable[[Node], bool],
) -> str | None:
    source_type = source_node.node_type
    target_type = target_node.node_type

    if {source_type, target_type} == {NodeType.BUILDING_FURNITURE, NodeType.BOUNDARY_SURFACE}:
        return "furniture_boundary_surface"
    if {source_type, target_type} == {NodeType.BUILDING_FURNITURE, NodeType.OPENING}:
        opening_node = source_node if source_type == NodeType.OPENING else target_node
        if not is_door_or_window_opening(opening_node):
            return None
        return "furniture_opening"
    if source_type == NodeType.BUILDING_FURNITURE and target_type == NodeType.BUILDING_FURNITURE:
        return "furniture_furniture"
    return None


def build_spatial_score_metrics(
    graph: SceneGraph,
    *,
    expected_connects_total: int = 0,
    touch_epsilon: float,
    adjacent_epsilon: float,
    intersection_epsilon: float,
    build_room_spatial_scope: Callable[
        ...,
        tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]], dict[str, int]],
    ],
    edge_index: Callable[[SceneGraph, RelationType], dict[str, list[str]]],
    build_node_bboxes: Callable[..., dict[str, BBox]],
    build_node_points: Callable[..., dict[str, list[Point3D]]],
    is_door_or_window_opening: Callable[[Node], bool],
    is_connects_opening: Callable[[Node], bool],
    touch_min_contact_area: float,
    touch_min_contact_length: float,
) -> dict[str, object]:
    nodes_by_id = graph.nodes
    connects_index = edge_index(graph, RelationType.CONNECTS)  # opening -> room
    room_to_furniture, room_to_boundary, room_to_opening, scope_stats = build_room_spatial_scope(
        graph,
        include_container_fallback=True,
        collapse_layered_fallback=True,
        edge_index=edge_index,
        build_node_bboxes=build_node_bboxes,
        is_door_or_window_opening=is_door_or_window_opening,
    )
    room_to_boundary_for_connects = room_to_boundary
    if scope_stats["fallback_room_count"] > 0:
        LOGGER.info(
            "[ScoreScope] room boundary fallback used: "
            "rooms=%d raw_links=%d collapsed_links=%d reduced=%d",
            scope_stats["fallback_room_count"],
            scope_stats["fallback_boundary_link_count"],
            scope_stats["fallback_boundary_collapsed_link_count"],
            scope_stats["fallback_boundary_reduced_link_count"],
        )
    has_opening_index = edge_index(graph, RelationType.HAS_OPENING)  # boundary surface -> opening

    target_types = {NodeType.BUILDING_FURNITURE, NodeType.BOUNDARY_SURFACE, NodeType.OPENING}
    node_bboxes = build_node_bboxes(graph, target_types=target_types)
    node_points = build_node_points(graph, target_types=target_types)

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
    for _room_id, furniture_ids in room_to_furniture.items():
        furniture_bbox_ids = sorted(
            {node_id for node_id in furniture_ids if node_id in node_bboxes}
        )
        boundary_bbox_ids = sorted(
            {node_id for node_id in room_to_boundary.get(_room_id, []) if node_id in node_bboxes}
        )
        opening_bbox_ids = sorted(
            {node_id for node_id in room_to_opening.get(_room_id, []) if node_id in node_bboxes}
        )

        for furniture_id in furniture_bbox_ids:
            for boundary_id in boundary_bbox_ids:
                candidate_pair_keys["furniture_boundary_surface"].add(
                    tuple(sorted((furniture_id, boundary_id)))
                )

        for furniture_id in furniture_bbox_ids:
            for opening_id in opening_bbox_ids:
                candidate_pair_keys["furniture_opening"].add(
                    tuple(sorted((furniture_id, opening_id)))
                )

        for index, source_id in enumerate(furniture_bbox_ids):
            for target_id in furniture_bbox_ids[index + 1 :]:
                candidate_pair_keys["furniture_furniture"].add(
                    tuple(sorted((source_id, target_id)))
                )

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
        family = spatial_pair_family(
            source_node,
            target_node,
            is_door_or_window_opening=is_door_or_window_opening,
        )
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
        confidence_in_range = (
            isinstance(confidence, (int, float)) and 0.0 <= float(confidence) <= 1.0
        )
        method_is_string = isinstance(metadata.get("method"), str) and bool(
            str(metadata.get("method")).strip()
        )
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
                if not is_connects_opening(opening_node):
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
        if not is_connects_opening(source_node):
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
            if not is_connects_opening(opening_node):
                continue
            for room_id in room_ids:
                room_node = nodes_by_id.get(room_id)
                if room_node is None or room_node.node_type != NodeType.ROOM:
                    continue
                candidate_pair_keys["opening_room_connects"].add((opening_id, room_id))
    candidate_pair_counts["opening_room_connects"] = max(
        connects_candidate_total, len(candidate_pair_keys["opening_room_connects"])
    )
    candidate_pair_counts_directed["opening_room_connects"] = candidate_pair_counts[
        "opening_room_connects"
    ]

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
                touch_min_contact_area=touch_min_contact_area,
                touch_min_contact_length=touch_min_contact_length,
            )
            if relation is not None:
                plausible += 1
        plausible_pair_counts[family] = plausible

    pair_count = len(pair_relations)
    precedence_valid_pairs = sum(1 for relations in pair_relations.values() if len(relations) <= 1)
    pair_conflict_count = sum(max(0, len(relations) - 1) for relations in pair_relations.values())

    metadata_ratio = safe_ratio(metadata_valid_total, inferred_total)
    schema_ratio = safe_ratio(schema_valid_total, inferred_total)
    precedence_ratio = safe_ratio(precedence_valid_pairs, pair_count)
    precision_like_ratio = (metadata_ratio + schema_ratio + precedence_ratio) / 3.0

    active_families = [family for family, total in candidate_pair_counts.items() if total > 0]
    inferred_pair_total = int(
        sum(len(family_inferred_pair_keys[family]) for family in active_families)
    )
    expected_pair_total = int(sum(candidate_pair_counts[family] for family in active_families))
    plausible_expected_total = int(sum(plausible_pair_counts[family] for family in active_families))
    expected_directed_total = int(
        sum(candidate_pair_counts_directed[family] for family in active_families)
    )
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
            family_coverage_ratio = safe_ratio(family_inferred_pair_total, int(candidate_total))
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
            "coverage_score": (
                round(family_coverage_ratio * 100.0, 2)
                if family_coverage_ratio is not None
                else None
            ),
            "relation_counts": dict(relation_counts),
        }
        pair_family_scores[family] = {
            "score": (
                round(family_coverage_ratio * 100.0, 2)
                if family_coverage_ratio is not None
                else None
            ),
            "actual_total": family_inferred_pair_total,
            "expected_total": int(candidate_total),
            "weight": family_weight,
            "weighted_score_contribution": (
                round(family_coverage_ratio * family_weight * 100.0, 2)
                if family_coverage_ratio is not None
                else None
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
    family_weighted_ratio = (
        (weighted_score_sum / weighted_score_weight_sum)
        if weighted_score_weight_sum > 0
        else 1.0
    )
    raw_coverage_ratio = safe_ratio(inferred_pair_total, expected_pair_total)
    plausible_coverage_ratio = safe_ratio(inferred_pair_total, plausible_expected_total)
    density_ratio = family_weighted_ratio

    return {
        "spatial_coverage": {
            "score": round(raw_coverage_ratio * 100.0, 2),
            "actual_total": int(inferred_pair_total),
            "expected_total": int(expected_pair_total),
            "actual_directed_total": int(inferred_directed_total_coverage),
            "expected_directed_total": int(expected_directed_total),
            "definition": (
                "raw candidate-hit-rate over active undirected candidate pairs in v1 scope"
            ),
        },
        "spatial_plausible_coverage": {
            "score": round(plausible_coverage_ratio * 100.0, 2),
            "actual_total": int(inferred_pair_total),
            "plausible_expected_total": int(plausible_expected_total),
            "expected_total": int(expected_pair_total),
            "definition": (
                "epsilon-aware plausible candidate hit-rate over active undirected "
                "candidate pairs in v1 scope"
            ),
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
            "definition": (
                "density-only spatial coverage metric (pair hit-rate), "
                "separated from quality sanity"
            ),
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
            "connects_candidate_strategy": (
                "max(source_expected, structural_chain, inferred_pairs_floor)"
            ),
            "plausible_expected_policy": (
                "epsilon-aware plausible candidates reported as supplementary denominator"
            ),
        },
    }
