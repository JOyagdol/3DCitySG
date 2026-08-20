"""Anchor records built from room signatures."""

from __future__ import annotations

from dataclasses import dataclass

from citygml_sg.world_graph.signatures import RoomSignature


@dataclass(frozen=True)
class RoomAnchor:
    """Stable retrieval anchor for one candidate Room."""

    signature: RoomSignature
    source: str = "world_graph"
    version: str = "room_anchor_v1"

    @property
    def anchor_id(self) -> str:
        return f"{self.version}:{self.signature.room_id}"

    def to_dict(self) -> dict[str, object]:
        return {
            "anchor_id": self.anchor_id,
            "source": self.source,
            "version": self.version,
            "signature": self.signature.to_dict(),
        }
