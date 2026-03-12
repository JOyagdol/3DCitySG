"""Schema constraints for allowed relation triples."""

from __future__ import annotations

from citygml_sg.domain.enums import NodeType, RelationType

ALLOWED_RELATIONS: set[tuple[NodeType, RelationType, NodeType]] = {
    (NodeType.BUILDING, RelationType.CONTAINS, NodeType.BUILDING_PART),
    (NodeType.BUILDING, RelationType.CONTAINS, NodeType.ROOM),
    (NodeType.BUILDING_PART, RelationType.CONTAINS, NodeType.ROOM),
    (NodeType.ROOM, RelationType.CONTAINS, NodeType.BUILDING_FURNITURE),
    (NodeType.ROOM, RelationType.BOUNDED_BY, NodeType.BOUNDARY_SURFACE),
    (NodeType.OPENING, RelationType.CONNECTS, NodeType.ROOM),
    (NodeType.BUILDING_FURNITURE, RelationType.ADJACENT_TO, NodeType.BOUNDARY_SURFACE),
    (NodeType.BUILDING_FURNITURE, RelationType.INSIDE, NodeType.ROOM),
}
