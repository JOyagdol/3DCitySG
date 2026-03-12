"""Node factory utilities."""

from __future__ import annotations

from citygml_sg.domain.enums import NodeType
from citygml_sg.domain.node import Node


def create_node(node_id: str, node_type: NodeType, **properties: object) -> Node:
    return Node(node_id=node_id, node_type=node_type, properties=dict(properties))
