"""Room-level feature signatures used by retrieval experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


CountMap = Mapping[str, int | float]
EvidenceMap = Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class RoomSignature:
    """Compact room feature vector derived from the CityGML world graph."""

    room_id: str
    room_name: str | None = None
    object_counts: CountMap = field(default_factory=dict)
    opening_counts: CountMap = field(default_factory=dict)
    relation_counts: CountMap = field(default_factory=dict)
    topology_counts: CountMap = field(default_factory=dict)
    evidence_ids: EvidenceMap = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "object_counts", dict(self.object_counts))
        object.__setattr__(self, "opening_counts", dict(self.opening_counts))
        object.__setattr__(self, "relation_counts", dict(self.relation_counts))
        object.__setattr__(self, "topology_counts", dict(self.topology_counts))
        object.__setattr__(
            self,
            "evidence_ids",
            {key: tuple(value) for key, value in self.evidence_ids.items()},
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "room_id": self.room_id,
            "room_name": self.room_name,
            "object_counts": dict(self.object_counts),
            "opening_counts": dict(self.opening_counts),
            "relation_counts": dict(self.relation_counts),
            "topology_counts": dict(self.topology_counts),
            "evidence_ids": {key: list(value) for key, value in self.evidence_ids.items()},
        }
