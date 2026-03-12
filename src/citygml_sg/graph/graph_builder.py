"""In-memory scene graph builder."""

from __future__ import annotations

from dataclasses import dataclass, field

from citygml_sg.domain.edge import Edge
from citygml_sg.domain.node import Node
from citygml_sg.graph.graph_schema import ALLOWED_RELATIONS


@dataclass(slots=True)
class SceneGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: Edge) -> None:
        source = self.nodes.get(edge.source_id)
        target = self.nodes.get(edge.target_id)
        if source is None or target is None:
            raise ValueError("Both source and target nodes must exist before adding an edge")
        triple = (source.node_type, edge.relation, target.node_type)
        if triple not in ALLOWED_RELATIONS:
            raise ValueError(f"Relation not allowed by schema: {triple}")
        self.edges.append(edge)
