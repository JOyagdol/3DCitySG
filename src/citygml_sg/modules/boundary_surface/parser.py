"""BoundarySurface parser module."""

from __future__ import annotations

from xml.etree.ElementTree import Element

from citygml_sg.utils.xml import find_first_lod, get_gml_id, local_name


def parse_boundary_surface_element(element: Element) -> dict:
    surface_type = local_name(element.tag)
    return {
        "gml_id": get_gml_id(element),
        "object_type": "BoundarySurface",
        "surface_type": surface_type,
        "lod": find_first_lod(element),
    }
