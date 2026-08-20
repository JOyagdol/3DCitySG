"""Regenerate retrieval result notes from raw JSON reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


DEFAULT_REPORTS: tuple[dict[str, str], ...] = (
    {
        "label": "E-type kitchen view",
        "target_room": "E103",
        "path": "data/output/e_type_kitchen_view_graph_query_report.json",
    },
    {
        "label": "E-type living / TV-sofa view",
        "target_room": "E102",
        "path": "data/output/e_type_living_tv_sofa_query_report.json",
    },
    {
        "label": "E-type sparse opening / window view",
        "target_room": "E204",
        "path": "data/output/e_type_empty_window_room_query_report.json",
    },
    {
        "label": "SmartCityLab corridor / column view",
        "target_room": "20",
        "path": "data/output/smartcity_lab_corridor_window_query_report.json",
    },
)

DEFAULT_METRICS_PATH = "data/output/e_type_room_retrieval_metrics.json"
DEFAULT_OUTPUT_PATH = "docs/retrieval/raw_json_sync_review_ko.md"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _first_scenario(report: dict[str, Any]) -> dict[str, Any]:
    scenarios = report.get("scenarios")
    if isinstance(scenarios, list) and scenarios:
        scenario = scenarios[0]
        if isinstance(scenario, dict):
            return scenario
    return {}


def _rows(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    rows = scenario.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _room_name(row: dict[str, Any]) -> str:
    return str(row.get("room_name") or row.get("room_id") or "-")


def _score(row: dict[str, Any]) -> str:
    value = row.get("total_score")
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return str(value)
    return "-"


def _ms(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.3f} ms"
    return "raw query time not stored"


def _rank_cell(row: dict[str, Any] | None) -> str:
    if row is None:
        return "-"
    return f"{_room_name(row)} `{_score(row)}`"


def _target_rank(rows: list[dict[str, Any]], target_room: str) -> str:
    matches = [
        index
        for index, row in enumerate(rows, start=1)
        if str(row.get("room_name")) == target_room or str(row.get("room_id")) == target_room
    ]
    if not matches:
        return "-"
    target_score = _score(rows[matches[0] - 1])
    tie_ranks = [
        index
        for index, row in enumerate(rows, start=1)
        if _score(row) == target_score
    ]
    if len(tie_ranks) > 1:
        return f"tie group {min(tie_ranks)}"
    return str(matches[0])


def _matched_categories(row: dict[str, Any]) -> str:
    matched_objects = row.get("matched_objects")
    if not isinstance(matched_objects, list):
        return "-"
    categories = []
    for item in matched_objects:
        if isinstance(item, dict) and item.get("category") is not None:
            categories.append(str(item["category"]))
    return ", ".join(categories) if categories else "-"


def _breakdown(row: dict[str, Any]) -> str:
    breakdown = row.get("score_breakdown")
    if not isinstance(breakdown, dict):
        return "-"
    parts = []
    for key, value in breakdown.items():
        if isinstance(value, float):
            value_text = f"{value:.6f}".rstrip("0").rstrip(".")
        else:
            value_text = str(value)
        parts.append(f"{key} `{value_text}`")
    return ", ".join(parts) if parts else "-"


def _evidence(row: dict[str, Any]) -> str:
    categories = _matched_categories(row)
    if categories != "-":
        return categories
    values = []
    for key in (
        "window_count",
        "door_count",
        "wall_surface_count",
        "floor_surface_count",
        "wall_floor_adjacency_count",
        "target_installation_count",
    ):
        if row.get(key) is not None:
            values.append(f"{key}={row[key]}")
    return ", ".join(values) if values else "-"


def _build_doc(report_specs: tuple[dict[str, str], ...], metrics_path: Path) -> str:
    lines: list[str] = [
        "# Raw JSON 기반 Retrieval 결과 재동기화 검토",
        "",
        "이 문서는 raw JSON 결과 파일을 기준으로 자동 재생성된다.",
        "",
        "## 1. Source-of-Truth Raw Files",
        "",
        "| 구분 | Raw JSON | 상태 |",
        "|---|---|---|",
    ]

    loaded_reports: list[tuple[dict[str, str], dict[str, Any], dict[str, Any], list[dict[str, Any]]]] = []
    for spec in report_specs:
        path = PROJECT_ROOT / spec["path"]
        if path.exists():
            report = _load_json(path)
            scenario = _first_scenario(report)
            rows = _rows(scenario)
            status = "loaded"
            loaded_reports.append((spec, report, scenario, rows))
        else:
            status = "missing"
        lines.append(f"| {spec['label']} | `{spec['path']}` | {status} |")

    metrics = _load_json(metrics_path) if metrics_path.exists() else {}
    lines.append(f"| E-type retrieval metrics | `{metrics_path.relative_to(PROJECT_ROOT)}` | {'loaded' if metrics else 'missing'} |")

    lines.extend(
        [
            "",
            "## 2. Raw JSON 기준 최신 후보 결과",
            "",
            "| Scenario | Target Room | Rank 1 | Rank 2 | Rank 3 | Target Rank | Retrieval Time |",
            "|---|---|---|---|---|---:|---:|",
        ]
    )
    for spec, _report, scenario, rows in loaded_reports:
        lines.append(
            "| {label} | {target} | {r1} | {r2} | {r3} | {target_rank} | {elapsed} |".format(
                label=spec["label"],
                target=spec["target_room"],
                r1=_rank_cell(rows[0] if len(rows) > 0 else None),
                r2=_rank_cell(rows[1] if len(rows) > 1 else None),
                r3=_rank_cell(rows[2] if len(rows) > 2 else None),
                target_rank=_target_rank(rows, spec["target_room"]),
                elapsed=_ms(scenario.get("query_elapsed_ms")),
            )
        )

    lines.extend(
        [
            "",
            "해석:",
            "",
            "1. Target room이 1위이면 top-1 retrieval 성공으로 본다.",
            "2. Target room이 3위 이내이면 top-3 inclusion 성공으로 본다.",
            "3. 동일 score 후보가 여러 개면 동점 그룹으로 해석하고, 추가 view 또는 signature similarity가 필요하다.",
            "4. 과거 heuristic 수치와 다를 경우 raw JSON 값을 우선한다.",
            "",
            "## 3. Scenario별 Top Evidence",
            "",
            "| Scenario | Top Room | Score | Evidence | Score Breakdown |",
            "|---|---|---:|---|---|",
        ]
    )
    for spec, _report, _scenario, rows in loaded_reports:
        top = rows[0] if rows else {}
        lines.append(
            f"| {spec['label']} | {_room_name(top)} | {_score(top)} | {_evidence(top)} | {_breakdown(top)} |"
        )

    summary = metrics.get("summary") if isinstance(metrics.get("summary"), dict) else {}
    lines.extend(
        [
            "",
            "## 4. 집계 Metric 기준",
            "",
            "`data/output/e_type_room_retrieval_metrics.json`는 현재 명시적으로 등록된 evaluation cases만 포함한다.",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Case count | {summary.get('case_count', '-')} |",
            f"| Top-1 Room Accuracy | {summary.get('top1_room_accuracy_pct', '-')}% |",
            f"| Top-3 Room Inclusion | {summary.get('top3_room_inclusion_pct', '-')}% |",
            f"| Mean Target Room Rank | {summary.get('mean_target_room_rank', '-')} |",
            f"| MRR | {summary.get('mrr', '-')} |",
            f"| Mean Retrieval Time | {_ms(summary.get('retrieval_time_ms_mean'))} |",
            f"| Total Retrieval Time | {_ms(summary.get('retrieval_time_ms_total'))} |",
            f"| Mean Total Elapsed Time | {_ms(summary.get('total_elapsed_ms_mean'))} |",
            "",
            "주의:",
            "",
            "1. Metrics JSON에 없는 scenario는 평균 성능 계산에 포함되지 않는다.",
            "2. 전체 논문용 평균을 내기 전에 evaluation case JSON에 대상 scenario를 명시적으로 추가해야 한다.",
            "",
            "## 5. 재동기화 필요 문서",
            "",
            "| 문서 | 처리 방침 |",
            "|---|---|",
            "| `docs/room_localization_query_results_ko.md` | raw JSON 기준 표로 재생성 필요 |",
            "| `docs/e_type_201dong_dataset_profile_ko.md` | dataset profile은 유지하되 retrieval 결과 표는 raw JSON 기준으로 재생성 필요 |",
            "| `docs/room_localization_query_scenarios.md` | scenario 정의는 유지, 결과값은 최신 raw JSON 값으로 교체 필요 |",
            "| `docs/experiment_results.md` / `docs/experiment_results_ko.md` | 대표 결과 표가 있으면 raw JSON 값으로 동기화 필요 |",
            "| `docs/dataset_result_comparison.md` / `docs/dataset_result_comparison_ko.md` | dataset별 최신 결과만 남기고 이력값은 history 문서로 분리 필요 |",
            "",
            "## 6. 운영 정책",
            "",
            "1. 최신 수치는 raw JSON report를 source-of-truth로 둔다.",
            "2. 논문용 문서에는 raw JSON에서 재생성한 표만 사용한다.",
            "3. 과거 수치 전체 테이블은 history/raw archive로 분리한다.",
            "4. 새 scenario를 추가하면 이 스크립트의 report 목록 또는 evaluation case JSON도 함께 갱신한다.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Regenerate room retrieval result docs from raw JSON reports.")
    parser.add_argument("--metrics", default=DEFAULT_METRICS_PATH, help="Metrics JSON path.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH, help="Markdown output path.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path = PROJECT_ROOT / args.metrics
    output_path.write_text(_build_doc(DEFAULT_REPORTS, metrics_path), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
