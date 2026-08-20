"""Run room-localization Cypher scenarios against the Neo4j world graph."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from citygml_sg.config.settings import load_project_config
from citygml_sg.retrieval.query_generator import SCENARIOS
from citygml_sg.retrieval.scoring import (
    DEFAULT_ROOM_RETRIEVAL_PARAMS,
    build_room_retrieval_params,
)
from citygml_sg.retrieval.reporting import to_json_safe as _json_safe
from citygml_sg.storage.neo4j.client import Neo4jClient
from citygml_sg.utils.io import ensure_dir


DEFAULT_PARAMS = DEFAULT_ROOM_RETRIEVAL_PARAMS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run room-localization Cypher scenario tests")
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Project config path containing Neo4j connection info",
    )
    parser.add_argument(
        "--output",
        default="data/output/room_localization_query_report.json",
        help="Room-localization scenario report JSON path",
    )
    parser.add_argument(
        "--scenario",
        choices=["all", *SCENARIOS.keys()],
        default="all",
        help="Scenario to run",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max rows per scenario")
    parser.add_argument(
        "--furniture-keywords",
        nargs="*",
        default=None,
        help="Furniture category/name keywords observed from an image view graph",
    )
    parser.add_argument(
        "--source-keywords",
        nargs="*",
        default=None,
        help="Source object keywords for furniture-pair scenario",
    )
    parser.add_argument(
        "--target-keywords",
        nargs="*",
        default=None,
        help="Target object keywords for furniture-pair scenario",
    )
    parser.add_argument(
        "--view-graph",
        default=None,
        help="Observed view graph JSON path. When provided, object scoring uses weight * confidence * visibility.",
    )
    return parser


def _build_params(args: argparse.Namespace) -> dict[str, object]:
    return build_room_retrieval_params(
        view_graph_path=args.view_graph,
        limit=args.limit,
        furniture_keywords=args.furniture_keywords,
        source_keywords=args.source_keywords,
        target_keywords=args.target_keywords,
    )


def _selected_scenarios(name: str) -> list[tuple[str, dict[str, object]]]:
    if name == "all":
        return list(SCENARIOS.items())
    return [(name, SCENARIOS[name])]


def main() -> int:
    run_t0 = perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    args = build_parser().parse_args()
    params = _build_params(args)
    config = load_project_config(args.config)
    neo4j = config.neo4j
    client = Neo4jClient(neo4j.uri, neo4j.username, neo4j.password, database=neo4j.database)

    results: list[dict[str, object]] = []
    try:
        with client.session() as session:
            for scenario_id, scenario in _selected_scenarios(args.scenario):
                query = str(scenario["query"])
                query_started_at = datetime.now(timezone.utc).isoformat()
                query_t0 = perf_counter()
                records = session.run(query, **params).data()
                query_elapsed_ms = (perf_counter() - query_t0) * 1000.0
                query_finished_at = datetime.now(timezone.utc).isoformat()
                rows = [_json_safe(record) for record in records]
                top_room = rows[0] if rows else None
                results.append(
                    {
                        "id": scenario_id,
                        "description": scenario["description"],
                        "view_graph_schema": scenario["view_graph_schema"],
                        "query": query.strip(),
                        "params": params,
                        "row_count": len(rows),
                        "elapsed_ms": round(query_elapsed_ms, 3),
                        "query_elapsed_ms": round(query_elapsed_ms, 3),
                        "query_started_at": query_started_at,
                        "query_finished_at": query_finished_at,
                        "top_room": top_room,
                        "rows": rows,
                    }
                )
    finally:
        client.close()

    finished_at = datetime.now(timezone.utc).isoformat()
    query_elapsed_ms_total = sum(float(result.get("query_elapsed_ms", 0.0)) for result in results)
    total_elapsed_ms = (perf_counter() - run_t0) * 1000.0
    report = {
        "summary": {
            "started_at": started_at,
            "finished_at": finished_at,
            "total_elapsed_ms": round(total_elapsed_ms, 3),
            "query_elapsed_ms_total": round(query_elapsed_ms_total, 3),
            "config_path": str(args.config),
            "output_path": str(args.output),
            "neo4j_uri": neo4j.uri,
            "neo4j_database": neo4j.database,
            "scenario": args.scenario,
            "scenario_total": len(results),
            "limit": int(params["limit"]),
            "view_graph_path": params.get("view_graph_path"),
            "observed_object_count": len(params.get("observed_objects", [])),
            "observed_relation_count": len(params.get("observed_relations", [])),
        },
        "scenarios": results,
    }

    output = Path(args.output)
    ensure_dir(output.parent)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Room-localization query report written: {output}")
    print(
        "Timing: "
        f"total={round((perf_counter() - run_t0) * 1000.0, 3)}ms "
        f"query_total={round(query_elapsed_ms_total, 3)}ms "
        f"scenarios={len(results)}"
    )
    for result in results:
        print(
            "  "
            f"{result['id']}: query_elapsed_ms={result['query_elapsed_ms']} "
            f"rows={result['row_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
