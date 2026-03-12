"""Indoor relation composition rules."""

from __future__ import annotations

from citygml_sg.domain.bbox import BBox
from citygml_sg.relations.adjacency import is_adjacent
from citygml_sg.relations.containment import is_contained


def infer_room_furniture_relations(room_bbox: BBox | None, furniture_bbox: BBox | None) -> dict[str, bool]:
    return {
        "inside": is_contained(furniture_bbox, room_bbox),
        "adjacent": is_adjacent(room_bbox, furniture_bbox),
    }
