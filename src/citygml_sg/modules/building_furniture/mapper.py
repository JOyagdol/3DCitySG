"""BuildingFurniture mapper to graph node properties."""

from __future__ import annotations

from citygml_sg.domain.city_objects import BuildingFurniture


def map_furniture_to_properties(obj: BuildingFurniture) -> dict:
    return {
        "gml_id": obj.gml_id,
        "object_type": obj.object_type,
        "class": obj.klass,
        "function": obj.function,
        "usage": obj.usage,
        "lod": obj.lod,
        "parent_room_id": obj.parent_room_id,
    }
