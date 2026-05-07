# Dataset Result Comparison Tracker (Latest Only)

Purpose:
1. Keep only the latest result per dataset in this document.
2. Use this as the current operational view.
3. Store historical snapshots separately in `docs/dataset_result_history.md`.

## 1) Run Policy

1. Reuse the same `--dataset-tag` for the same input dataset.
2. Use `--to-neo4j` when benchmark must run on freshly synchronized DB state.
3. After each run, update the row for that dataset (replace previous latest row).

Recommended command:

```powershell
conda run -n 3DCitySG python scripts/refresh_latest_reports.py --input "<input.gml>" --config configs/default.yaml --dataset-tag "<dataset_tag>" --to-neo4j
```

## 2) Latest Comparison Table

| Date | Dataset Tag | Input | Import Summary | Benchmark Report | Profile Report | Nodes | Edges | Overall | Spatial Coverage | B-tier nonzero | H-tier nonzero | S-tier nonzero | CONNECTS | TOUCHES | ADJACENT_TO | INTERSECTS | Avg Query ms | Wall Avg s | Baseline | Notes |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 2026-05-07 | fzk_haus_lod2_v2 | `fzk_haus_lod2_v2.gml` | `data/output/fzk_haus_lod2_v2__import_summary_20260507_034201.json` | `data/output/fzk_haus_lod2_v2__benchmark_report_20260507_034201.json` | `data/output/fzk_haus_lod2_v2__import_profile_report_20260507_034201.json` | 80 | 90 | 100.00 | 100.00 | 2/7 | 0/5 | 0/5 | 0 | 0 | 0 | 0 | 7.799 | 0.032 | N/A | Compact LoD2 sample. Spatial candidate pairs are absent, so hard/scenario tiers are zero. |
| 2026-05-07 | e_type_201dong_ifc4 | `(210812)E-TYPE_201dong-IFC4.gml` | `data/output/e_type_201dong_ifc4__import_summary_20260507_034415.json` | `data/output/e_type_201dong_ifc4__benchmark_report_20260507_034415.json` | `data/output/e_type_201dong_ifc4__import_profile_report_20260507_034415.json` | 1,076,200 | 1,240,332 | 98.04 | 24.24 | 6/7 | 4/5 | 4/5 | 63 | 4 | 8 | 4 | 4.065 | 141.727 | FAIL | Query set includes scenario tier (`S1..S5`). Profile total.avg is within threshold, but baseline fails due spatial coverage threshold mismatch. |
| 2026-05-07 | snowdon_towers_ifc4 | `Snowdon Towers Sample Architectural-IFC4.gml` | `data/output/snowdon_towers_ifc4__import_summary_20260507_104353.json` | `data/output/snowdon_towers_ifc4__benchmark_report_20260507_104353.json` | `data/output/snowdon_towers_ifc4__import_profile_report_20260507_104353.json` | 16,960,567 | 19,779,555 | 99.87 | 5.85 | 6/7 | 4/5 | 4/5 | 1,179 | 180 | 162 | 432 | 5.128 | 1510.059 | N/A | Profile resumed from interrupted run; aggregate generated successfully (`runs_success=3`). |

## 3) History Policy

1. Do not keep old rows here.
2. Move previous rows to `docs/dataset_result_history.md`.
