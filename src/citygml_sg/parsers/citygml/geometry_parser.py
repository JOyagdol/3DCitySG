"""Geometry extraction from CityGML XML."""

from __future__ import annotations

from xml.etree.ElementTree import Element


def parse_geometry(element: Element) -> dict:
    return {"tag": element.tag, "vertex_count": 0, "face_count": 0}
