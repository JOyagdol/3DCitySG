"""Graph validation routines."""

from __future__ import annotations

from citygml_sg.graph.graph_builder import SceneGraph


def validate_graph(graph: SceneGraph) -> list[str]:
    errors: list[str] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in graph.edges:
        if edge.source_id not in graph.nodes:
            errors.append(f"missing source node: {edge.source_id}")
        if edge.target_id not in graph.nodes:
            errors.append(f"missing target node: {edge.target_id}")
        key = (edge.source_id, edge.relation.value, edge.target_id)
        if key in seen_edges:
            errors.append(f"duplicate edge: {edge.source_id}-[{edge.relation.value}]->{edge.target_id}")
        else:
            seen_edges.add(key)
    return errors
