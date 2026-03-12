"""Graph edge model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from citygml_sg.domain.enums import RelationType


@dataclass(slots=True)
class Edge:
    source_id: str
    target_id: str
    relation: RelationType
    properties: dict[str, Any] = field(default_factory=dict)
