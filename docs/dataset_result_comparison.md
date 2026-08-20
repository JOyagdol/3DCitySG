> Latest retrieval numbers should be read from docs/retrieval/raw_json_sync_review_ko.md first. Some legacy tables in this document may still contain older heuristic values until the raw-JSON sync script regenerates them.

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

Notes:
1. The E-TYPE row uses the latest 2026-05-15 import result.
2. E-TYPE benchmark/profile values are still the 2026-05-07 full refresh values.

| Date | Dataset Tag | Input | Import Summary | Benchmark Report | Profile Report | Nodes | Edges | Overall | Spatial Coverage | B-tier nonzero | H-tier nonzero | S-tier nonzero | CONNECTS | TOUCHES | ADJACENT_TO | INTERSECTS | Avg Query ms | Wall Avg s | Baseline | Notes |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 2026-05-07 | fzk_haus_lod2_v2 | `fzk_haus_lod2_v2.gml` | `data/output/fzk_haus_lod2_v2__import_summary_20260507_034201.json` | `data/output/fzk_haus_lod2_v2__benchmark_report_20260507_034201.json` | `data/output/fzk_haus_lod2_v2__import_profile_report_20260507_034201.json` | 80 | 90 | 100.00 | 100.00 | 2/7 | 0/5 | 0/5 | 0 | 0 | 0 | 0 | 7.799 | 0.032 | N/A | Compact LoD2 sample. Spatial candidate pairs are absent, so hard/scenario tiers are zero. |
| 2026-05-15 import / 2026-05-07 benchmark / 2026-06-04 query | e_type_201dong_ifc4 | `(210812)E-TYPE_201dong-IFC4.gml` | `data/output/import_summary.json` | `data/output/e_type_201dong_ifc4__benchmark_report_20260507_034415.json` | `data/output/e_type_201dong_ifc4__import_profile_report_20260507_034415.json` | 1,076,200 | 1,240,562 | 98.04 | 23.81 | 6/7 | 4/5 | 4/5 | 37 | 18 | 74 | 4 | 4.065 | 141.727 | FAIL | Latest v2 spatial import reflected. `HOSTED_BY=24`, `ADJACENT_SURFACE=142`, `ATTACHED_TO=10`, `spatial_plausible_coverage=90.43`. Room localization scenario: E103 ranked first (`score=11.0`) for kitchen-like query. Benchmark/profile not rerun yet. |
| 2026-05-07 | snowdon_towers_ifc4 | `Snowdon Towers Sample Architectural-IFC4.gml` | `data/output/snowdon_towers_ifc4__import_summary_20260507_104353.json` | `data/output/snowdon_towers_ifc4__benchmark_report_20260507_104353.json` | `data/output/snowdon_towers_ifc4__import_profile_report_20260507_104353.json` | 16,960,567 | 19,779,555 | 99.87 | 5.85 | 6/7 | 4/5 | 4/5 | 1,179 | 180 | 162 | 432 | 5.128 | 1510.059 | N/A | Profile resumed from interrupted run; aggregate generated successfully (`runs_success=3`). |

## 3) History Policy

1. Do not keep old rows here.
2. Move previous rows to `docs/dataset_result_history.md`.

## 4) Room Localization Query Snapshot

Source:

1. `data/output/e_type_kitchen_view_query_report.json`
2. `docs/room_localization_query_results.md`

Latest recorded room-localization query:

| Dataset | Scenario | Input Mode | Top Room | Top Score | Second Room | Second Score | Note |
|---|---|---|---|---:|---|---:|---|
| e_type_201dong_ifc4 | `combined_room_score` | heuristic categories (`storage`, `fridge`, `table`, `sofa`) | E103 | 11.0 | E102 | 9.5 | E103 has strong `fridge/storage` evidence and floor attachment; E102 remains plausible with `sofa/table/fridge` and one furniture-pair relation. |
