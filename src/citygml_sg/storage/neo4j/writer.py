"""Neo4j write adapter."""

from __future__ import annotations

from citygml_sg.domain.edge import Edge
from citygml_sg.domain.node import Node
from citygml_sg.storage.neo4j.client import Neo4jClient
from citygml_sg.storage.neo4j.queries import UPSERT_EDGE_TEMPLATE, UPSERT_NODE


class Neo4jWriter:
    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    def write_nodes(self, nodes: list[Node]) -> None:
        with self._client.session() as session:
            for node in nodes:
                session.run(
                    UPSERT_NODE,
                    id=node.node_id,
                    properties={"node_type": node.node_type.value, **node.properties},
                )

    def write_edges(self, edges: list[Edge]) -> None:
        with self._client.session() as session:
            for edge in edges:
                query = UPSERT_EDGE_TEMPLATE.format(relation=edge.relation.value)
                session.run(
                    query,
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    properties=edge.properties,
                )
