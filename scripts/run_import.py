"""Run semantic parsing and graph import pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from citygml_sg.app.pipeline import run_import_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CityGML import pipeline")
    parser.add_argument("--input", required=True, help="Path to CityGML (.gml/.xml) file")
    parser.add_argument(
        "--output",
        default="data/output/import_summary.json",
        help="Path to output summary JSON file",
    )
    parser.add_argument(
        "--to-neo4j",
        action="store_true",
        help="Persist generated graph nodes/edges to Neo4j",
    )
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Project config path containing neo4j connection info",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    raise SystemExit(
        run_import_pipeline(
            args.input,
            args.output,
            to_neo4j=args.to_neo4j,
            config_path=args.config,
        )
    )
