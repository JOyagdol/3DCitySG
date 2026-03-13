"""Address parser module."""

from __future__ import annotations

from xml.etree.ElementTree import Element

from citygml_sg.utils.xml import get_first_child_text, parse_common_object_properties


def parse_address_element(element: Element) -> dict:
    properties = parse_common_object_properties(element)

    locality = get_first_child_text(element, "LocalityName")
    street_name = get_first_child_text(element, "ThoroughfareName")
    street_number = get_first_child_text(element, "ThoroughfareNumber")
    postal_code = get_first_child_text(element, "PostalCodeNumber")

    if locality:
        properties["address_locality"] = locality
    if street_name:
        properties["address_street_name"] = street_name
    if street_number:
        properties["address_street_number"] = street_number
    if postal_code:
        properties["address_postal_code"] = postal_code

    properties["object_type"] = "Address"
    return properties

