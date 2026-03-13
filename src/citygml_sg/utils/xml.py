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


def get_direct_children_by_local_name(element: Element, child_local_name: str) -> list[Element]:
    target = child_local_name.lower()
    return [child for child in list(element) if local_name(child.tag).lower() == target]


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
    def _set_primary_and_all(props: dict[str, object], key: str, values: list[str]) -> None:
        if not values:
            return
        props[key] = values[0]
        if len(values) > 1:
            props[f"{key}_all"] = values

    properties: dict[str, object] = {
        "gml_id": get_gml_id(element),
        "lod": find_first_lod(element),
    }

    names = get_direct_child_texts(element, "name")
    if names:
        properties["gml_name"] = names[0]
        properties["gml_name_all"] = names

    # Core/GML metadata fields (previously missing item #2)
    description = get_first_direct_child_text(element, "description")
    if description:
        properties["gml_description"] = description

    creation_date = get_first_direct_child_text(element, "creationDate")
    if creation_date:
        properties["creation_date"] = creation_date

    relative_to_terrain = get_first_direct_child_text(element, "relativeToTerrain")
    if relative_to_terrain:
        properties["relative_to_terrain"] = relative_to_terrain

    # Building semantic fields (previously missing item #1)
    class_elements = get_direct_children_by_local_name(element, "class")
    class_values = [child.text.strip() for child in class_elements if child.text and child.text.strip()]
    _set_primary_and_all(properties, "class_code", class_values)
    if class_elements and class_elements[0].get("codeSpace"):
        properties["class_code_space"] = class_elements[0].get("codeSpace")

    function_elements = get_direct_children_by_local_name(element, "function")
    function_values = [child.text.strip() for child in function_elements if child.text and child.text.strip()]
    _set_primary_and_all(properties, "function_code", function_values)
    if function_elements and function_elements[0].get("codeSpace"):
        properties["function_code_space"] = function_elements[0].get("codeSpace")

    usage_elements = get_direct_children_by_local_name(element, "usage")
    usage_values = [child.text.strip() for child in usage_elements if child.text and child.text.strip()]
    _set_primary_and_all(properties, "usage_code", usage_values)
    if usage_elements and usage_elements[0].get("codeSpace"):
        properties["usage_code_space"] = usage_elements[0].get("codeSpace")

    year_of_construction = get_first_direct_child_text(element, "yearOfConstruction")
    if year_of_construction:
        properties["year_of_construction"] = _parse_numeric(year_of_construction)

    roof_type_elements = get_direct_children_by_local_name(element, "roofType")
    roof_type_values = [child.text.strip() for child in roof_type_elements if child.text and child.text.strip()]
    _set_primary_and_all(properties, "roof_type_code", roof_type_values)
    if roof_type_elements and roof_type_elements[0].get("codeSpace"):
        properties["roof_type_code_space"] = roof_type_elements[0].get("codeSpace")

    measured_height_elements = get_direct_children_by_local_name(element, "measuredHeight")
    if measured_height_elements:
        raw_height = measured_height_elements[0].text.strip() if measured_height_elements[0].text else None
        if raw_height:
            properties["measured_height"] = _parse_numeric(raw_height)
        height_uom = measured_height_elements[0].get("uom")
        if height_uom:
            properties["measured_height_uom"] = height_uom

    storeys_above_ground = get_first_direct_child_text(element, "storeysAboveGround")
    if storeys_above_ground:
        properties["storeys_above_ground"] = _parse_numeric(storeys_above_ground)

    storeys_below_ground = get_first_direct_child_text(element, "storeysBelowGround")
    if storeys_below_ground:
        properties["storeys_below_ground"] = _parse_numeric(storeys_below_ground)

    properties.update(parse_generic_attributes(element))
    return properties
