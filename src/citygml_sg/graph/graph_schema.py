"""Schema constraints for allowed relation triples."""

from __future__ import annotations

from citygml_sg.domain.enums import NodeType, RelationType

OBJECT_NODE_TYPES: set[NodeType] = {
    NodeType.BUILDING,
    NodeType.BUILDING_PART,
    NodeType.ROOM,
    NodeType.BOUNDARY_SURFACE,
    NodeType.OPENING,
    NodeType.BUILDING_FURNITURE,
}

ALLOWED_RELATIONS: set[tuple[NodeType, RelationType, NodeType]] = {
    (NodeType.BUILDING, RelationType.CONTAINS, NodeType.BUILDING_PART),
    (NodeType.BUILDING, RelationType.CONTAINS, NodeType.ROOM),
    (NodeType.BUILDING_PART, RelationType.CONTAINS, NodeType.ROOM),
    (NodeType.ROOM, RelationType.CONTAINS, NodeType.BUILDING_FURNITURE),
    (NodeType.ROOM, RelationType.BOUNDED_BY, NodeType.BOUNDARY_SURFACE),
    (NodeType.BOUNDARY_SURFACE, RelationType.HAS_OPENING, NodeType.OPENING),
    (NodeType.OPENING, RelationType.CONNECTS, NodeType.ROOM),
    (NodeType.BUILDING_FURNITURE, RelationType.ADJACENT_TO, NodeType.BOUNDARY_SURFACE),
    (NodeType.BUILDING_FURNITURE, RelationType.INSIDE, NodeType.ROOM),
    (NodeType.POLYGON, RelationType.HAS_RING, NodeType.LINEAR_RING),
    (NodeType.LINEAR_RING, RelationType.HAS_POS, NodeType.POSITION),
}

for object_type in OBJECT_NODE_TYPES:
    ALLOWED_RELATIONS.add((object_type, RelationType.HAS_GEOMETRY, NodeType.POLYGON))
