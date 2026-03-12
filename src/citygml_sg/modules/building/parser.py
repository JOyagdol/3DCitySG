"""Building parser module."""

from __future__ import annotations

from xml.etree.ElementTree import Element

from citygml_sg.utils.xml import find_first_lod, get_gml_id


def parse_building_element(element: Element) -> dict:
    return {
        "gml_id": get_gml_id(element),
        "object_type": "Building",
        "lod": find_first_lod(element),
    }
