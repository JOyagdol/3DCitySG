from __future__ import annotations

from citygml_sg.domain.enums import RelationType
from citygml_sg.graph.edge_factory import create_edge
from citygml_sg.relations.spatial_priority import normalize_spatial_precedence


def test_intersects_wins_over_touches_and_adjacent() -> None:
    edges = [
        create_edge("f1", "s1", RelationType.ADJACENT_TO),
        create_edge("f1", "s1", RelationType.TOUCHES),
        create_edge("f1", "s1", RelationType.INTERSECTS),
    ]

    normalized, removed = normalize_spatial_precedence(edges)
    assert removed == 2
    assert len(normalized) == 1
    assert normalized[0].relation == RelationType.INTERSECTS


def test_touches_wins_over_adjacent() -> None:
    edges = [
        create_edge("f1", "s1", RelationType.ADJACENT_TO),
        create_edge("f1", "s1", RelationType.TOUCHES),
    ]

    normalized, removed = normalize_spatial_precedence(edges)
    assert removed == 1
    assert len(normalized) == 1
    assert normalized[0].relation == RelationType.TOUCHES


def test_reverse_direction_is_independent_pair() -> None:
    edges = [
        create_edge("f1", "s1", RelationType.INTERSECTS),
        create_edge("s1", "f1", RelationType.TOUCHES),
    ]

    normalized, removed = normalize_spatial_precedence(edges)
    assert removed == 0
    assert len(normalized) == 2
    assert {(edge.source_id, edge.target_id, edge.relation) for edge in normalized} == {
        ("f1", "s1", RelationType.INTERSECTS),
        ("s1", "f1", RelationType.TOUCHES),
    }


def test_non_priority_relations_are_preserved() -> None:
    edges = [
        create_edge("f1", "s1", RelationType.ADJACENT_TO),
        create_edge("f1", "s1", RelationType.TOUCHES),
        create_edge("f1", "r1", RelationType.INSIDE),
    ]

    normalized, removed = normalize_spatial_precedence(edges)
    assert removed == 1
    assert len(normalized) == 2
    assert any(edge.relation == RelationType.INSIDE for edge in normalized)
