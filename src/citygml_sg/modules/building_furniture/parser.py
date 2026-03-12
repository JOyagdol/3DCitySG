"""BuildingFurniture parser module."""

from __future__ import annotations

from xml.etree.ElementTree import Element

from citygml_sg.domain.city_objects import BuildingFurniture
from citygml_sg.utils.xml import (
    get_direct_child_texts,
    get_first_direct_child_text,
    parse_common_object_properties,
)


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
    properties = parse_common_object_properties(element)
    klass = get_first_direct_child_text(element, "class")
    functions = get_direct_child_texts(element, "function")
    usages = get_direct_child_texts(element, "usage")

    properties["object_type"] = "BuildingFurniture"
    properties["class"] = klass
    properties["function"] = functions
    properties["usage"] = usages
    return properties
