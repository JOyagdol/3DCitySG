"""Neo4j client wrapper."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from neo4j import GraphDatabase


class Neo4jClient:
    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j") -> None:
        self._driver = GraphDatabase.driver(uri, auth=(username, password))
        self._database = database

    def close(self) -> None:
        self._driver.close()

    @contextmanager
    def session(self) -> Iterator:
        with self._driver.session(database=self._database) as session:
            yield session
