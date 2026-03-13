"""CLI entrypoints for pipeline stages."""

from __future__ import annotations

import argparse

from citygml_sg.app.pipeline import (
    run_benchmark_pipeline,
    run_export_pipeline,
    run_import_pipeline,
    run_relation_pipeline,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="citygml-sg")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import", help="Parse and ingest CityGML/CityJSON")
    import_parser.add_argument("--input", required=True, help="Path to CityGML file")
    import_parser.add_argument(
        "--output",
        default="data/output/import_summary.json",
        help="Output JSON path",
    )
    import_parser.add_argument(
        "--to-neo4j",
        action="store_true",
        help="Persist generated graph nodes/edges to Neo4j",
    )
    import_parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Project config path containing neo4j connection info",
    )

    subparsers.add_parser("relations", help="Extract spatial relations")
    subparsers.add_parser("export", help="Export graph to target storage")
    subparsers.add_parser("benchmark", help="Run benchmark queries")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "import":
        return run_import_pipeline(
            args.input,
            args.output,
            to_neo4j=args.to_neo4j,
            config_path=args.config,
        )
    if args.command == "relations":
        return run_relation_pipeline()
    if args.command == "export":
        return run_export_pipeline()
    if args.command == "benchmark":
        return run_benchmark_pipeline()

    parser.error("Unknown command")
    return 2
