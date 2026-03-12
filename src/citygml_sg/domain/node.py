"""Graph node model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from citygml_sg.domain.enums import NodeType


@dataclass(slots=True)
class Node:
    node_id: str
    node_type: NodeType
    properties: dict[str, Any] = field(default_factory=dict)
