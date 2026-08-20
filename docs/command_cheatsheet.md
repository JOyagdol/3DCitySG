# Command Cheatsheet

This is the command source-of-truth for routine runs.
Run commands from the repository root after activating your Python environment.
All commands below are one-line commands.

## 1. Environment

```powershell
cd "C:\Users\OKLab\Desktop\AIDT Lab\City Scene Understanding\3DCitySG"
```

```powershell
conda activate 3DCitySG
```

## 2. Import Only

FZK Haus import without Neo4j:

```powershell
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/fzk_haus_import.json --config configs/default.yaml
```

FZK Haus import with Neo4j:

```powershell
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/fzk_haus_import.json --to-neo4j --config configs/default.yaml
```

E-type import with Neo4j:

```powershell
python scripts/run_import.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --output data/output/e_type_import.json --to-neo4j --config configs/default.yaml
```

SmartCity Lab import with Neo4j:

```powershell
python scripts/run_import.py --input "data/input/SMARTCITY_LAB_(RV2024)_mod-IFC4x3.gml" --output data/output/smartcity_lab_import.json --to-neo4j --config configs/default.yaml
```

## 3. Full Refresh

E-type refresh with Neo4j sync:

```powershell
python scripts/refresh_latest_reports.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --config configs/default.yaml --dataset-tag "e_type_201dong_ifc4" --to-neo4j --skip-baseline
```

SmartCity Lab refresh with Neo4j sync:

```powershell
python scripts/refresh_latest_reports.py --input "data/input/SMARTCITY_LAB_(RV2024)_mod-IFC4x3.gml" --config configs/default.yaml --dataset-tag "smartcity_lab_ifc4x3" --to-neo4j --skip-baseline
```

Fast refresh without profile/baseline:

```powershell
python scripts/refresh_latest_reports.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --config configs/default.yaml --dataset-tag "e_type_201dong_ifc4" --to-neo4j --skip-profile --skip-baseline
```

## 4. Dataset Batch Refresh

```powershell
python scripts/refresh_latest_reports.py --input "data/input/fzk_haus_lod2_v2.gml" --config configs/default.yaml --dataset-tag "fzk_haus_lod2_v2" --to-neo4j --skip-baseline
```

```powershell
python scripts/refresh_latest_reports.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --config configs/default.yaml --dataset-tag "e_type_201dong_ifc4" --to-neo4j --skip-baseline
```

```powershell
python scripts/refresh_latest_reports.py --input "data/input/Snowdon Towers Sample Architectural-IFC4.gml" --config configs/default.yaml --dataset-tag "snowdon_towers_ifc4" --to-neo4j --skip-baseline
```

```powershell
python scripts/refresh_latest_reports.py --input "data/input/SMARTCITY_LAB_(RV2024)_mod-IFC4x3.gml" --config configs/default.yaml --dataset-tag "smartcity_lab_ifc4x3" --to-neo4j --skip-baseline
```

## 5. Benchmark Only

```powershell
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
```

## 6. Import Profiling

Single dataset profiling:

```powershell
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --config configs/default.yaml
```

Resume profiling:

```powershell
python scripts/profile_import_runs.py --input "data/input/Snowdon Towers Sample Architectural-IFC4.gml" --runs 3 --config configs/default.yaml --output-dir "data/output/snowdon_towers_ifc4__profiling_YYYYMMDD_HHMMSS" --report "data/output/snowdon_towers_ifc4__import_profile_report_YYYYMMDD_HHMMSS.json" --resume
```

## 7. Room Retrieval Queries

Canonical retrieval scripts are under `scripts/retrieval/`.

Run all room retrieval scenarios:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_room_localization_query_report.json --scenario all --limit 10
```

E-type kitchen OVG scenario:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_kitchen_view_graph_query_report.json --scenario combined_room_score --limit 10 --view-graph docs/examples/observed_view_graph_kitchen.json
```

E-type living / TV-sofa OVG scenario:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_living_tv_sofa_query_report.json --scenario combined_room_score --limit 10 --view-graph docs/examples/observed_view_graph_e_type_living_tv_sofa.json
```

E-type sparse opening/window scenario:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_empty_window_room_query_report.json --scenario opening_boundary_room_score --view-graph docs/examples/observed_view_graph_e_type_empty_window_room.json
```

SmartCity Lab corridor/window scenario:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/smartcity_lab_corridor_window_query_report.json --scenario opening_boundary_room_score --view-graph docs/examples/observed_view_graph_smartcity_corridor_window.json
```

## 8. Retrieval Timing Profile

E-type kitchen timing profile:

```powershell
python scripts/retrieval/profile_room_localization_stages.py --config configs/default.yaml --scenario combined_room_score --view-graph docs/examples/observed_view_graph_kitchen.json --output data/output/e_type_kitchen_stage_profile.json --warmup 1 --repeat 3
```

E-type living timing profile:

```powershell
python scripts/retrieval/profile_room_localization_stages.py --config configs/default.yaml --scenario combined_room_score --view-graph docs/examples/observed_view_graph_e_type_living_tv_sofa.json --output data/output/e_type_living_stage_profile.json --warmup 1 --repeat 3
```

## 9. Retrieval Metrics and Docs

Evaluate E-type retrieval metrics:

```powershell
python scripts/retrieval/evaluate_room_retrieval_metrics.py --case-file docs/examples/e_type_room_retrieval_eval_cases.json --output data/output/e_type_room_retrieval_metrics.json --top-k 3
```

Regenerate retrieval result note from raw JSON:

```powershell
python scripts/retrieval/sync_room_retrieval_docs.py --output docs/retrieval/raw_json_sync_review_ko.md
```

## 10. Baseline Validation

```powershell
python scripts/check_large_scale_baseline.py --baseline configs/baselines/201dong_v1_baseline.json --import-summary data/output/e_type_201dong_ifc4__import_summary_YYYYMMDD_HHMMSS.json --profile-report data/output/e_type_201dong_ifc4__import_profile_report_YYYYMMDD_HHMMSS.json
```

## 11. Documentation References

1. Project structure: `docs/project_structure.md`
2. Architecture: `docs/architecture.md`
3. Retrieval domain: `docs/retrieval/README.md`
4. WorldGraph domain: `docs/world_graph/README.md`
5. OVG domain: `docs/ovg/README.md`
6. Raw retrieval result sync: `docs/retrieval/raw_json_sync_review_ko.md`
7. Pipeline refactor review: `docs/pipeline_refactor_review.md`
