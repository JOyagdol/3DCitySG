"""Resolve xlink references in CityGML documents."""


def resolve_xlink(href: str) -> str:
    return href.lstrip("#")
