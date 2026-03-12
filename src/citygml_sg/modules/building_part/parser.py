"""BuildingPart parser module."""

from __future__ import annotations

from xml.etree.ElementTree import Element

from citygml_sg.utils.xml import parse_common_object_properties


def parse_building_part_element(element: Element) -> dict:
    properties = parse_common_object_properties(element)
    properties["object_type"] = "BuildingPart"
    return properties
