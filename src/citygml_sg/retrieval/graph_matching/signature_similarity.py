"""Small signature-similarity helpers for room retrieval."""

from __future__ import annotations

from typing import Mapping

from citygml_sg.world_graph.signatures import RoomSignature


NumericMap = Mapping[str, int | float]


def weighted_overlap_score(observed: NumericMap, candidate: NumericMap) -> float:
    """Score how much of an observed count/weight map is covered by a candidate map."""
    denominator = sum(max(float(value), 0.0) for value in observed.values())
    if denominator <= 0.0:
        return 0.0
    numerator = 0.0
    for key, observed_value in observed.items():
        observed_weight = max(float(observed_value), 0.0)
        candidate_weight = max(float(candidate.get(key, 0.0)), 0.0)
        numerator += min(observed_weight, candidate_weight)
    return numerator / denominator


def score_room_signature(
    observed_objects: NumericMap,
    observed_openings: NumericMap,
    observed_relations: NumericMap,
    signature: RoomSignature,
    *,
    object_weight: float = 0.45,
    opening_weight: float = 0.25,
    relation_weight: float = 0.30,
) -> dict[str, float]:
    """Return a normalized similarity score between OVG features and one room signature."""
    object_score = weighted_overlap_score(observed_objects, signature.object_counts)
    opening_score = weighted_overlap_score(observed_openings, signature.opening_counts)
    relation_score = weighted_overlap_score(observed_relations, signature.relation_counts)
    total_weight = object_weight + opening_weight + relation_weight
    total_score = 0.0
    if total_weight > 0.0:
        total_score = (
            object_score * object_weight
            + opening_score * opening_weight
            + relation_score * relation_weight
        ) / total_weight
    return {
        "total_score": total_score,
        "object_score": object_score,
        "opening_score": opening_score,
        "relation_score": relation_score,
    }
