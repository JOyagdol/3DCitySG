# v1 Experiment Results (Latest Only)

This document keeps only the latest experiment snapshot.
Historical records are archived in `docs/experiment_results_history.md`.

## 1) Latest Artifacts (2026-05-07)

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

| Dataset | Nodes | Edges | Overall | Spatial Coverage | CONNECTS | TOUCHES | ADJACENT_TO | INTERSECTS | Query Total | Avg Query ms | B/H/S nonzero | Profile total.avg (s) | Profile wall.avg (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| fzk_haus_lod2_v2 | 80 | 90 | 100.00 | 100.00 | 0 | 0 | 0 | 0 | 17 | 7.799 | 2/7, 0/5, 0/5 | 0.015518 | 0.032302 |
| e_type_201dong_ifc4 | 1,076,200 | 1,240,332 | 98.04 | 24.24 | 63 | 4 | 8 | 4 | 17 | 4.065 | 6/7, 4/5, 4/5 | 90.641901 | 141.727498 |
| snowdon_towers_ifc4 | 16,960,567 | 19,779,555 | 99.87 | 5.85 | 1,179 | 180 | 162 | 432 | 17 | 5.128 | 6/7, 4/5, 4/5 | 1510.058829 | 1510.058829 |

## 3) Notes

1. `CONNECTS` is present in the latest E-TYPE graph (`H4=63`).
2. E-TYPE baseline remains `FAIL` with current baseline policy:
   - `spatial_coverage_min=50.0`
   - latest `spatial_coverage=24.24`
3. Snowdon profiling was resumed after interruption and completed with `runs_success=3`.
