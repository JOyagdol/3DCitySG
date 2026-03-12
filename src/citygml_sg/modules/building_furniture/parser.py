"""BuildingFurniture parser module."""

from __future__ import annotations

from xml.etree.ElementTree import Element

from citygml_sg.domain.city_objects import BuildingFurniture
from citygml_sg.utils.xml import find_first_lod, get_first_child_text, get_gml_id


def parse_building_furniture(raw: dict) -> BuildingFurniture:
    return BuildingFurniture(
        gml_id=str(raw.get("gml_id", "")),
        lod=str(raw.get("lod", "")) or None,
        klass=raw.get("class"),
        function=list(raw.get("function", [])),
        usage=list(raw.get("usage", [])),
        parent_room_id=raw.get("parent_room_id"),
    )


def parse_building_furniture_element(element: Element) -> dict:
    klass = get_first_child_text(element, "class")
    function = get_first_child_text(element, "function")
    usage = get_first_child_text(element, "usage")

    return {
        "gml_id": get_gml_id(element),
        "object_type": "BuildingFurniture",
        "class": klass,
        "function": [function] if function else [],
        "usage": [usage] if usage else [],
        "lod": find_first_lod(element),
    }
