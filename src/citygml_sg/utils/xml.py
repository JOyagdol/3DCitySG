"""XML utility helpers."""

from __future__ import annotations

from xml.etree.ElementTree import Element

GML_ID_URIS = ("http://www.opengis.net/gml", "http://www.opengis.net/gml/3.2")


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def get_gml_id(element: Element) -> str | None:
    for uri in GML_ID_URIS:
        value = element.get(f"{{{uri}}}id")
        if value:
            return value
    return element.get("id")


def get_first_child_text(element: Element, child_local_name: str) -> str | None:
    target = child_local_name.lower()
    for child in element.iter():
        if local_name(child.tag).lower() == target:
            text = child.text.strip() if child.text else None
            if text:
                return text
    return None


def find_first_lod(element: Element) -> str | None:
    for child in element.iter():
        lname = local_name(child.tag).lower()
        if lname.startswith("lod"):
            return lname.replace("lod", "LoD")
    return None
