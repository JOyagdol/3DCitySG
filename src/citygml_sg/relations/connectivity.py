"""Connectivity relation rules."""

from __future__ import annotations


def is_connected(door_room_pairs: list[tuple[str, str]], left_room_id: str, right_room_id: str) -> bool:
    pair_set = {tuple(sorted(pair)) for pair in door_room_pairs}
    return tuple(sorted((left_room_id, right_room_id))) in pair_set
