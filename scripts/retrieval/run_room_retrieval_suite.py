"""Run a room-retrieval evaluation suite against Neo4j."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from citygml_sg.config.settings import load_project_config
from citygml_sg.retrieval.evaluation import (
    apply_case_variant,
    evaluate_case_rows,
    normalize_recall_k_values,
    summarize_evaluations,
)
from citygml_sg.retrieval.query_generator import SCENARIOS
from citygml_sg.retrieval.reporting import to_json_safe
from citygml_sg.retrieval.scoring import build_room_retrieval_params
from citygml_sg.storage.neo4j.client import Neo4jClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run room-retrieval test suite cases.")
    parser.add_argument("--suite", type=Path, required=True, help="Room retrieval suite JSON file.")
    parser.add_argument("--config", default="configs/default.yaml", help="Neo4j config path.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON report path.")
    parser.add_argument("--top-k", type=int, default=3, help="Top-K inclusion threshold.")
    parser.add_argument(
        "--recall-k",
        nargs="*",
        type=int,
        default=[1, 3, 5],
        help="Recall@K thresholds to report. Defaults to 1 3 5. top-k is always included.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Override candidate limit for every case.")
    parser.add_argument(
        "--case-id",
        action="append",
        help="Optional case id filter. Can be repeated. Defaults to all cases.",
    )
    return parser


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_suite(path: Path) -> dict[str, Any]:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: suite must be a JSON object")
    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path}: suite requires a non-empty 'cases' list")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"{path}: cases[{index}] must be an object")
        for key in ("case_id", "scenario_id", "view_graph", "target_room"):
            if not case.get(key):
                raise ValueError(f"{path}: cases[{index}] requires '{key}'")
    return raw


def _select_cases(cases: list[dict[str, Any]], case_ids: list[str] | None) -> list[dict[str, Any]]:
    if not case_ids:
        return cases
    wanted = set(case_ids)
    selected = [case for case in cases if str(case.get("case_id")) in wanted]
    missing = sorted(wanted - {str(case.get("case_id")) for case in selected})
    if missing:
        raise ValueError(f"case_id not found in suite: {', '.join(missing)}")
    return selected


def _case_limit(case: dict[str, Any], *, suite_default: int, cli_limit: int | None) -> int:
    if cli_limit is not None:
        return max(1, int(cli_limit))
    if case.get("limit") is not None:
        return max(1, int(case["limit"]))
    return max(1, suite_default)


def main() -> int:
    args = build_parser().parse_args()
    if args.top_k < 1:
        raise ValueError("--top-k must be >= 1")
    recall_k_values = normalize_recall_k_values(args.recall_k, top_k=args.top_k)

    suite = _load_suite(args.suite)
    cases = _select_cases(list(suite["cases"]), args.case_id)
    suite_default_limit = max(1, int(suite.get("default_limit", 10)))

    config = load_project_config(args.config)
    neo4j = config.neo4j
    client = Neo4jClient(neo4j.uri, neo4j.username, neo4j.password, database=neo4j.database)

    started_at = datetime.now(timezone.utc).isoformat()
    run_t0 = perf_counter()
    evaluated_cases: list[dict[str, Any]] = []
    try:
        with client.session() as session:
            for case in cases:
                scenario_id = str(case["scenario_id"])
                if scenario_id not in SCENARIOS:
                    raise ValueError(f"Unknown scenario_id: {scenario_id}")
                scenario = SCENARIOS[scenario_id]
                params = build_room_retrieval_params(
                    view_graph_path=str(case["view_graph"]),
                    limit=_case_limit(case, suite_default=suite_default_limit, cli_limit=args.limit),
                    furniture_keywords=None,
                    source_keywords=None,
                    target_keywords=None,
                )
                params = apply_case_variant(params, case)
                case["observed_object_count"] = len(params.get("observed_objects", []))
                case["observed_relation_count"] = len(params.get("observed_relations", []))

                query = str(scenario["query"])
                query_t0 = perf_counter()
                rows = [to_json_safe(row) for row in session.run(query, **params).data()]
                query_elapsed_ms = (perf_counter() - query_t0) * 1000.0

                evaluated = evaluate_case_rows(
                    case,
                    rows,
                    top_k=args.top_k,
                    retrieval_time_ms=query_elapsed_ms,
                    recall_k_values=recall_k_values,
                )
                evaluated["description"] = case.get("description", "")
                evaluated["variant"] = case.get("variant", {})
                evaluated["params"] = {
                    "limit": params.get("limit"),
                    "furniture_keywords": params.get("furniture_keywords"),
                    "source_keywords": params.get("source_keywords"),
                    "target_keywords": params.get("target_keywords"),
                    "min_doors": params.get("min_doors"),
                    "min_windows": params.get("min_windows"),
                    "installation_keywords": params.get("installation_keywords"),
                    "installation_target_ids": params.get("installation_target_ids"),
                }
                evaluated_cases.append(evaluated)
                print(
                    f"{evaluated['case_id']}: target={evaluated['target_room']} "
                    f"rank={evaluated['target_rank']} top={evaluated['top_room'].get('room_name')} "
                    f"time={evaluated['retrieval_time_ms']}ms"
                )
    finally:
        client.close()

    finished_at = datetime.now(timezone.utc).isoformat()
    report = {
        "summary": {
            "suite_id": suite.get("suite_id", args.suite.stem),
            "dataset": suite.get("dataset", ""),
            "started_at": started_at,
            "finished_at": finished_at,
            "total_elapsed_ms": round((perf_counter() - run_t0) * 1000.0, 3),
            "config_path": str(args.config),
            "neo4j_uri": neo4j.uri,
            "neo4j_database": neo4j.database,
            "suite_path": str(args.suite),
            "case_count": len(evaluated_cases),
            "top_k": args.top_k,
            "recall_k": list(recall_k_values),
        },
        "metrics": summarize_evaluations(
            evaluated_cases,
            top_k=args.top_k,
            recall_k_values=recall_k_values,
        ),
        "cases": evaluated_cases,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    overall = report["metrics"]["overall"]
    print(f"Room-retrieval suite report written: {args.output}")
    print(
        "Metrics: "
        f"recall@1={overall['recall_at_1_pct']}% "
        f"recall@{args.top_k}={overall[f'recall_at_{args.top_k}_pct']}% "
        f"mean_rank={overall['mean_target_room_rank']} "
        f"mrr={overall['mrr']} "
        f"time_mean={overall['retrieval_time_ms_mean']}ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
