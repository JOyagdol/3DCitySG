"""Run repeated import profiling and export aggregated timing report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev
import sys
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from citygml_sg.app.pipeline import run_import_pipeline
from citygml_sg.utils.io import ensure_dir
from citygml_sg.utils.logging import get_logger

LOGGER = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile repeated import runs")
    parser.add_argument("--input", required=True, help="Path to CityGML input file")
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Project config path",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of repeated runs",
    )
    parser.add_argument(
        "--output-dir",
        default="data/output/profiling",
        help="Directory for per-run outputs",
    )
    parser.add_argument(
        "--report",
        default="data/output/import_profile_report.json",
        help="Aggregated profiling report path",
    )
    parser.add_argument(
        "--to-neo4j",
        action="store_true",
        help="Include Neo4j export in profiling run",
    )
    return parser


def _aggregate_metric(values: list[float]) -> dict[str, float]:
    if not values:
        return {"avg": 0.0, "min": 0.0, "max": 0.0, "std": 0.0}
    return {
        "avg": round(mean(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "std": round(pstdev(values), 6) if len(values) > 1 else 0.0,
    }


def main() -> int:
    args = build_parser().parse_args()
    if args.runs <= 0:
        LOGGER.error("--runs must be >= 1")
        return 2

    input_path = Path(args.input)
    if not input_path.exists():
        LOGGER.error("Input file does not exist: %s", input_path)
        return 2

    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)

    run_records: list[dict[str, object]] = []
    for run_idx in range(1, args.runs + 1):
        run_output = output_dir / f"import_run_{run_idx}.json"
        t0 = perf_counter()
        rc = run_import_pipeline(
            str(input_path),
            str(run_output),
            to_neo4j=bool(args.to_neo4j),
            config_path=args.config,
        )
        wall_time = perf_counter() - t0

        record: dict[str, object] = {
            "run_index": run_idx,
            "return_code": int(rc),
            "wall_time_seconds": round(wall_time, 6),
            "output_path": str(run_output),
        }
        if run_output.exists():
            payload = json.loads(run_output.read_text(encoding="utf-8"))
            summary = payload.get("summary", {})
            stage_durations = summary.get("stage_durations", {})
            record["node_count"] = int(summary.get("node_count", 0))
            record["edge_count"] = int(summary.get("edge_count", 0))
            record["stage_durations"] = stage_durations
            if "scorecard" in summary:
                record["scorecard_overall"] = float(summary["scorecard"].get("overall_score", 0.0))
        run_records.append(record)
        LOGGER.info(
            "[Profile] run=%d rc=%d wall=%.3fs output=%s",
            run_idx,
            rc,
            wall_time,
            run_output,
        )

    successful = [r for r in run_records if int(r.get("return_code", 0)) == 0]
    stage_names = {
        stage
        for record in successful
        for stage in dict(record.get("stage_durations", {})).keys()
    }
    stage_aggregates: dict[str, dict[str, float]] = {}
    for stage in sorted(stage_names):
        values = [
            float(dict(record.get("stage_durations", {})).get(stage, 0.0))
            for record in successful
            if stage in dict(record.get("stage_durations", {}))
        ]
        stage_aggregates[stage] = _aggregate_metric(values)

    wall_values = [float(record.get("wall_time_seconds", 0.0)) for record in successful]
    node_values = [float(record.get("node_count", 0)) for record in successful if "node_count" in record]
    edge_values = [float(record.get("edge_count", 0)) for record in successful if "edge_count" in record]

    report = {
        "summary": {
            "input_path": str(input_path),
            "config_path": str(args.config),
            "to_neo4j": bool(args.to_neo4j),
            "runs_requested": int(args.runs),
            "runs_success": len(successful),
            "runs_failed": int(args.runs) - len(successful),
            "wall_time_seconds": _aggregate_metric(wall_values),
            "node_count": _aggregate_metric(node_values),
            "edge_count": _aggregate_metric(edge_values),
            "stage_duration_seconds": stage_aggregates,
        },
        "runs": run_records,
    }

    report_path = Path(args.report)
    ensure_dir(report_path.parent)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info("Profile report written: %s", report_path)
    return 0 if report["summary"]["runs_failed"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
