# Command Cheatsheet (v1)

This is the single command reference for routine runs.
Use this document first, then open each guide for interpretation details.

## 1) Environment

```powershell
cd "C:\Users\OKLab\Desktop\AIDT Lab\City Scene Understanding\3DCitySG"
conda activate 3DCitySG
```

## 2) Import Only (`run_import.py`)

Use when you only need one import output.

```powershell
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json --config configs/default.yaml
```

With Neo4j export:

```powershell
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json --to-neo4j --config configs/default.yaml
```

SmartCity Lab full refresh:

```powershell
python scripts/refresh_latest_reports.py --input "data/input/SMARTCITY_LAB_(RV2024)_mod-IFC4x3.gml" --config configs/default.yaml --dataset-tag "smartcity_lab_ifc4x3" --to-neo4j --skip-baseline
```

## 3) Benchmark Only

```powershell
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
```

## 4) Room Localization Cypher Scenarios

Run view-graph matching style room-candidate ranking against the Neo4j world graph.

```powershell
python scripts/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_room_localization_query_report.json --scenario all --limit 10
```

Run the current kitchen-like heuristic query used in the latest paper note:

```powershell
python scripts/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_kitchen_view_query_report.json --scenario combined_room_score --limit 10 --furniture-keywords storage fridge table sofa
```

Run room ranking from an observed view graph JSON:

```powershell
python scripts/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_kitchen_view_graph_query_report.json --scenario combined_room_score --limit 10 --view-graph docs/examples/observed_view_graph_kitchen.json
```

Run the SmartCity Lab window/boundary view scenario:

```powershell
python scripts/room_localization_queries.py --config configs/default.yaml --output data/output/smartcity_lab_corridor_window_query_report.json --scenario opening_boundary_room_score --view-graph docs/examples/observed_view_graph_smartcity_corridor_window.json
```

Result interpretation:

1. `docs/room_localization_query_scenarios.md`
2. `docs/room_localization_query_results.md`

## 5) Profiling Only

```powershell
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --config configs/default.yaml
```

Resume remaining runs from an existing profiling directory:

```powershell
python scripts/profile_import_runs.py --input "data/input/Snowdon Towers Sample Architectural-IFC4.gml" --runs 3 --config configs/default.yaml --output-dir "data/output/snowdon_towers_ifc4__profiling_20260507_104353" --report "data/output/snowdon_towers_ifc4__import_profile_report_20260507_104353.json" --resume
```

## 6) One-command Full Refresh (Recommended)

Runs import + benchmark + profiling and updates default outputs.

```powershell
python scripts/refresh_latest_reports.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --config configs/default.yaml --dataset-tag "e_type_201dong_ifc4" --to-neo4j --skip-baseline
```

Useful options:

1. `--skip-profile --skip-baseline`: faster refresh
2. `--no-promote-defaults`: keep timestamped outputs only
3. `--dataset-tag "<tag>"`: force output prefix
4. `--profile-resume --profile-output-dir "<dir>" --profile-report "<json>"`: resume interrupted profiling run

## 7) Dataset Batch Commands (Current 3)

```powershell
python scripts/refresh_latest_reports.py --input "data/input/fzk_haus_lod2_v2.gml" --config configs/default.yaml --dataset-tag "fzk_haus_lod2_v2" --to-neo4j --skip-baseline
python scripts/refresh_latest_reports.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --config configs/default.yaml --dataset-tag "e_type_201dong_ifc4" --to-neo4j --skip-baseline
python scripts/refresh_latest_reports.py --input "data/input/Snowdon Towers Sample Architectural-IFC4.gml" --config configs/default.yaml --dataset-tag "snowdon_towers_ifc4" --to-neo4j --skip-baseline
```

## 8) Baseline Validation (201dong only)

```powershell
python scripts/check_large_scale_baseline.py --baseline configs/baselines/201dong_v1_baseline.json --import-summary data/output/e_type_201dong_ifc4__import_summary_YYYYMMDD_HHMMSS.json --profile-report data/output/e_type_201dong_ifc4__import_profile_report_YYYYMMDD_HHMMSS.json
```
