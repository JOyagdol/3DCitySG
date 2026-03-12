"""Geometry rules for indoor furniture objects."""

from __future__ import annotations

from citygml_sg.domain.city_objects import BuildingFurniture


def is_valid_furniture_geometry(obj: BuildingFurniture) -> bool:
    return obj.geometry is not None
