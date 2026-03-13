"""BuildingInstallation parser module."""

from __future__ import annotations

from xml.etree.ElementTree import Element

from citygml_sg.utils.xml import local_name, parse_common_object_properties


def parse_building_installation_element(element: Element) -> dict:
    properties = parse_common_object_properties(element)
    tag_name = local_name(element.tag)
    properties["object_type"] = tag_name
    properties["installation_type"] = tag_name
    return properties

