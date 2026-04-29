# v1 Measurement Runbook

This runbook defines reproducible steps for generating benchmark and profiling outputs in the v1 baseline.

## 1. Goal

1. Generate query benchmark results (`benchmark_report.json`)
2. Generate import profiling results (`import_profile_report.json`)
3. Collect inputs for `docs/experiment_results.md`

## 2. Prerequisites

1. Project root:
   - `C:\Users\OKLab\Desktop\AIDT Lab\City Scene Understanding\3DCitySG`
2. Conda environment:
   - `3DCitySG`
3. Neo4j:
   - running locally
   - matches connection settings in `configs/default.yaml`

## 3. Commands

```powershell
cd "C:\Users\OKLab\Desktop\AIDT Lab\City Scene Understanding\3DCitySG"
conda activate 3DCitySG
```

### 3.1 Import + Neo4j Export (single baseline run)

```powershell
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json --to-neo4j --config configs/default.yaml
```

### 3.2 Query Benchmark

```powershell
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
```

### 3.3 Import Profiling

```powershell
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --config configs/default.yaml
```

For profiling including Neo4j export:

```powershell
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --to-neo4j --config configs/default.yaml
```

## 4. Outputs

1. Import output:
   - `data/output/my_import.json`
2. Benchmark output:
   - `data/output/benchmark_report.json`
3. Profiling outputs:
   - per-run: `data/output/profiling/import_run_<n>.json`
   - aggregate: `data/output/import_profile_report.json`

## 5. Completion Checklist

1. `Import complete` appears in import logs
2. `summary.query_failed = 0` in benchmark report
3. `summary.runs_failed = 0` in profiling report
4. Recorded metrics are copied into `docs/experiment_results.md`

## 6. Fixed Baseline Example (2026-04-29, E-TYPE_201dong)

Use these values as a stable comparison reference.

### 6.1 Executed Commands

```powershell
python scripts/run_import.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --output data/output/E-TYPE_201dong_after_boundarytype.json --config configs/default.yaml
python scripts/profile_import_runs.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --runs 3 --config configs/default.yaml --output-dir data/output/profiling_201dong_after_boundarytype --report data/output/import_profile_report_201dong_after_boundarytype.json
python scripts/check_large_scale_baseline.py --baseline configs/baselines/201dong_v1_baseline.json --import-summary data/output/E-TYPE_201dong_after_boundarytype.json --profile-report data/output/import_profile_report_201dong_after_boundarytype.json
```

### 6.2 Snapshot Results

1. Import (`--to-neo4j` disabled):
   - nodes=`1,076,200`, edges=`1,240,261`
   - BoundarySurfaceType nodes=`5`
   - HAS_SURFACE_TYPE edges=`190`
   - scorecard overall=`98.04`
   - spatial coverage=`57.14 (8/14)`
   - spatial precision-like sanity=`100.00`
   - total runtime=`85.629s` (single run)
2. Profiling (`--to-neo4j` disabled, 3 runs):
   - wall time avg=`134.699091s` (min=`132.979980s`, max=`136.587765s`, std=`1.477744s`)
   - stage avg:
     - `parse_xml=4.550062s`
     - `collect_semantics=1.001046s`
     - `build_nodes=0.006266s`
     - `build_semantic_edges=0.372700s`
     - `build_geometry=20.811885s`
     - `export_json=47.413900s`
     - `total=84.934705s`
3. Baseline verdict:
   - `scripts/check_large_scale_baseline.py` -> `PASS`
