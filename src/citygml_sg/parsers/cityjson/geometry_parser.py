"""CityJSON geometry parser placeholder."""


def parse_cityjson_geometry(cityjson_object: dict) -> dict:
    return {"type": cityjson_object.get("type", "Unknown"), "geometry": cityjson_object.get("geometry", [])}
