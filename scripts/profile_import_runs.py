"""Run repeated import profiling and export aggregated timing report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev
import subprocess
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
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse existing import_run_<n>.json files and run only missing indices",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Run import in-process (default is subprocess isolation for memory safety)",
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


def _read_summary_only(output_path: Path) -> dict[str, object]:
    # Large output files can be multi-GB; parse only the summary prefix.
    max_bytes = 16 * 1024 * 1024
    head = output_path.open("rb").read(max_bytes)
    text = head.decode("utf-8", errors="ignore")

    summary_key = '"summary"'
    key_idx = text.find(summary_key)
    if key_idx < 0:
        return {}
    colon_idx = text.find(":", key_idx)
    obj_start = text.find("{", colon_idx)
    if obj_start < 0:
        return {}

    marker = '\n  "nodes"'
    marker_idx = text.find(marker, obj_start)
    if marker_idx < 0:
        marker_idx = text.find('\r\n  "nodes"', obj_start)
    if marker_idx < 0:
        # Fallback: try full parse only for genuinely small files.
        if output_path.stat().st_size <= max_bytes:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            return dict(payload.get("summary", {}))
        raise ValueError(
            f"Could not locate summary boundary in large output: {output_path}. "
            "Re-run import to regenerate a valid output JSON."
        )

    summary_text = text[obj_start:marker_idx].rstrip()
    if summary_text.endswith(","):
        summary_text = summary_text[:-1]
    return dict(json.loads(summary_text))


def _build_record_from_output(run_idx: int, run_output: Path, rc: int, wall_time: float | None) -> dict[str, object]:
    record: dict[str, object] = {
        "run_index": run_idx,
        "return_code": int(rc),
        "output_path": str(run_output),
    }
    if wall_time is not None and wall_time > 0.0:
        record["wall_time_seconds"] = round(float(wall_time), 6)

    if run_output.exists():
        summary = _read_summary_only(run_output)
        stage_durations = dict(summary.get("stage_durations", {}))
        if wall_time is not None and wall_time > 0.0:
            # Measured wall-time is authoritative for this process run.
            stage_durations["total"] = round(float(wall_time), 6)
            if float(stage_durations.get("export_json", 0.0) or 0.0) <= 0.0:
                known = sum(
                    float(stage_durations.get(name, 0.0) or 0.0)
                    for name in (
                        "parse_xml",
                        "collect_semantics",
                        "build_nodes",
                        "build_semantic_edges",
                        "build_geometry",
                        "export_neo4j",
                    )
                )
                derived_export_json = max(0.0, float(wall_time) - known)
                stage_durations["export_json"] = round(derived_export_json, 6)
        elif float(stage_durations.get("total", 0.0) or 0.0) > 0.0:
            record["wall_time_seconds"] = round(float(stage_durations.get("total", 0.0) or 0.0), 6)
        elif stage_durations:
            derived_total = sum(float(v or 0.0) for v in stage_durations.values())
            if derived_total > 0.0:
                stage_durations["total"] = round(float(derived_total), 6)
                record["wall_time_seconds"] = round(float(derived_total), 6)

        record["node_count"] = int(summary.get("node_count", 0))
        record["edge_count"] = int(summary.get("edge_count", 0))
        record["stage_durations"] = stage_durations
        if "scorecard" in summary:
            record["scorecard_overall"] = float(summary["scorecard"].get("overall_score", 0.0))
    return record


def _run_single_import(
    *,
    input_path: Path,
    run_output: Path,
    config_path: str,
    to_neo4j: bool,
    in_process: bool,
) -> tuple[int, float]:
    t0 = perf_counter()
    if in_process:
        rc = run_import_pipeline(
            str(input_path),
            str(run_output),
            to_neo4j=bool(to_neo4j),
            config_path=config_path,
        )
    else:
        cmd = [
            sys.executable,
            "scripts/run_import.py",
            "--input",
            str(input_path),
            "--output",
            str(run_output),
            "--config",
            str(config_path),
        ]
        if to_neo4j:
            cmd.append("--to-neo4j")
        proc = subprocess.run(cmd, check=False)
        rc = int(proc.returncode)
    wall_time = perf_counter() - t0
    return int(rc), float(wall_time)


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
        if args.resume and run_output.exists():
            try:
                record = _build_record_from_output(run_idx, run_output, rc=0, wall_time=None)
                run_records.append(record)
                LOGGER.info(
                    "[Profile] run=%d rc=%d wall=%s output=%s (reused)",
                    run_idx,
                    0,
                    f"{float(record.get('wall_time_seconds', 0.0)):.3f}s"
                    if "wall_time_seconds" in record
                    else "unknown",
                    run_output,
                )
                continue
            except Exception as exc:
                LOGGER.warning(
                    "[Profile] run=%d existing output parse failed (%s), rerunning",
                    run_idx,
                    exc,
                )

        rc, wall_time = _run_single_import(
            input_path=input_path,
            run_output=run_output,
            config_path=args.config,
            to_neo4j=bool(args.to_neo4j),
            in_process=bool(args.in_process),
        )
        record = _build_record_from_output(run_idx, run_output, rc=rc, wall_time=wall_time)
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

    wall_values = [
        float(record.get("wall_time_seconds", 0.0))
        for record in successful
        if float(record.get("wall_time_seconds", 0.0) or 0.0) > 0.0
    ]
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
