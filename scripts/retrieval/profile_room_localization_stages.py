"""Profile room-localization query timing at coarse retrieval stages.

The main room-localization script records one query+fetch time per scenario.
This helper keeps that full measurement and adds independent component probes
so slow feature groups can be identified before moving to precomputed room
signatures.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from citygml_sg.config.settings import load_project_config
from citygml_sg.retrieval.query_generator import SCENARIOS
from citygml_sg.retrieval.reporting import to_json_safe
from citygml_sg.storage.neo4j.client import Neo4jClient
from citygml_sg.utils.io import ensure_dir
from room_localization_queries import _build_params


FURNITURE_CATEGORY_CASE = """
CASE
  WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'sink' THEN 'sink'
  WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'counter' THEN 'counter'
  WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'cabinet' THEN 'cabinet'
  WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'storage' THEN 'storage'
  WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'fridge'
    OR toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'freezer'
    OR toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'refrigerator' THEN 'fridge'
  WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'sofa' THEN 'sofa'
  WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'tv'
    OR toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'television'
    OR toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'display' THEN 'tv'
  WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'table' THEN 'table'
  ELSE null
END
""".strip()


COMPONENT_PROBES: dict[str, list[dict[str, str]]] = {
    "combined_room_score": [
        {
            "id": "candidate_rooms",
            "description": "Scan candidate Room nodes.",
            "query": "MATCH (r:Room) RETURN count(r) AS room_count",
        },
        {
            "id": "object_keyword_features",
            "description": "Collect room furniture and match observed furniture categories.",
            "query": f"""
MATCH (r:Room)
OPTIONAL MATCH (f:BuildingFurniture)-[:INSIDE]->(r)
WITH r,
     [f IN collect(DISTINCT f) WHERE f IS NOT NULL |
       {{id: f.id, category: {FURNITURE_CATEGORY_CASE}}}
     ] AS categorized_objects
WITH r, [obj IN categorized_objects WHERE obj.category IN $furniture_keywords] AS matched_objects
RETURN count(r) AS room_count,
       sum(size(matched_objects)) AS matched_object_total,
       count(CASE WHEN size(matched_objects) > 0 THEN 1 END) AS matched_room_count
""",
        },
        {
            "id": "door_connectivity_features",
            "description": "Count Door-to-Room CONNECTS evidence.",
            "query": """
MATCH (r:Room)
OPTIONAL MATCH (d:Opening {opening_type: 'Door'})-[:CONNECTS]->(r)
WITH r, count(DISTINCT d) AS door_count
RETURN count(r) AS room_count,
       sum(door_count) AS door_link_total,
       count(CASE WHEN door_count >= $min_doors THEN 1 END) AS room_with_min_doors
""",
        },
        {
            "id": "floor_attachment_features",
            "description": "Check floor ATTACHED_TO evidence for matched objects.",
            "query": f"""
MATCH (r:Room)
OPTIONAL MATCH (f:BuildingFurniture)-[:INSIDE]->(r)
WITH r,
     [f IN collect(DISTINCT f) WHERE f IS NOT NULL |
       {{id: f.id, category: {FURNITURE_CATEGORY_CASE}}}
     ] AS categorized_objects
WITH r, [obj IN categorized_objects WHERE obj.category IN $furniture_keywords] AS matched_objects
OPTIONAL MATCH (mf:BuildingFurniture)-[:ATTACHED_TO]->(bs:BoundarySurface)
WHERE mf.id IN [obj IN matched_objects | obj.id]
  AND bs.surface_type IN $floor_surface_types
RETURN count(DISTINCT r) AS room_count,
       count(DISTINCT mf) AS floor_attached_object_count
""",
        },
        {
            "id": "furniture_pair_relation_features",
            "description": "Count spatial relations among matched furniture pairs.",
            "query": f"""
MATCH (r:Room)
OPTIONAL MATCH (f:BuildingFurniture)-[:INSIDE]->(r)
WITH r,
     [f IN collect(DISTINCT f) WHERE f IS NOT NULL |
       {{id: f.id, category: {FURNITURE_CATEGORY_CASE}}}
     ] AS categorized_objects
WITH r, [obj IN categorized_objects WHERE obj.category IN $furniture_keywords] AS matched_objects
MATCH (a:BuildingFurniture)-[:INSIDE]->(r)
MATCH (b:BuildingFurniture)-[:INSIDE]->(r)
WHERE a.id < b.id
  AND a.id IN [obj IN matched_objects | obj.id]
  AND b.id IN [obj IN matched_objects | obj.id]
MATCH (a)-[rel:ADJACENT_TO|TOUCHES|INTERSECTS|ABOVE|BELOW]-(b)
RETURN count(DISTINCT r) AS room_count,
       count(DISTINCT a.id + '|' + b.id) AS furniture_relation_pair_count
""",
        },
    ],
    "opening_boundary_room_score": [
        {
            "id": "candidate_rooms",
            "description": "Scan candidate Room nodes.",
            "query": "MATCH (r:Room) RETURN count(r) AS room_count",
        },
        {
            "id": "door_connectivity_features",
            "description": "Count Door-to-Room CONNECTS evidence.",
            "query": """
MATCH (r:Room)
OPTIONAL MATCH (d:Opening {opening_type: 'Door'})-[:CONNECTS]->(r)
WITH r, count(DISTINCT d) AS door_count
RETURN count(r) AS room_count,
       sum(door_count) AS door_link_total,
       count(CASE WHEN door_count >= $min_doors THEN 1 END) AS room_with_min_doors
""",
        },
        {
            "id": "window_features",
            "description": "Collect direct and host-wall fallback Window evidence.",
            "query": """
MATCH (r:Room)
OPTIONAL MATCH (r)-[:BOUNDED_BY]->(bs:BoundarySurface)-[:HAS_OPENING]->(w:Opening {opening_type: 'Window'})
WITH r, collect(DISTINCT w.id) AS direct_window_ids
OPTIONAL MATCH (r)<-[:CONNECTS]-(connected_opening:Opening)-[:HOSTED_BY]->(host_wall:BoundarySurface)<-[:HOSTED_BY]-(hosted_window:Opening {opening_type: 'Window'})
WITH r, direct_window_ids, collect(DISTINCT hosted_window.id) AS hosted_window_ids
WITH r, direct_window_ids + hosted_window_ids AS raw_window_ids
WITH r, [id IN raw_window_ids WHERE id IS NOT NULL] AS window_ids
RETURN count(r) AS room_count,
       sum(size(window_ids)) AS raw_window_evidence_total,
       count(CASE WHEN size(window_ids) >= $min_windows THEN 1 END) AS room_with_min_windows
""",
        },
        {
            "id": "wall_surface_features",
            "description": "Collect direct and host-wall fallback WallSurface evidence.",
            "query": """
MATCH (r:Room)
OPTIONAL MATCH (r)-[:BOUNDED_BY]->(wall:BoundarySurface)
WHERE wall.surface_type IN $wall_surface_types
WITH r, collect(DISTINCT wall.id) AS direct_wall_ids
OPTIONAL MATCH (r)<-[:CONNECTS]-(connected_opening:Opening)-[:HOSTED_BY]->(host_wall:BoundarySurface)
WHERE host_wall.surface_type IN $wall_surface_types
WITH r, direct_wall_ids, collect(DISTINCT host_wall.id) AS host_wall_ids
WITH r, direct_wall_ids + host_wall_ids AS raw_wall_ids
WITH r, [id IN raw_wall_ids WHERE id IS NOT NULL] AS wall_ids
RETURN count(r) AS room_count,
       sum(size(wall_ids)) AS raw_wall_evidence_total
""",
        },
        {
            "id": "floor_surface_features",
            "description": "Collect direct and host-wall adjacency fallback FloorSurface evidence.",
            "query": """
MATCH (r:Room)
OPTIONAL MATCH (r)-[:BOUNDED_BY]->(floor:BoundarySurface)
WHERE floor.surface_type IN $floor_surface_types
WITH r, collect(DISTINCT floor.id) AS direct_floor_ids
OPTIONAL MATCH (r)<-[:CONNECTS]-(connected_opening:Opening)-[:HOSTED_BY]->(host_wall:BoundarySurface)-[:ADJACENT_SURFACE]-(host_floor:BoundarySurface)
WHERE host_floor.surface_type IN $floor_surface_types
WITH r, direct_floor_ids, collect(DISTINCT host_floor.id) AS host_floor_ids
WITH r, direct_floor_ids + host_floor_ids AS raw_floor_ids
WITH r, [id IN raw_floor_ids WHERE id IS NOT NULL] AS floor_ids
RETURN count(r) AS room_count,
       sum(size(floor_ids)) AS raw_floor_evidence_total
""",
        },
        {
            "id": "wall_floor_adjacency_features",
            "description": "Count wall-floor ADJACENT_SURFACE topology evidence.",
            "query": """
MATCH (r:Room)
OPTIONAL MATCH (r)-[:BOUNDED_BY]->(a:BoundarySurface)-[rel:ADJACENT_SURFACE]-(b:BoundarySurface)
WHERE (
    a.surface_type IN $wall_surface_types AND b.surface_type IN $floor_surface_types
  ) OR (
    a.surface_type IN $floor_surface_types AND b.surface_type IN $wall_surface_types
  )
WITH r, collect(DISTINCT a.id + '|' + b.id) AS direct_adjacency_ids
OPTIONAL MATCH (r)<-[:CONNECTS]-(connected_opening:Opening)-[:HOSTED_BY]->(host_wall:BoundarySurface)-[fallback_rel:ADJACENT_SURFACE]-(host_floor:BoundarySurface)
WHERE (
    host_wall.surface_type IN $wall_surface_types AND host_floor.surface_type IN $floor_surface_types
  ) OR (
    host_wall.surface_type IN $floor_surface_types AND host_floor.surface_type IN $wall_surface_types
  )
WITH r, direct_adjacency_ids, collect(DISTINCT host_wall.id + '|' + host_floor.id) AS fallback_adjacency_ids
WITH r, direct_adjacency_ids + fallback_adjacency_ids AS raw_adjacency_ids
WITH r, [id IN raw_adjacency_ids WHERE id IS NOT NULL] AS adjacency_ids
RETURN count(r) AS room_count,
       sum(size(adjacency_ids)) AS raw_wall_floor_adjacency_total
""",
        },
        {
            "id": "installation_features",
            "description": "Collect room installation and target installation evidence.",
            "query": """
MATCH (r:Room)
OPTIONAL MATCH (r)-[:ROOM_INSTALLATION]->(inst)
WITH r, collect(DISTINCT inst) AS raw_installations
WITH r,
     [inst IN raw_installations
       WHERE inst IS NOT NULL
         AND ('IntBuildingInstallation' IN labels(inst) OR 'BuildingInstallation' IN labels(inst))
     ] AS installations
OPTIONAL MATCH (target_int:IntBuildingInstallation)
WHERE target_int.id IN $installation_target_ids OR target_int.gml_id IN $installation_target_ids
WITH r, installations, collect(DISTINCT target_int) AS target_int_installations
OPTIONAL MATCH (target_outer:BuildingInstallation)
WHERE target_outer.id IN $installation_target_ids OR target_outer.gml_id IN $installation_target_ids
WITH r, installations, target_int_installations, collect(DISTINCT target_outer) AS target_outer_installations
WITH r, installations, target_int_installations + target_outer_installations AS target_installations
RETURN count(r) AS room_count,
       sum(size(installations)) AS room_installation_total,
       sum(size(target_installations)) AS target_installation_probe_total
""",
        },
    ],
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile room-localization query stages.")
    parser.add_argument("--config", default="configs/default.yaml", help="Project config path.")
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS), help="Scenario id to profile.")
    parser.add_argument("--view-graph", type=Path, help="Observed view graph JSON path.")
    parser.add_argument("--limit", type=int, default=10, help="Top-K limit for the full scenario query.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON report path.")
    parser.add_argument("--warmup", type=int, default=1, help="Warmup runs per query.")
    parser.add_argument("--repeat", type=int, default=3, help="Measured repeat runs per query.")
    parser.add_argument(
        "--profile-order",
        choices=("full-first", "probes-first"),
        default="full-first",
        help=(
            "Run order. Use full-first to measure retrieval cold/warm latency before diagnostic probes; "
            "use probes-first to keep the older probe-first behavior."
        ),
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help=(
            "Run RETURN 1 before the full/profile queries. This isolates lazy Neo4j driver/Bolt "
            "connection startup from retrieval query latency."
        ),
    )
    parser.add_argument("--furniture-keywords", nargs="*", help="Override furniture keywords.")
    parser.add_argument("--source-keywords", nargs="*", help="Override source keywords.")
    parser.add_argument("--target-keywords", nargs="*", help="Override target keywords.")
    return parser


def _run_query(session: Any, query: str, params: dict[str, object]) -> tuple[float, float, list[dict[str, Any]]]:
    submit_started = perf_counter()
    result = session.run(query, **params)
    submit_ms = (perf_counter() - submit_started) * 1000.0
    fetch_started = perf_counter()
    records = result.data()
    fetch_ms = (perf_counter() - fetch_started) * 1000.0
    return submit_ms, fetch_ms, records


def _record_query_run(session: Any, query: str, params: dict[str, object]) -> dict[str, object]:
    total_started = perf_counter()
    submit_ms, fetch_ms, records = _run_query(session, query, params)
    total_ms = (perf_counter() - total_started) * 1000.0
    rows_started = perf_counter()
    rows = [to_json_safe(record) for record in records]
    rows_materialize_ms = (perf_counter() - rows_started) * 1000.0
    return {
        "total_ms": round(total_ms, 3),
        "submit_ms": round(submit_ms, 3),
        "fetch_ms": round(fetch_ms, 3),
        "rows_materialize_ms": round(rows_materialize_ms, 3),
        "row_count": len(rows),
        "sample_rows": rows[0:3],
    }


def _summarize_runs(runs: list[dict[str, object]], *, prefix: str = "") -> dict[str, object]:
    if not runs:
        return {
            f"{prefix}run_count": 0,
            f"{prefix}avg_total_ms": None,
            f"{prefix}min_total_ms": None,
            f"{prefix}max_total_ms": None,
            f"{prefix}avg_submit_ms": None,
            f"{prefix}avg_fetch_ms": None,
            f"{prefix}avg_rows_materialize_ms": None,
        }
    total_values = [float(run["total_ms"]) for run in runs]
    fetch_values = [float(run["fetch_ms"]) for run in runs]
    submit_values = [float(run["submit_ms"]) for run in runs]
    materialize_values = [float(run["rows_materialize_ms"]) for run in runs]
    return {
        f"{prefix}run_count": len(runs),
        f"{prefix}avg_total_ms": round(sum(total_values) / len(total_values), 3),
        f"{prefix}min_total_ms": round(min(total_values), 3),
        f"{prefix}max_total_ms": round(max(total_values), 3),
        f"{prefix}avg_submit_ms": round(sum(submit_values) / len(submit_values), 3),
        f"{prefix}avg_fetch_ms": round(sum(fetch_values) / len(fetch_values), 3),
        f"{prefix}avg_rows_materialize_ms": round(sum(materialize_values) / len(materialize_values), 3),
    }


def _profile_query(
    session: Any,
    *,
    query: str,
    params: dict[str, object],
    warmup: int,
    repeat: int,
) -> dict[str, object]:
    warmup_runs: list[dict[str, object]] = []
    for _ in range(max(0, warmup)):
        warmup_runs.append(_record_query_run(session, query, params))

    runs: list[dict[str, object]] = []
    for _ in range(max(1, repeat)):
        runs.append(_record_query_run(session, query, params))

    first_executed_run = warmup_runs[0] if warmup_runs else runs[0]
    first_executed_source = "warmup" if warmup_runs else "measured"
    warmup_summary = _summarize_runs(warmup_runs, prefix="warmup_")
    measured_summary = _summarize_runs(runs)
    return {
        **measured_summary,
        **warmup_summary,
        "first_executed_source": first_executed_source,
        "first_executed_run": first_executed_run,
        "warmup_runs": warmup_runs,
        "runs": runs,
    }


def main() -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    total_started = perf_counter()
    args = build_parser().parse_args()

    params_started = perf_counter()
    params = _build_params(args)
    params_build_ms = (perf_counter() - params_started) * 1000.0

    config_started = perf_counter()
    config = load_project_config(args.config)
    config_load_ms = (perf_counter() - config_started) * 1000.0

    neo4j = config.neo4j
    connect_started = perf_counter()
    client = Neo4jClient(neo4j.uri, neo4j.username, neo4j.password, database=neo4j.database)
    driver_create_ms = (perf_counter() - connect_started) * 1000.0

    scenario = SCENARIOS[args.scenario]
    full_query = str(scenario["query"])
    probe_results: list[dict[str, object]] = []
    preflight_profile: dict[str, object] | None = None

    def _run_component_probes(session: Any) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for probe in COMPONENT_PROBES.get(args.scenario, []):
            profile = _profile_query(
                session,
                query=probe["query"],
                params=params,
                warmup=args.warmup,
                repeat=args.repeat,
            )
            results.append(
                {
                    "id": probe["id"],
                    "description": probe["description"],
                    "query": probe["query"].strip(),
                    **profile,
                }
            )
        return results

    try:
        with client.session() as session:
            if args.preflight:
                preflight_profile = _profile_query(
                    session,
                    query="RETURN 1 AS ok",
                    params=params,
                    warmup=1,
                    repeat=1,
                )
            if args.profile_order == "full-first":
                full_profile = _profile_query(
                    session,
                    query=full_query,
                    params=params,
                    warmup=args.warmup,
                    repeat=args.repeat,
                )
                probe_results = _run_component_probes(session)
            else:
                probe_results = _run_component_probes(session)
                full_profile = _profile_query(
                    session,
                    query=full_query,
                    params=params,
                    warmup=args.warmup,
                    repeat=args.repeat,
                )
    finally:
        client.close()

    report_started = perf_counter()
    report = {
        "summary": {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total_elapsed_ms": round((perf_counter() - total_started) * 1000.0, 3),
            "config_path": args.config,
            "output_path": str(args.output),
            "neo4j_uri": neo4j.uri,
            "neo4j_database": neo4j.database,
            "scenario": args.scenario,
            "view_graph_path": str(args.view_graph) if args.view_graph is not None else None,
            "warmup": args.warmup,
            "repeat": args.repeat,
            "profile_order": args.profile_order,
            "preflight": bool(args.preflight),
            "params_build_ms": round(params_build_ms, 3),
            "config_load_ms": round(config_load_ms, 3),
            "driver_create_ms": round(driver_create_ms, 3),
            "component_probe_count": len(probe_results),
            "note": (
                "Component probes are independent diagnostic queries. They are not an exact additive "
                "decomposition of the full scenario query plan. Warmup runs are recorded separately; "
                "avg_total_ms is computed from measured repeat runs only. Use profile_order=full-first "
                "when measuring retrieval cold/warm latency. Use preflight=true to measure and absorb "
                "lazy Neo4j connection startup before retrieval."
            ),
        },
        "preflight_query": (
            {
                "id": "preflight_return_1",
                "description": "Connectivity preflight query used to isolate lazy driver/Bolt startup cost.",
                "query": "RETURN 1 AS ok",
                **preflight_profile,
            }
            if preflight_profile is not None
            else None
        ),
        "full_query": {
            "id": args.scenario,
            "description": scenario["description"],
            "query": full_query.strip(),
            **full_profile,
        },
        "component_probes": probe_results,
        "params": params,
    }
    ensure_dir(args.output.parent)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report_write_ms = (perf_counter() - report_started) * 1000.0

    print(f"Room-localization stage profile written: {args.output}")
    print(
        "Timing: "
        f"scenario={args.scenario} "
        f"preflight={args.preflight} "
        f"full_avg={report['full_query']['avg_total_ms']}ms "
        f"probes={len(probe_results)} "
        f"report_write={round(report_write_ms, 3)}ms"
    )
    if preflight_profile is not None:
        print(
            "  preflight_return_1: "
            f"first={preflight_profile['first_executed_run']['total_ms']}ms "
            f"avg_total_ms={preflight_profile['avg_total_ms']}"
        )
    for probe in probe_results:
        print(
            f"  {probe['id']}: "
            f"warmup_avg={probe['warmup_avg_total_ms']}ms "
            f"avg_total_ms={probe['avg_total_ms']} "
            f"rows={probe['runs'][0]['row_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
