"""Spatial relation precedence normalization utilities."""

from __future__ import annotations

from citygml_sg.domain.edge import Edge
from citygml_sg.domain.enums import RelationType

SPATIAL_PRECEDENCE: dict[RelationType, int] = {
    RelationType.ADJACENT_TO: 1,
    RelationType.TOUCHES: 2,
    RelationType.INTERSECTS: 3,
}


def normalize_spatial_precedence(edges: list[Edge]) -> tuple[list[Edge], int]:
    """Keep only the strongest spatial relation per (source_id, target_id) pair.

    Precedence rule:
    INTERSECTS > TOUCHES > ADJACENT_TO
    """

    strongest_by_pair: dict[tuple[str, str], tuple[int, RelationType]] = {}
    for edge in edges:
        rank = SPATIAL_PRECEDENCE.get(edge.relation)
        if rank is None:
            continue
        pair = (edge.source_id, edge.target_id)
        current = strongest_by_pair.get(pair)
        if current is None or rank > current[0]:
            strongest_by_pair[pair] = (rank, edge.relation)

    normalized: list[Edge] = []
    kept_spatial_pair: set[tuple[str, str]] = set()
    removed = 0

    for edge in edges:
        rank = SPATIAL_PRECEDENCE.get(edge.relation)
        if rank is None:
            normalized.append(edge)
            continue

        pair = (edge.source_id, edge.target_id)
        winner_relation = strongest_by_pair[pair][1]
        if edge.relation != winner_relation:
            removed += 1
            continue

        if pair in kept_spatial_pair:
            removed += 1
            continue

        kept_spatial_pair.add(pair)
        normalized.append(edge)

    return normalized, removed
