"""Run Neo4j query benchmark suite and export JSON report."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from citygml_sg.app.pipeline import run_benchmark_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run benchmark query suite")
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Project config path containing Neo4j connection info",
    )
    parser.add_argument(
        "--output",
        default="data/output/benchmark_report.json",
        help="Benchmark report JSON path",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
        help="Warmup run count for each query",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=3,
        help="Measured repeat run count for each query",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    raise SystemExit(
        run_benchmark_pipeline(
            config_path=args.config,
            output_path=args.output,
            warmup_runs=args.warmup,
            repeat_runs=args.repeat,
        )
    )
