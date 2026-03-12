"""Edge factory utilities."""

from __future__ import annotations

from citygml_sg.domain.edge import Edge
from citygml_sg.domain.enums import RelationType


def create_edge(source_id: str, target_id: str, relation: RelationType, **properties: object) -> Edge:
    return Edge(source_id=source_id, target_id=target_id, relation=relation, properties=dict(properties))
