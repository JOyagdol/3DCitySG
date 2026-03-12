"""BuildingFurniture validation routines."""

from __future__ import annotations

from citygml_sg.domain.city_objects import BuildingFurniture


def validate_building_furniture(obj: BuildingFurniture) -> list[str]:
    errors: list[str] = []
    if not obj.gml_id:
        errors.append("missing gml_id")
    if obj.parent_room_id is None:
        errors.append("missing parent_room_id")
    return errors
