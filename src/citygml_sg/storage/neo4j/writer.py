"""Neo4j write adapter."""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Callable, Iterator, TypeVar

from citygml_sg.domain.edge import Edge
from citygml_sg.domain.node import Node
from citygml_sg.storage.neo4j.client import Neo4jClient
from citygml_sg.storage.neo4j.queries import (
    UPSERT_EDGE_BATCH_TEMPLATE,
    UPSERT_NODE_WITH_LABEL_BATCH_TEMPLATE,
)

T = TypeVar("T")


class Neo4jWriter:
    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    @staticmethod
    def _chunked(items: list[T], size: int) -> Iterator[list[T]]:
        if size <= 0:
            yield items
            return
        for i in range(0, len(items), size):
            yield items[i : i + size]

    @staticmethod
    def _safe_label(label: str) -> str:
        cleaned = re.sub(r"[^0-9A-Za-z_]", "_", label)
        if not cleaned:
            return "UnknownType"
        if cleaned[0].isdigit():
            return f"N_{cleaned}"
        return cleaned

    def write_nodes(
        self,
        nodes: list[Node],
        progress_callback: Callable[[int, int], None] | None = None,
        progress_step: int | None = None,
        batch_size: int = 5000,
    ) -> None:
        total = len(nodes)
        if progress_callback is not None:
            progress_callback(0, total)

        step = progress_step if (progress_step is not None and progress_step > 0) else max(1, total // 100)
        nodes_by_label: dict[str, list[Node]] = defaultdict(list)
        for node in nodes:
            nodes_by_label[self._safe_label(node.node_type.value)].append(node)

        done = 0

        with self._client.session() as session:
            for label, typed_nodes in nodes_by_label.items():
                query = UPSERT_NODE_WITH_LABEL_BATCH_TEMPLATE.format(label=label)
                for chunk in self._chunked(typed_nodes, batch_size):
                    rows = [
                        {
                            "id": node.node_id,
                            "properties": {"node_type": node.node_type.value, **node.properties},
                        }
                        for node in chunk
                    ]
                    session.run(query, rows=rows)
                    done += len(chunk)
                    if progress_callback is not None and (done % step == 0 or done == total):
                        progress_callback(done, total)

    def write_edges(
        self,
        edges: list[Edge],
        progress_callback: Callable[[int, int], None] | None = None,
        progress_step: int | None = None,
        batch_size: int = 5000,
    ) -> None:
        total = len(edges)
        if progress_callback is not None:
            progress_callback(0, total)

        step = progress_step if (progress_step is not None and progress_step > 0) else max(1, total // 100)
        edges_by_relation: dict[str, list[Edge]] = defaultdict(list)
        for edge in edges:
            edges_by_relation[edge.relation.value].append(edge)

        done = 0
        with self._client.session() as session:
            for relation, typed_edges in edges_by_relation.items():
                query = UPSERT_EDGE_BATCH_TEMPLATE.format(relation=relation)
                for chunk in self._chunked(typed_edges, batch_size):
                    rows = [
                        {
                            "source_id": edge.source_id,
                            "target_id": edge.target_id,
                            "properties": edge.properties,
                        }
                        for edge in chunk
                    ]
                    session.run(query, rows=rows)
                    done += len(chunk)
                    if progress_callback is not None and (done % step == 0 or done == total):
                        progress_callback(done, total)
