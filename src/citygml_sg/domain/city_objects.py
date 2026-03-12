"""City object hierarchy including BuildingFurniture."""

from __future__ import annotations

from dataclasses import dataclass, field

from citygml_sg.domain.bbox import BBox
from citygml_sg.domain.geometry import Point3D, PolygonMesh


@dataclass(slots=True)
class CityObject:
    gml_id: str
    object_type: str
    lod: str | None = None
    geometry: PolygonMesh | None = None
    bbox: BBox | None = None
    centroid: Point3D | None = None
    parent_id: str | None = None


@dataclass(slots=True)
class Building(CityObject):
    object_type: str = "Building"


@dataclass(slots=True)
class BuildingPart(CityObject):
    object_type: str = "BuildingPart"


@dataclass(slots=True)
class Room(CityObject):
    object_type: str = "Room"


@dataclass(slots=True)
class BoundarySurface(CityObject):
    object_type: str = "BoundarySurface"
    surface_type: str = "BoundarySurface"


@dataclass(slots=True)
class Opening(CityObject):
    object_type: str = "Opening"
    opening_type: str = "Opening"


@dataclass(slots=True)
class BuildingFurniture(CityObject):
    object_type: str = "BuildingFurniture"
    klass: str | None = None
    function: list[str] = field(default_factory=list)
    usage: list[str] = field(default_factory=list)
    parent_room_id: str | None = None
