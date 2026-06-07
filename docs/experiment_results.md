# v1 Experiment Results (Latest Only)

This document keeps only the latest experiment snapshot.
Historical records are archived in `docs/experiment_results_history.md`.

## 1) Latest Artifacts

Current E-TYPE v2 spatial import result:

1. E-TYPE v2 spatial import-only (2026-05-15):
   - `data/output/import_summary.json`

Dataset-level full refresh artifacts with benchmark/profile are still the 2026-05-07 snapshots.

1. FZK:
   - `data/output/fzk_haus_lod2_v2__import_summary_20260507_034201.json`
   - `data/output/fzk_haus_lod2_v2__benchmark_report_20260507_034201.json`
   - `data/output/fzk_haus_lod2_v2__import_profile_report_20260507_034201.json`
2. E-TYPE:
   - `data/output/e_type_201dong_ifc4__import_summary_20260507_034415.json`
   - `data/output/e_type_201dong_ifc4__benchmark_report_20260507_034415.json`
   - `data/output/e_type_201dong_ifc4__import_profile_report_20260507_034415.json`
3. Snowdon:
   - `data/output/snowdon_towers_ifc4__import_summary_20260507_104353.json`
   - `data/output/snowdon_towers_ifc4__benchmark_report_20260507_104353.json`
   - `data/output/snowdon_towers_ifc4__import_profile_report_20260507_104353.json`

## 2) Snapshot Table

Notes:
1. E-TYPE import metrics are from `data/output/import_summary.json` generated on 2026-05-15.
2. Query/profile metrics are still from the 2026-05-07 full refresh because benchmark/profile were not rerun after the latest import-only spatial update.

| Dataset | Nodes | Edges | Overall | Spatial Coverage | CONNECTS | TOUCHES | ADJACENT_TO | INTERSECTS | Query Total (last benchmark) | Avg Query ms (last benchmark) | B/H/S nonzero (last benchmark) | Profile total.avg (s) | Profile wall.avg (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| fzk_haus_lod2_v2 | 80 | 90 | 100.00 | 100.00 | 0 | 0 | 0 | 0 | 17 | 7.799 | 2/7, 0/5, 0/5 | 0.015518 | 0.032302 |
| e_type_201dong_ifc4 | 1,076,200 | 1,240,562 | 98.04 | 23.81 | 37 | 18 | 74 | 4 | 17 | 4.065 | 6/7, 4/5, 4/5 | 90.641901 | 141.727498 |
| snowdon_towers_ifc4 | 16,960,567 | 19,779,555 | 99.87 | 5.85 | 1,179 | 180 | 162 | 432 | 17 | 5.128 | 6/7, 4/5, 4/5 | 1510.058829 | 1510.058829 |

## 3) Latest E-TYPE v2 Spatial Import Details

Source file: `data/output/import_summary.json`

1. Overall:
   - nodes=`1,076,200`
   - edges=`1,240,562`
   - overall=`98.04`
2. Spatial scores:
   - `spatial_coverage=23.81` (`85/357`)
   - `spatial_plausible_coverage=90.43` (`85/94`)
   - `spatial_density=28.85`
   - `spatial_precision_sanity=100.00`
   - `spatial_quality=100.00`
3. Relation counts:
   - `CONNECTS=37`
   - `HOSTED_BY=24`
   - `ADJACENT_TO=74`
   - `TOUCHES=18`
   - `INTERSECTS=4`
   - `ADJACENT_SURFACE=142`
   - `ATTACHED_TO=10`
4. Confirmed policy effects:
   - Floor representative selection now attaches the sofa/table/smart table fridge to the top finish floor (`Floor:U-FL-T110 건식난방-T10강화마루 2:1910481`) instead of the insulation layer.
   - `ADJACENT_SURFACE` keeps representative-surface collapse and requires polygon shared-edge validation.

## 4) Notes

1. Door-only `CONNECTS` is present in the latest E-TYPE import (`CONNECTS=37`).
2. E-TYPE baseline remains `FAIL` with current baseline policy:
   - `spatial_coverage_min=50.0`
   - latest import `spatial_coverage=23.81`
   - `spatial_plausible_coverage=90.43`, so most threshold-aware plausible relations are materialized.
3. Snowdon profiling was resumed after interruption and completed with `runs_success=3`.

## 5) Room Localization Query Scenario Result

Source:

1. Detailed paper notes: `docs/room_localization_query_results.md`
2. Raw report: `data/output/e_type_kitchen_view_query_report.json`
3. Scenario guide: `docs/room_localization_query_scenarios.md`

Current scenario:

1. dataset: `e_type_201dong_ifc4`
2. scenario: `combined_room_score`
3. input mode: heuristic object category query
4. furniture keywords: `storage`, `fridge`, `table`, `sofa`
5. row_count: `10`
6. elapsed_ms: `3170.910`

Top ranking:

| Rank | Room | Score | Matched Categories | Object | Door | Floor | Relation | Interpretation |
|---:|---|---:|---|---:|---:|---:|---:|---|
| 1 | E103 | 11.0 | fridge, storage | 8.0 | 1.0 | 2.0 | 0.0 | strongest kitchen-like evidence |
| 2 | E102 | 9.5 | sofa, table, fridge | 6.0 | 1.0 | 1.5 | 1.0 | plausible mixed living/kitchen candidate |

Interpretation:

1. E103 ranks first because it contains strong kitchen-like cues (`fridge`, `storage`) and both matched objects are floor-attached.
2. E102 remains a plausible secondary candidate because it contains `sofa`, `table`, and `fridge`, plus one matched furniture-pair spatial relation.
3. The result supports the paper claim that a CityGML-derived semantic-spatial world graph can act as a queryable room-localization prior.
4. This is not final image-based localization accuracy; it is a Cypher scenario test using heuristic observed categories.
