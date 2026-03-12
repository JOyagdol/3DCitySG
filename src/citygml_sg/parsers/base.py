"""Parser base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class RawRecord:
    record_id: str
    payload: dict


class BaseParser(ABC):
    @abstractmethod
    def parse(self, path: str) -> list[RawRecord]:
        raise NotImplementedError
