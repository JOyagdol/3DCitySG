"""BoundarySurface parser module."""

from __future__ import annotations

from xml.etree.ElementTree import Element

from citygml_sg.utils.xml import local_name, parse_common_object_properties


def parse_boundary_surface_element(element: Element) -> dict:
    properties = parse_common_object_properties(element)
    properties["object_type"] = "BoundarySurface"
    properties["surface_type"] = local_name(element.tag)
    return properties
