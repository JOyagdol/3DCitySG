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

## 3) Benchmark Only

```powershell
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
```

## 4) Profiling Only

```powershell
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --config configs/default.yaml
```

Resume remaining runs from an existing profiling directory:

```powershell
python scripts/profile_import_runs.py --input "data/input/Snowdon Towers Sample Architectural-IFC4.gml" --runs 3 --config configs/default.yaml --output-dir "data/output/snowdon_towers_ifc4__profiling_20260507_104353" --report "data/output/snowdon_towers_ifc4__import_profile_report_20260507_104353.json" --resume
```

## 5) One-command Full Refresh (Recommended)

Runs import + benchmark + profiling and updates default outputs.

```powershell
python scripts/refresh_latest_reports.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --config configs/default.yaml --dataset-tag "e_type_201dong_ifc4" --to-neo4j --skip-baseline
```

Useful options:

1. `--skip-profile --skip-baseline`: faster refresh
2. `--no-promote-defaults`: keep timestamped outputs only
3. `--dataset-tag "<tag>"`: force output prefix
4. `--profile-resume --profile-output-dir "<dir>" --profile-report "<json>"`: resume interrupted profiling run

## 6) Dataset Batch Commands (Current 3)

```powershell
python scripts/refresh_latest_reports.py --input "data/input/fzk_haus_lod2_v2.gml" --config configs/default.yaml --dataset-tag "fzk_haus_lod2_v2" --to-neo4j --skip-baseline
python scripts/refresh_latest_reports.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --config configs/default.yaml --dataset-tag "e_type_201dong_ifc4" --to-neo4j --skip-baseline
python scripts/refresh_latest_reports.py --input "data/input/Snowdon Towers Sample Architectural-IFC4.gml" --config configs/default.yaml --dataset-tag "snowdon_towers_ifc4" --to-neo4j --skip-baseline
```

## 7) Baseline Validation (201dong only)

```powershell
python scripts/check_large_scale_baseline.py --baseline configs/baselines/201dong_v1_baseline.json --import-summary data/output/e_type_201dong_ifc4__import_summary_YYYYMMDD_HHMMSS.json --profile-report data/output/e_type_201dong_ifc4__import_profile_report_YYYYMMDD_HHMMSS.json
```
