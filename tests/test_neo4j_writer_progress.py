"""Neo4j writer progress reporting tests."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from citygml_sg.domain.edge import Edge
from citygml_sg.domain.enums import NodeType, RelationType
from citygml_sg.domain.node import Node
from citygml_sg.storage.neo4j.writer import Neo4jWriter


class _FakeResult:
    def consume(self) -> None:
        return None


class _FakeSession:
    def run(self, query: str, **params: object) -> _FakeResult:
        return _FakeResult()


class _FakeClient:
    @contextmanager
    def session(self) -> Iterator[_FakeSession]:
        yield _FakeSession()


def test_node_progress_reports_when_batch_crosses_step_boundary() -> None:
    writer = Neo4jWriter(_FakeClient())  # type: ignore[arg-type]
    nodes = [Node(f"n{i}", NodeType.ROOM) for i in range(25)]
    calls: list[tuple[int, int]] = []

    writer.write_nodes(nodes, progress_callback=calls.append, progress_step=10, batch_size=6)

    assert calls == [(0, 25), (12, 25), (24, 25), (25, 25)]


def test_edge_progress_reports_when_batch_crosses_step_boundary() -> None:
    writer = Neo4jWriter(_FakeClient())  # type: ignore[arg-type]
    edges = [Edge(f"source{i}", f"target{i}", RelationType.CONTAINS) for i in range(25)]
    calls: list[tuple[int, int]] = []

    writer.write_edges(edges, progress_callback=calls.append, progress_step=10, batch_size=6)

    assert calls == [(0, 25), (12, 25), (24, 25), (25, 25)]
