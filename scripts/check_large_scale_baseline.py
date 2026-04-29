"""Validate import/profile outputs against a large-scale baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from citygml_sg.utils.logging import get_logger

LOGGER = get_logger(__name__)


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fmt_ok(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _check_min_max(
    value: float,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> bool:
    if min_value is not None and value < min_value:
        return False
    if max_value is not None and value > max_value:
        return False
    return True


def _check_import_summary(
    baseline: dict[str, Any],
    summary_payload: dict[str, Any],
) -> tuple[bool, list[str]]:
    checks: list[str] = []
    ok_all = True
    summary_cfg = baseline.get("import_summary", {})
    summary = summary_payload.get("summary", summary_payload)

    for field in ("node_count", "edge_count"):
        cfg = summary_cfg.get(field, {})
        value = float(summary.get(field, 0))
        ok = _check_min_max(
            value,
            min_value=cfg.get("min"),
            max_value=cfg.get("max"),
        )
        checks.append(
            f"[{_fmt_ok(ok)}] import.{field}={value:.0f} range=[{cfg.get('min')}, {cfg.get('max')}]"
        )
        ok_all = ok_all and ok

    scorecard = summary.get("scorecard", {})
    score_cfg = summary_cfg.get("scorecard", {})
    score_fields: list[tuple[str, str]] = [
        ("overall_score", "overall_min"),
        ("node_coverage.score", "node_coverage_min"),
        ("relation_coverage.score", "relation_coverage_min"),
        ("property_coverage.score", "property_coverage_min"),
        ("spatial_coverage.score", "spatial_coverage_min"),
        ("spatial_precision_sanity.score", "spatial_precision_sanity_min"),
    ]

    def _read_nested(obj: dict[str, Any], dotted: str) -> float:
        cur: Any = obj
        for token in dotted.split("."):
            if not isinstance(cur, dict):
                return 0.0
            cur = cur.get(token)
        try:
            return float(cur)
        except (TypeError, ValueError):
            return 0.0

    for field, min_key in score_fields:
        min_value = score_cfg.get(min_key)
        if min_value is None:
            continue
        value = _read_nested(scorecard, field)
        ok = value >= float(min_value)
        checks.append(f"[{_fmt_ok(ok)}] scorecard.{field}={value:.2f} min={float(min_value):.2f}")
        ok_all = ok_all and ok

    node_type_counts = summary.get("node_type_counts", {})
    for node_type, expected in dict(summary_cfg.get("node_type_counts", {})).items():
        actual = int(node_type_counts.get(node_type, -1))
        ok = actual == int(expected)
        checks.append(f"[{_fmt_ok(ok)}] node_type_counts.{node_type}={actual} expected={int(expected)}")
        ok_all = ok_all and ok

    relation_counts = summary.get("relation_counts", {})
    for relation, expected in dict(summary_cfg.get("relation_counts", {})).items():
        actual = int(relation_counts.get(relation, -1))
        ok = actual == int(expected)
        checks.append(f"[{_fmt_ok(ok)}] relation_counts.{relation}={actual} expected={int(expected)}")
        ok_all = ok_all and ok

    return ok_all, checks


def _check_profile_report(
    baseline: dict[str, Any],
    profile_payload: dict[str, Any],
) -> tuple[bool, list[str]]:
    checks: list[str] = []
    ok_all = True
    profile_cfg = baseline.get("profile_report", {})
    summary = profile_payload.get("summary", {})

    runs_requested_expected = profile_cfg.get("runs_requested")
    runs_requested_actual = int(summary.get("runs_requested", 0))
    if runs_requested_expected is not None:
        ok = runs_requested_actual == int(runs_requested_expected)
        checks.append(
            f"[{_fmt_ok(ok)}] profile.runs_requested={runs_requested_actual} expected={int(runs_requested_expected)}"
        )
        ok_all = ok_all and ok

    runs_success_min = profile_cfg.get("runs_success_min")
    runs_success_actual = int(summary.get("runs_success", 0))
    if runs_success_min is not None:
        ok = runs_success_actual >= int(runs_success_min)
        checks.append(
            f"[{_fmt_ok(ok)}] profile.runs_success={runs_success_actual} min={int(runs_success_min)}"
        )
        ok_all = ok_all and ok

    wall_cfg = dict(profile_cfg.get("wall_time_seconds", {}))
    wall_summary = dict(summary.get("wall_time_seconds", {}))
    for metric, op in (("avg", "avg_max"), ("std", "std_max")):
        limit = wall_cfg.get(op)
        if limit is None:
            continue
        value = float(wall_summary.get(metric, 0.0))
        ok = value <= float(limit)
        checks.append(f"[{_fmt_ok(ok)}] profile.wall_time_seconds.{metric}={value:.3f} max={float(limit):.3f}")
        ok_all = ok_all and ok

    stage_cfg = dict(profile_cfg.get("stage_duration_seconds", {}))
    stage_summary = dict(summary.get("stage_duration_seconds", {}))
    for stage_name, limits in stage_cfg.items():
        stage_stats = dict(stage_summary.get(stage_name, {}))
        avg_max = limits.get("avg_max")
        std_max = limits.get("std_max")
        if avg_max is not None:
            value = float(stage_stats.get("avg", 0.0))
            ok = value <= float(avg_max)
            checks.append(f"[{_fmt_ok(ok)}] profile.stage.{stage_name}.avg={value:.3f} max={float(avg_max):.3f}")
            ok_all = ok_all and ok
        if std_max is not None:
            value = float(stage_stats.get("std", 0.0))
            ok = value <= float(std_max)
            checks.append(f"[{_fmt_ok(ok)}] profile.stage.{stage_name}.std={value:.3f} max={float(std_max):.3f}")
            ok_all = ok_all and ok

    return ok_all, checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate large-scale baseline")
    parser.add_argument(
        "--baseline",
        default="configs/baselines/201dong_v1_baseline.json",
        help="Baseline definition JSON path",
    )
    parser.add_argument(
        "--import-summary",
        required=True,
        help="Import output JSON path (summary.scorecard expected)",
    )
    parser.add_argument(
        "--profile-report",
        default="",
        help="Optional profile report JSON path",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    baseline = _load_json(args.baseline)
    import_payload = _load_json(args.import_summary)

    ok_import, import_checks = _check_import_summary(baseline, import_payload)
    LOGGER.info("Baseline check: import summary")
    for line in import_checks:
        LOGGER.info("  %s", line)

    ok_profile = True
    if args.profile_report:
        profile_payload = _load_json(args.profile_report)
        ok_profile, profile_checks = _check_profile_report(baseline, profile_payload)
        LOGGER.info("Baseline check: profile report")
        for line in profile_checks:
            LOGGER.info("  %s", line)
    else:
        LOGGER.info("Baseline check: profile report SKIP (not provided)")

    success = ok_import and ok_profile
    LOGGER.info("Baseline verdict: %s", "PASS" if success else "FAIL")
    return 0 if success else 3


if __name__ == "__main__":
    raise SystemExit(main())
