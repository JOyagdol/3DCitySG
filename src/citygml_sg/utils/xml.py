"""XML utility helpers."""

from __future__ import annotations

import re
from xml.etree.ElementTree import Element

GML_ID_URIS = ("http://www.opengis.net/gml", "http://www.opengis.net/gml/3.2")
GENERIC_ATTRIBUTE_TAGS = {
    "stringAttribute",
    "intAttribute",
    "doubleAttribute",
    "measureAttribute",
    "uriAttribute",
    "dateAttribute",
}


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


def _sanitize_property_key(name: str) -> str:
    key = re.sub(r"[^0-9A-Za-z_]+", "_", name.strip())
    key = re.sub(r"_+", "_", key).strip("_").lower()
    return key or "unnamed"


def _parse_numeric(text: str) -> int | float | str:
    stripped = text.strip()
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        return stripped


def get_direct_child_texts(element: Element, child_local_name: str) -> list[str]:
    values: list[str] = []
    target = child_local_name.lower()
    for child in list(element):
        if local_name(child.tag).lower() != target:
            continue
        if child.text and child.text.strip():
            values.append(child.text.strip())
    return values


def get_first_direct_child_text(element: Element, child_local_name: str) -> str | None:
    values = get_direct_child_texts(element, child_local_name)
    return values[0] if values else None


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


def parse_generic_attributes(element: Element) -> dict:
    properties: dict[str, object] = {}

    for child in list(element):
        tag = local_name(child.tag)
        if tag not in GENERIC_ATTRIBUTE_TAGS:
            continue

        attr_name = child.get("name")
        if not attr_name:
            continue

        value_element: Element | None = None
        for candidate in list(child):
            if local_name(candidate.tag).lower() == "value":
                value_element = candidate
                break
        if value_element is None:
            continue

        raw_value = value_element.text.strip() if value_element.text else None
        if not raw_value:
            continue

        key = f"attr_{_sanitize_property_key(attr_name)}"
        if tag in {"intAttribute", "doubleAttribute", "measureAttribute"}:
            properties[key] = _parse_numeric(raw_value)
        else:
            properties[key] = raw_value

        if tag == "measureAttribute":
            uom = value_element.get("uom")
            if uom:
                properties[f"{key}_uom"] = uom

    return properties


def parse_common_object_properties(element: Element) -> dict:
    properties: dict[str, object] = {
        "gml_id": get_gml_id(element),
        "lod": find_first_lod(element),
    }

    names = get_direct_child_texts(element, "name")
    if names:
        properties["gml_name"] = names[0]
        properties["gml_name_all"] = names

    properties.update(parse_generic_attributes(element))
    return properties
