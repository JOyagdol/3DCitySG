"""Build room-retrieval scoring parameters from CLI and observed view graphs."""

from __future__ import annotations

from collections.abc import Sequence

from citygml_sg.ovg.validation import load_observed_view_graph, optional_non_negative_int


DEFAULT_ROOM_RETRIEVAL_PARAMS: dict[str, object] = {
    "furniture_keywords": ["storage", "fridge", "sofa", "table"],
    "source_keywords": ["sofa"],
    "target_keywords": ["table"],
    "floor_surface_types": ["FloorSurface", "GroundSurface"],
    "wall_surface_types": ["WallSurface", "ClosureSurface"],
    "min_doors": 1,
    "min_windows": 1,
    "furniture_keyword_weight": 3.0,
    "default_object_weight": 3.0,
    "door_weight": 1.0,
    "installation_weight": 1.5,
    "installation_keywords": ["column", "pillar", "기둥"],
    "installation_target_ids": [],
    "observed_objects": [],
    "observed_relations": [],
    "view_graph_path": None,
}

NON_FURNITURE_VIEW_CATEGORIES = {
    "door",
    "window",
    "opening",
    "floor",
    "floor_surface",
    "floorsurface",
    "wall",
    "wall_surface",
    "wallsurface",
    "boundarysurface",
    "boundary_surface",
    "buildinginstallation",
    "building_installation",
    "intbuildinginstallation",
    "int_building_installation",
    "installation",
    "column",
    "pillar",
    "기둥",
}

INSTALLATION_VIEW_CATEGORIES = {
    "buildinginstallation",
    "building_installation",
    "intbuildinginstallation",
    "int_building_installation",
    "installation",
    "column",
    "pillar",
    "기둥",
}


def build_room_retrieval_params(
    *,
    view_graph_path: str | None,
    limit: int | None,
    furniture_keywords: Sequence[str] | None,
    source_keywords: Sequence[str] | None,
    target_keywords: Sequence[str] | None,
) -> dict[str, object]:
    """Return Cypher parameters for room-localization retrieval."""
    params = dict(DEFAULT_ROOM_RETRIEVAL_PARAMS)
    observed_objects, observed_relations, observed_constraints, observed_query = load_observed_view_graph(
        view_graph_path
    )
    if view_graph_path is not None:
        params["view_graph_path"] = str(view_graph_path)
        params["observed_objects"] = observed_objects
        params["observed_relations"] = observed_relations
        params["observed_constraints"] = observed_constraints
        params["observed_query"] = observed_query
        room_constraints = observed_constraints.get("room", {})
        if isinstance(room_constraints, dict):
            min_doors = optional_non_negative_int(
                room_constraints.get("min_doors"),
                field="constraints.room.min_doors",
                path=str(view_graph_path),
            )
            min_windows = optional_non_negative_int(
                room_constraints.get("min_windows"),
                field="constraints.room.min_windows",
                path=str(view_graph_path),
            )
            candidate_limit = optional_non_negative_int(
                room_constraints.get("candidate_limit"),
                field="constraints.room.candidate_limit",
                path=str(view_graph_path),
            )
            if min_doors is not None:
                params["min_doors"] = min_doors
            if min_windows is not None:
                params["min_windows"] = min_windows
            if candidate_limit is not None:
                params["limit"] = max(1, candidate_limit)
        observed_furniture_keywords = sorted(
            {
                str(item["category"])
                for item in observed_objects
                if str(item["category"]) not in NON_FURNITURE_VIEW_CATEGORIES
            }
        )
        observed_installation_keywords = sorted(
            {
                str(item["category"])
                for item in observed_objects
                if str(item["category"]) in INSTALLATION_VIEW_CATEGORIES
            }
        )
        if observed_furniture_keywords:
            params["furniture_keywords"] = observed_furniture_keywords
        if observed_installation_keywords:
            params["installation_keywords"] = sorted(
                set(str(item) for item in params.get("installation_keywords", []))
                | set(observed_installation_keywords)
            )
        observed_installation_target_ids: set[str] = set()
        for item in observed_objects:
            if str(item["category"]) not in INSTALLATION_VIEW_CATEGORIES:
                continue
            for id_field in ("id", "gml_id", "target_id"):
                if item.get(id_field) is not None:
                    observed_installation_target_ids.add(str(item[id_field]))
            if isinstance(item.get("target_ids"), list):
                observed_installation_target_ids.update(str(target_id) for target_id in item["target_ids"])
            attributes = item.get("attributes")
            if isinstance(attributes, dict):
                for id_field in ("id", "gml_id", "target_id"):
                    if attributes.get(id_field) is not None:
                        observed_installation_target_ids.add(str(attributes[id_field]))
                if isinstance(attributes.get("target_ids"), list):
                    observed_installation_target_ids.update(
                        str(target_id) for target_id in attributes["target_ids"]
                    )
        if observed_installation_target_ids:
            params["installation_target_ids"] = sorted(
                set(str(item) for item in params.get("installation_target_ids", []))
                | observed_installation_target_ids
            )

    if furniture_keywords is not None:
        params["furniture_keywords"] = list(furniture_keywords)
    if source_keywords is not None:
        params["source_keywords"] = list(source_keywords)
    if target_keywords is not None:
        params["target_keywords"] = list(target_keywords)
    if limit is not None:
        params["limit"] = max(1, int(limit))
    else:
        params["limit"] = max(1, int(params.get("limit", 10)))
    return params
