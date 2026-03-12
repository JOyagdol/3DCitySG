"""Neo4j read adapter."""

from __future__ import annotations

from citygml_sg.storage.neo4j.client import Neo4jClient


class Neo4jReader:
    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    def fetch_node_count(self) -> int:
        with self._client.session() as session:
            result = session.run("MATCH (n:CityObject) RETURN count(n) AS c")
            return int(result.single()["c"])
