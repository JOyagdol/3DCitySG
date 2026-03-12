"""Base interface for relation extractors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from citygml_sg.domain.edge import Edge
from citygml_sg.domain.node import Node


class BaseRelationExtractor(ABC):
    @abstractmethod
    def extract(self, nodes: list[Node]) -> list[Edge]:
        raise NotImplementedError
