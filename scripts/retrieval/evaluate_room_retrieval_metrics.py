"""Evaluate room-retrieval reports against target rooms."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute Top-1, Top-K, mean rank, MRR, and retrieval time from room query reports."
    )
    parser.add_argument(
        "--case",
        action="append",
        nargs=3,
        metavar=("CASE_ID", "REPORT_PATH", "TARGET_ROOM"),
        help="Evaluation case triple. TARGET_ROOM can match room_name or room_id.",
    )
    parser.add_argument(
        "--case-file",
        type=Path,
        help="JSON file with cases: either a list or {'cases': [...]} entries.",
    )
    parser.add_argument(
        "--scenario-id",
        help="Scenario id to evaluate when a report contains multiple scenarios. Defaults to the first scenario.",
    )
    parser.add_argument("--top-k", type=int, default=3, help="Top-K inclusion threshold. Default: 3.")
    parser.add_argument("--output", type=Path, required=True, help="Path to write the evaluation JSON report.")
    return parser


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_cases(args: argparse.Namespace) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    if args.case_file is not None:
        raw = _read_json(args.case_file)
        raw_cases = raw.get("cases", raw) if isinstance(raw, dict) else raw
        if not isinstance(raw_cases, list):
            raise ValueError(f"{args.case_file}: expected a list or an object with a 'cases' list")
        for index, item in enumerate(raw_cases):
            if not isinstance(item, dict):
                raise ValueError(f"{args.case_file}: cases[{index}] must be an object")
            case_id = item.get("case_id") or item.get("id")
            report_path = item.get("report_path") or item.get("report")
            target_room = item.get("target_room") or item.get("target")
            if not case_id or not report_path or not target_room:
                raise ValueError(
                    f"{args.case_file}: cases[{index}] requires case_id, report_path, and target_room"
                )
            case = {
                "case_id": str(case_id),
                "report_path": str(report_path),
                "target_room": str(target_room),
            }
            if item.get("scenario_id"):
                case["scenario_id"] = str(item["scenario_id"])
            cases.append(case)

    for case_id, report_path, target_room in args.case or []:
        cases.append(
            {
                "case_id": case_id,
                "report_path": report_path,
                "target_room": target_room,
            }
        )

    if not cases:
        raise ValueError("Provide at least one --case or --case-file entry")
    return cases


def _normalize(value: object) -> str:
    return str(value or "").strip().casefold()


def _select_scenario(report: dict[str, Any], scenario_id: str | None) -> dict[str, Any]:
    scenarios = report.get("scenarios", [])
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("report has no scenarios")
    if scenario_id is None:
        return scenarios[0]
    for scenario in scenarios:
        if str(scenario.get("id")) == scenario_id:
            return scenario
    raise ValueError(f"scenario not found: {scenario_id}")


def _find_target_rank(rows: list[dict[str, Any]], target_room: str) -> int | None:
    target = _normalize(target_room)
    for index, row in enumerate(rows, start=1):
        if _normalize(row.get("room_name")) == target or _normalize(row.get("room_id")) == target:
            return index
    return None


def _evaluate_case(case: dict[str, str], *, top_k: int, default_scenario_id: str | None) -> dict[str, Any]:
    report_path = Path(case["report_path"])
    report = _read_json(report_path)
    scenario_id = case.get("scenario_id") or default_scenario_id
    scenario = _select_scenario(report, scenario_id)
    rows = scenario.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError(f"{report_path}: scenario rows must be a list")

    target_room = case["target_room"]
    rank = _find_target_rank(rows, target_room)
    row_count = len(rows)
    penalized_rank = rank if rank is not None else row_count + 1
    reciprocal_rank = 0.0 if rank is None else 1.0 / rank
    query_elapsed_ms = scenario.get("query_elapsed_ms", scenario.get("elapsed_ms"))
    total_elapsed_ms = None
    summary = report.get("summary")
    if isinstance(summary, dict):
        total_elapsed_ms = summary.get("total_elapsed_ms")
    top_room = rows[0] if rows else None

    return {
        "case_id": case["case_id"],
        "report_path": str(report_path),
        "scenario_id": str(scenario.get("id", scenario_id or "")),
        "target_room": target_room,
        "target_rank": rank,
        "target_rank_for_mean": penalized_rank,
        "target_found": rank is not None,
        "top1_correct": rank == 1,
        f"top{top_k}_included": rank is not None and rank <= top_k,
        "reciprocal_rank": round(reciprocal_rank, 6),
        "retrieval_time_ms": query_elapsed_ms,
        "total_elapsed_ms": total_elapsed_ms,
        "row_count": row_count,
        "top_room": {
            "room_id": top_room.get("room_id") if isinstance(top_room, dict) else None,
            "room_name": top_room.get("room_name") if isinstance(top_room, dict) else None,
            "total_score": top_room.get("total_score") if isinstance(top_room, dict) else None,
        },
    }


def _average_numeric(values: list[Any]) -> float | None:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric:
        return None
    return round(mean(numeric), 3)


def _sum_numeric(values: list[Any]) -> float | None:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric:
        return None
    return round(sum(numeric), 3)


def main() -> int:
    args = build_parser().parse_args()
    if args.top_k < 1:
        raise ValueError("--top-k must be >= 1")

    cases = _load_cases(args)
    evaluated = [
        _evaluate_case(case, top_k=args.top_k, default_scenario_id=args.scenario_id)
        for case in cases
    ]
    case_count = len(evaluated)
    top1_count = sum(1 for item in evaluated if item["top1_correct"])
    topk_key = f"top{args.top_k}_included"
    topk_count = sum(1 for item in evaluated if item[topk_key])
    mrr = mean(float(item["reciprocal_rank"]) for item in evaluated)
    mean_rank = mean(float(item["target_rank_for_mean"]) for item in evaluated)

    report = {
        "summary": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "case_count": case_count,
            "top_k": args.top_k,
            "top1_room_accuracy": round(top1_count / case_count, 6),
            "top1_room_accuracy_pct": round((top1_count / case_count) * 100.0, 3),
            f"top{args.top_k}_room_inclusion": round(topk_count / case_count, 6),
            f"top{args.top_k}_room_inclusion_pct": round((topk_count / case_count) * 100.0, 3),
            "mean_target_room_rank": round(mean_rank, 3),
            "mrr": round(mrr, 6),
            "retrieval_time_ms_mean": _average_numeric([item["retrieval_time_ms"] for item in evaluated]),
            "retrieval_time_ms_total": _sum_numeric([item["retrieval_time_ms"] for item in evaluated]),
            "total_elapsed_ms_mean": _average_numeric([item["total_elapsed_ms"] for item in evaluated]),
            "total_elapsed_ms_total": _sum_numeric([item["total_elapsed_ms"] for item in evaluated]),
        },
        "cases": evaluated,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Room-retrieval metrics report written: {args.output}")
    print(
        "Metrics: "
        f"top1={report['summary']['top1_room_accuracy_pct']}% "
        f"top{args.top_k}={report['summary'][f'top{args.top_k}_room_inclusion_pct']}% "
        f"mean_rank={report['summary']['mean_target_room_rank']} "
        f"mrr={report['summary']['mrr']} "
        f"retrieval_time_mean={report['summary']['retrieval_time_ms_mean']}ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
