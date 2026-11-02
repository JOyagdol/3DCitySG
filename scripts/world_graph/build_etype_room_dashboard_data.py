"""Build lightweight E-TYPE room dashboard data from graph JSON.

The import artifact is large because it contains polygon/ring/position nodes.
This script streams the JSON arrays written by ``write_graph_json_stream`` and
extracts only Building, Room, and BuildingFurniture geometry needed by the local
viewer.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_INPUT = Path("data/output/e_type_import.json")
DEFAULT_OUTPUT = Path("web/etype_room_dashboard/etype_room_dashboard_data.json")

TARGET_NODE_TYPES = {"Building", "Room", "BuildingFurniture"}
POSITION_NODE_TYPE = "Position"


def _iter_json_array_objects(path: Path, section_name: str) -> Iterable[dict[str, object]]:
    marker = f'"{section_name}": ['
    in_section = False

    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not in_section:
                if marker in line:
                    in_section = True
                continue

            text = line.strip()
            if not text:
                continue
            if text in {"]", "],"}:
                break
            if text.endswith(","):
                text = text[:-1]
            if not text:
                continue
            yield json.loads(text)


def _edge_value(edge: dict[str, object], key: str) -> str:
    value = edge.get(key)
    return str(value) if value is not None else ""


def _node_id(node: dict[str, object]) -> str:
    return str(node.get("id") or "")


def _node_type(node: dict[str, object]) -> str:
    return str(node.get("type") or "")


def _properties(node: dict[str, object]) -> dict[str, object]:
    props = node.get("properties")
    return props if isinstance(props, dict) else {}


def _display_name(props: dict[str, object], node_id: str) -> str:
    for key in (
        "gml_name",
        "attr_ifc_longname",
        "attr_identity_data_name",
        "attr_identity_data_type_name",
        "attr_ifc_object_type",
    ):
        value = props.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return node_id


def _short_id(value: str, *, prefix: int = 8, suffix: int = 6) -> str:
    if len(value) <= prefix + suffix + 3:
        return value
    return f"{value[:prefix]}...{value[-suffix:]}"


def _infer_level(name: str, props: dict[str, object]) -> str:
    for key in ("attr_constraints_level", "level", "storey", "floor"):
        value = props.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    match = re.search(r"\bE([0-9])", name)
    if match:
        return f"{match.group(1)}F"
    return "unknown"


def _bbox(points: list[tuple[float, float, float]]) -> dict[str, float] | None:
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    zs = [point[2] for point in points]
    return {
        "min_x": min(xs),
        "min_y": min(ys),
        "min_z": min(zs),
        "max_x": max(xs),
        "max_y": max(ys),
        "max_z": max(zs),
    }


def _bbox_center(bbox: dict[str, float]) -> dict[str, float]:
    return {
        "x": (bbox["min_x"] + bbox["max_x"]) / 2.0,
        "y": (bbox["min_y"] + bbox["max_y"]) / 2.0,
        "z": (bbox["min_z"] + bbox["max_z"]) / 2.0,
    }


def _bbox_size(bbox: dict[str, float]) -> dict[str, float]:
    return {
        "x": bbox["max_x"] - bbox["min_x"],
        "y": bbox["max_y"] - bbox["min_y"],
        "z": bbox["max_z"] - bbox["min_z"],
    }


def _footprint_from_bbox(bbox: dict[str, float]) -> list[list[float]]:
    return [
        [bbox["min_x"], bbox["min_y"]],
        [bbox["max_x"], bbox["min_y"]],
        [bbox["max_x"], bbox["max_y"]],
        [bbox["min_x"], bbox["max_y"]],
    ]


def _bbox_area_xy(bbox: dict[str, float]) -> float:
    return max(0.0, bbox["max_x"] - bbox["min_x"]) * max(0.0, bbox["max_y"] - bbox["min_y"])


def _obb_xy_pca(points: list[tuple[float, float, float]]) -> dict[str, object] | None:
    if len(points) < 3:
        return None

    mean_x = sum(point[0] for point in points) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    cxx = sum((point[0] - mean_x) ** 2 for point in points) / len(points)
    cyy = sum((point[1] - mean_y) ** 2 for point in points) / len(points)
    cxy = sum((point[0] - mean_x) * (point[1] - mean_y) for point in points) / len(points)

    if cxx + cyy <= 1.0e-12:
        return None

    angle = 0.5 * math.atan2(2.0 * cxy, cxx - cyy)
    ux = math.cos(angle)
    uy = math.sin(angle)
    vx = -uy
    vy = ux

    projected_u = [point[0] * ux + point[1] * uy for point in points]
    projected_v = [point[0] * vx + point[1] * vy for point in points]
    min_u = min(projected_u)
    max_u = max(projected_u)
    min_v = min(projected_v)
    max_v = max(projected_v)
    min_z = min(point[2] for point in points)
    max_z = max(point[2] for point in points)

    size_u = max_u - min_u
    size_v = max_v - min_v
    size_z = max_z - min_z
    if max(size_u, size_v, size_z) <= 1.0e-9:
        return None

    center_u = (min_u + max_u) / 2.0
    center_v = (min_v + max_v) / 2.0
    center_z = (min_z + max_z) / 2.0
    center_x = center_u * ux + center_v * vx
    center_y = center_u * uy + center_v * vy

    def corner(u_value: float, v_value: float, z_value: float) -> list[float]:
        return [
            u_value * ux + v_value * vx,
            u_value * uy + v_value * vy,
            z_value,
        ]

    corners = [
        corner(min_u, min_v, min_z),
        corner(max_u, min_v, min_z),
        corner(max_u, max_v, min_z),
        corner(min_u, max_v, min_z),
        corner(min_u, min_v, max_z),
        corner(max_u, min_v, max_z),
        corner(max_u, max_v, max_z),
        corner(min_u, max_v, max_z),
    ]

    return {
        "method": "xy_pca_z_extent_v1",
        "center": {"x": center_x, "y": center_y, "z": center_z},
        "axes": [
            {"x": ux, "y": uy, "z": 0.0},
            {"x": vx, "y": vy, "z": 0.0},
            {"x": 0.0, "y": 0.0, "z": 1.0},
        ],
        "half_sizes": {"x": size_u / 2.0, "y": size_v / 2.0, "z": size_z / 2.0},
        "angle_rad": angle,
        "corners": corners,
    }


def _cross_2d(
    origin: tuple[float, float],
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    return (first[0] - origin[0]) * (second[1] - origin[1]) - (
        first[1] - origin[1]
    ) * (second[0] - origin[0])


def _convex_hull_xy(points: list[tuple[float, float, float]]) -> list[list[float]] | None:
    unique_points = sorted({(round(point[0], 6), round(point[1], 6)) for point in points})
    if len(unique_points) < 3:
        return None

    lower: list[tuple[float, float]] = []
    for point in unique_points:
        while len(lower) >= 2 and _cross_2d(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(unique_points):
        while len(upper) >= 2 and _cross_2d(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return None
    return [[point[0], point[1]] for point in hull]


def _outline_xy_hull(points: list[tuple[float, float, float]]) -> dict[str, object] | None:
    if len(points) < 3:
        return None
    footprint = _convex_hull_xy(points)
    if footprint is None:
        return None

    min_z = min(point[2] for point in points)
    max_z = max(point[2] for point in points)
    if max_z - min_z <= 1.0e-9:
        return None

    return {
        "method": "xy_convex_hull_z_extent_v1",
        "footprint": footprint,
        "min_z": min_z,
        "max_z": max_z,
        "vertex_count": len(footprint),
    }


def _finite_bounds(items: list[dict[str, object]]) -> dict[str, float]:
    bounds = {
        "min_x": math.inf,
        "min_y": math.inf,
        "min_z": math.inf,
        "max_x": -math.inf,
        "max_y": -math.inf,
        "max_z": -math.inf,
    }
    for item in items:
        bbox = item.get("bbox")
        if not isinstance(bbox, dict):
            continue
        for key in bounds:
            value = bbox.get(key)
            if not isinstance(value, (int, float)):
                continue
            if key.startswith("min_"):
                bounds[key] = min(bounds[key], float(value))
            else:
                bounds[key] = max(bounds[key], float(value))

    if any(not math.isfinite(value) for value in bounds.values()):
        return {
            "min_x": 0.0,
            "min_y": 0.0,
            "min_z": 0.0,
            "max_x": 1.0,
            "max_y": 1.0,
            "max_z": 1.0,
        }
    return bounds


def _geometry_points_for_targets(
    graph_json_path: Path,
    target_node_ids: set[str],
    detailed_polygon_node_ids: set[str],
) -> tuple[
    dict[str, list[tuple[float, float, float]]],
    dict[str, list[dict[str, object]]],
    dict[str, set[str]],
    dict[str, set[str]],
]:
    object_to_polygons: dict[str, list[str]] = defaultdict(list)
    furniture_to_rooms: dict[str, set[str]] = defaultdict(set)
    room_to_furniture: dict[str, set[str]] = defaultdict(set)

    for edge in _iter_json_array_objects(graph_json_path, "edges"):
        relation = _edge_value(edge, "relation")
        source_id = _edge_value(edge, "source_id")
        target_id = _edge_value(edge, "target_id")
        if relation == "HAS_GEOMETRY" and source_id in target_node_ids:
            object_to_polygons[source_id].append(target_id)
        elif relation == "INSIDE" and source_id in target_node_ids:
            furniture_to_rooms[source_id].add(target_id)
        elif relation == "INTERIOR_FURNITURE" and target_id in target_node_ids:
            room_to_furniture[source_id].add(target_id)
            furniture_to_rooms[target_id].add(source_id)

    polygon_ids = {polygon_id for polygon_ids in object_to_polygons.values() for polygon_id in polygon_ids}
    polygon_to_rings: dict[str, list[str]] = defaultdict(list)
    for edge in _iter_json_array_objects(graph_json_path, "edges"):
        if _edge_value(edge, "relation") != "HAS_RING":
            continue
        source_id = _edge_value(edge, "source_id")
        if source_id in polygon_ids:
            polygon_to_rings[source_id].append(_edge_value(edge, "target_id"))

    ring_ids = {ring_id for ring_list in polygon_to_rings.values() for ring_id in ring_list}
    ring_to_positions: dict[str, list[str]] = defaultdict(list)
    for edge in _iter_json_array_objects(graph_json_path, "edges"):
        if _edge_value(edge, "relation") != "HAS_POS":
            continue
        source_id = _edge_value(edge, "source_id")
        if source_id in ring_ids:
            ring_to_positions[source_id].append(_edge_value(edge, "target_id"))

    position_ids = {pos_id for pos_ids in ring_to_positions.values() for pos_id in pos_ids}
    positions: dict[str, tuple[float, float, float]] = {}
    for node in _iter_json_array_objects(graph_json_path, "nodes"):
        if _node_type(node) != POSITION_NODE_TYPE:
            continue
        node_id = _node_id(node)
        if node_id not in position_ids:
            continue
        props = _properties(node)
        x = props.get("x")
        y = props.get("y")
        z = props.get("z")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and isinstance(z, (int, float)):
            positions[node_id] = (float(x), float(y), float(z))

    points_by_object: dict[str, list[tuple[float, float, float]]] = {}
    polygons_by_object: dict[str, list[dict[str, object]]] = {}
    for object_id, polygon_list in object_to_polygons.items():
        points: list[tuple[float, float, float]] = []
        polygons: list[dict[str, object]] = []
        keep_polygon_detail = object_id in detailed_polygon_node_ids
        for polygon_id in polygon_list:
            polygon_rings: list[list[list[float]]] = []
            for ring_id in polygon_to_rings.get(polygon_id, []):
                ring_points: list[list[float]] = []
                for pos_id in ring_to_positions.get(ring_id, []):
                    point = positions.get(pos_id)
                    if point is not None:
                        points.append(point)
                        if keep_polygon_detail:
                            ring_points.append([point[0], point[1], point[2]])
                if keep_polygon_detail and len(ring_points) >= 3:
                    polygon_rings.append(ring_points)
            if keep_polygon_detail and polygon_rings:
                polygons.append({"id": polygon_id, "rings": polygon_rings})
        points_by_object[object_id] = points
        if keep_polygon_detail:
            polygons_by_object[object_id] = polygons

    return points_by_object, polygons_by_object, furniture_to_rooms, room_to_furniture


def build_dashboard_data(graph_json_path: Path) -> dict[str, object]:
    target_nodes: dict[str, dict[str, object]] = {}
    for node in _iter_json_array_objects(graph_json_path, "nodes"):
        node_type = _node_type(node)
        if node_type in TARGET_NODE_TYPES:
            target_nodes[_node_id(node)] = node

    (
        points_by_object,
        polygons_by_object,
        furniture_room_candidates,
        room_furniture_candidates,
    ) = _geometry_points_for_targets(
        graph_json_path,
        set(target_nodes),
        {node_id for node_id, node in target_nodes.items() if _node_type(node) == "Room"},
    )
    furniture_to_rooms = {
        furniture_id: sorted(room_ids)[0]
        for furniture_id, room_ids in furniture_room_candidates.items()
        if room_ids
    }
    room_to_furniture: dict[str, list[str]] = defaultdict(list)
    for room_id, furniture_ids in room_furniture_candidates.items():
        room_to_furniture[room_id].extend(sorted(furniture_ids))
    for furniture_id, room_id in furniture_to_rooms.items():
        room_to_furniture[room_id].append(furniture_id)

    buildings: list[dict[str, object]] = []
    rooms: list[dict[str, object]] = []
    furniture: list[dict[str, object]] = []
    skipped_without_geometry: list[dict[str, str]] = []

    for node_id, node in target_nodes.items():
        props = _properties(node)
        bbox = _bbox(points_by_object.get(node_id, []))
        if bbox is None:
            skipped_without_geometry.append({"id": node_id, "type": _node_type(node)})
            continue

        name = _display_name(props, node_id)
        item = {
            "id": node_id,
            "gml_id": str(props.get("gml_id") or node_id),
            "short_id": _short_id(str(props.get("gml_id") or node_id)),
            "type": _node_type(node),
            "name": name,
            "level": _infer_level(name, props),
            "bbox": bbox,
            "center": _bbox_center(bbox),
            "size": _bbox_size(bbox),
            "area_xy": _bbox_area_xy(bbox),
            "footprint": _footprint_from_bbox(bbox),
            "ifc_tag": str(props.get("attr_ifc_tag") or ""),
            "ifc_object_type": str(props.get("attr_ifc_object_type") or ""),
        }

        node_type = _node_type(node)
        if node_type == "Building":
            buildings.append(item)
        elif node_type == "Room":
            room_polygons = polygons_by_object.get(node_id, [])
            item["polygon_count"] = len(room_polygons)
            item["polygons"] = room_polygons
            item["furniture_ids"] = sorted(set(room_to_furniture.get(node_id, [])))
            rooms.append(item)
        else:
            object_points = points_by_object.get(node_id, [])
            outline = _outline_xy_hull(object_points)
            obb = _obb_xy_pca(object_points)
            if outline is not None:
                item["outline"] = outline
                item["geometry_mode"] = "outline_xy_hull"
            if obb is not None:
                item["obb"] = obb
                if outline is None:
                    item["geometry_mode"] = "obb_xy_pca"
            if outline is None and obb is None:
                item["geometry_mode"] = "bbox_simplified"
            room_id = furniture_to_rooms.get(node_id)
            item["room_id"] = room_id or ""
            furniture.append(item)

    room_name_by_id = {str(room["id"]): str(room["name"]) for room in rooms}
    room_level_by_id = {str(room["id"]): str(room["level"]) for room in rooms}
    for item in furniture:
        room_id = str(item.get("room_id") or "")
        item["room_name"] = room_name_by_id.get(room_id, "")
        item["level"] = room_level_by_id.get(room_id, str(item.get("level") or "unknown"))

    buildings.sort(key=lambda item: (str(item["name"]), str(item["id"])))
    rooms.sort(key=lambda item: (str(item["level"]), str(item["name"]), str(item["id"])))
    furniture.sort(key=lambda item: (str(item.get("room_name") or ""), str(item["name"]), str(item["id"])))

    bounds = _finite_bounds(buildings + rooms + furniture)
    levels = sorted({str(room["level"]) for room in rooms})

    return {
        "metadata": {
            "source_graph_json": str(graph_json_path),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "geometry_policy": "room_polygon_faces_and_furniture_xy_hull_outline_with_obb_fallback_from_HAS_GEOMETRY_HAS_RING_HAS_POS",
            "viewer_scope": "Building, Room, and BuildingFurniture only",
        },
        "summary": {
            "building_count": len(buildings),
            "room_count": len(rooms),
            "furniture_count": len(furniture),
            "levels": levels,
            "skipped_without_geometry_count": len(skipped_without_geometry),
        },
        "bounds": bounds,
        "buildings": buildings,
        "rooms": rooms,
        "furniture": furniture,
        "skipped_without_geometry": skipped_without_geometry,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Graph JSON artifact. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Dashboard data JSON path. Default: {DEFAULT_OUTPUT}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        raise FileNotFoundError(f"Input graph JSON not found: {args.input}")

    data = build_dashboard_data(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = data["summary"]
    print(f"Dashboard data written: {args.output}")
    print(
        "buildings={building_count} rooms={room_count} furniture={furniture_count} levels={levels}".format(
            building_count=summary["building_count"],
            room_count=summary["room_count"],
            furniture_count=summary["furniture_count"],
            levels=", ".join(summary["levels"]) if summary["levels"] else "none",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
