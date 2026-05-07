"""Refresh latest import/benchmark/profile reports in one command."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh latest reporting artifacts")
    parser.add_argument(
        "--input",
        default="data/input/(210812)E-TYPE_201dong-IFC4.gml",
        help="CityGML input path for import/profile runs",
    )
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Project config path",
    )
    parser.add_argument(
        "--output-dir",
        default="data/output",
        help="Output directory root",
    )
    parser.add_argument(
        "--baseline",
        default="configs/baselines/201dong_v1_baseline.json",
        help="Baseline JSON path for pass/fail validation",
    )
    parser.add_argument(
        "--dataset-tag",
        default="",
        help="Optional dataset tag override (default: derived from input filename)",
    )
    parser.add_argument("--warmup", type=int, default=1, help="Benchmark warmup runs")
    parser.add_argument("--repeat", type=int, default=3, help="Benchmark measured runs")
    parser.add_argument("--profile-runs", type=int, default=3, help="Repeated import profile runs")
    parser.add_argument(
        "--profile-output-dir",
        default="",
        help="Optional override for profiling output directory",
    )
    parser.add_argument(
        "--profile-report",
        default="",
        help="Optional override for profiling aggregate report path",
    )
    parser.add_argument(
        "--profile-resume",
        action="store_true",
        help="Pass --resume to profile_import_runs.py (reuse existing import_run_<n>.json)",
    )
    parser.add_argument(
        "--profile-in-process",
        action="store_true",
        help="Pass --in-process to profile_import_runs.py (default is subprocess isolation)",
    )
    parser.add_argument(
        "--to-neo4j",
        action="store_true",
        help="Force import sync to Neo4j before running benchmark",
    )
    parser.add_argument(
        "--no-promote-defaults",
        action="store_true",
        help="Do not overwrite default output files in data/output",
    )
    parser.add_argument("--skip-import", action="store_true", help="Skip import summary generation")
    parser.add_argument("--skip-benchmark", action="store_true", help="Skip query benchmark generation")
    parser.add_argument("--skip-profile", action="store_true", help="Skip repeated import profiling")
    parser.add_argument("--skip-baseline", action="store_true", help="Skip baseline validation")
    return parser


def _run(cmd: list[str]) -> None:
    print(f"[RUN] {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", text.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned.lower() or "dataset"


def _promote_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"[PROMOTE] {dst} <= {src}")


def _promote_profile_dir(src_dir: Path, dst_dir: Path) -> None:
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)
    print(f"[PROMOTE] {dst_dir} <= {src_dir}")


def main() -> int:
    args = build_parser().parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    promote_defaults = not args.no_promote_defaults

    if args.to_neo4j and (not args.skip_benchmark) and args.skip_import:
        print("[ERROR] --to-neo4j requires import stage when benchmark is enabled. Remove --skip-import.")
        return 2

    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    input_path = Path(args.input)
    dataset_tag = _slugify(args.dataset_tag) if args.dataset_tag else _slugify(input_path.stem)

    import_summary_path = output_root / f"{dataset_tag}__import_summary_{timestamp}.json"
    benchmark_report_path = output_root / f"{dataset_tag}__benchmark_report_{timestamp}.json"
    profile_dir = (
        Path(args.profile_output_dir)
        if args.profile_output_dir
        else output_root / f"{dataset_tag}__profiling_{timestamp}"
    )
    profile_report_path = (
        Path(args.profile_report)
        if args.profile_report
        else output_root / f"{dataset_tag}__import_profile_report_{timestamp}.json"
    )
    default_import_summary_path = output_root / "import_summary.json"
    default_benchmark_report_path = output_root / "benchmark_report.json"
    default_profile_dir = output_root / "profiling"
    default_profile_report_path = output_root / "import_profile_report.json"

    if not args.skip_import:
        import_cmd = [
            sys.executable,
            "scripts/run_import.py",
            "--input",
            args.input,
            "--output",
            str(import_summary_path),
            "--config",
            args.config,
        ]
        if args.to_neo4j:
            import_cmd.append("--to-neo4j")
        _run(import_cmd)
        if promote_defaults:
            _promote_file(import_summary_path, default_import_summary_path)

    if not args.skip_benchmark:
        _run(
            [
                sys.executable,
                "scripts/benchmark_queries.py",
                "--config",
                args.config,
                "--output",
                str(benchmark_report_path),
                "--warmup",
                str(args.warmup),
                "--repeat",
                str(args.repeat),
            ]
        )
        if promote_defaults:
            _promote_file(benchmark_report_path, default_benchmark_report_path)

    if not args.skip_profile:
        profile_cmd = [
            sys.executable,
            "scripts/profile_import_runs.py",
            "--input",
            args.input,
            "--runs",
            str(args.profile_runs),
            "--config",
            args.config,
            "--output-dir",
            str(profile_dir),
            "--report",
            str(profile_report_path),
        ]
        if args.profile_resume:
            profile_cmd.append("--resume")
        if args.profile_in_process:
            profile_cmd.append("--in-process")
        _run(profile_cmd)
        if promote_defaults:
            _promote_profile_dir(profile_dir, default_profile_dir)
            _promote_file(profile_report_path, default_profile_report_path)

    if not args.skip_baseline:
        if args.skip_import:
            print("[WARN] baseline check requires import summary path; --skip-import used.")
        else:
            baseline_cmd = [
                sys.executable,
                "scripts/check_large_scale_baseline.py",
                "--baseline",
                args.baseline,
                "--import-summary",
                str(import_summary_path),
            ]
            if not args.skip_profile:
                baseline_cmd.extend(["--profile-report", str(profile_report_path)])
            _run(baseline_cmd)

    print("[DONE] latest report refresh complete")
    print(f"  dataset_tag:      {dataset_tag}")
    print(f"  import_summary:   {import_summary_path if not args.skip_import else 'SKIPPED'}")
    print(f"  benchmark_report: {benchmark_report_path if not args.skip_benchmark else 'SKIPPED'}")
    print(f"  profile_report:   {profile_report_path if not args.skip_profile else 'SKIPPED'}")
    if promote_defaults:
        print("  defaults:         UPDATED")
    else:
        print("  defaults:         SKIPPED (--no-promote-defaults)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
