"""Domain enums for node and edge typing."""

from enum import Enum


class NodeType(str, Enum):
    BUILDING = "Building"
    BUILDING_PART = "BuildingPart"
    ROOM = "Room"
    BOUNDARY_SURFACE = "BoundarySurface"
    OPENING = "Opening"
    BUILDING_FURNITURE = "BuildingFurniture"


class RelationType(str, Enum):
    CONTAINS = "CONTAINS"
    INSIDE = "INSIDE"
    ADJACENT_TO = "ADJACENT_TO"
    TOUCHES = "TOUCHES"
    CONNECTS = "CONNECTS"
    BOUNDED_BY = "BOUNDED_BY"
