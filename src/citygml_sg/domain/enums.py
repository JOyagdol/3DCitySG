"""Domain enums for node and edge typing."""

from enum import Enum


class NodeType(str, Enum):
    BUILDING = "Building"
    BUILDING_PART = "BuildingPart"
    ROOM = "Room"
    BOUNDARY_SURFACE = "BoundarySurface"
    OPENING = "Opening"
    BUILDING_FURNITURE = "BuildingFurniture"
    POLYGON = "Polygon"
    LINEAR_RING = "LinearRing"
    POSITION = "Position"


class RelationType(str, Enum):
    CONTAINS = "CONTAINS"
    INSIDE = "INSIDE"
    ADJACENT_TO = "ADJACENT_TO"
    TOUCHES = "TOUCHES"
    CONNECTS = "CONNECTS"
    BOUNDED_BY = "BOUNDED_BY"
    HAS_OPENING = "HAS_OPENING"
    HAS_GEOMETRY = "HAS_GEOMETRY"
    HAS_RING = "HAS_RING"
    HAS_POS = "HAS_POS"
