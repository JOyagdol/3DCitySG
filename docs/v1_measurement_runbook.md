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

## 6. Fixed Baseline Example (2026-03-26, E-TYPE_201dong)

Use these values as a stable comparison reference.

### 6.1 Executed Commands

```powershell
python -m pytest -q
python -m pytest tests/test_spatial_relation_pairs.py -q
python scripts/run_import.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --output data/output/E-TYPE_201dong.json --to-neo4j --config configs/default.yaml
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
python scripts/profile_import_runs.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --runs 3 --config configs/default.yaml
```

### 6.2 Snapshot Results

1. Tests:
   - `python -m pytest -q` -> `13 passed`
   - `python -m pytest tests/test_spatial_relation_pairs.py -q` -> `6 passed`
2. Import (`--to-neo4j`):
   - nodes=`1,076,195`, edges=`1,240,071`
   - scorecard overall=`97.97`
   - spatial coverage=`57.14 (8/14)`
   - spatial precision-like sanity=`100.00`
   - total runtime=`306.559s`
3. Benchmark:
   - Q1 avg=`10.629ms`, Q2 avg=`5.744ms`, Q3 avg=`5.441ms`, Q4 avg=`7.424ms`, Q5 avg=`5.775ms`
   - all result counts were `0`
   - Neo4j warnings reported missing `CONNECTS` relation type (Q4/Q5)
4. Profiling (`--to-neo4j` disabled):
   - wall time avg=`153.028553s` (min=`149.791812s`, max=`156.003975s`, std=`2.542828s`)
   - stage avg: `parse_xml=5.753844s`, `collect_semantics=1.135243s`,
     `build_nodes=0.007367s`, `build_semantic_edges=0.455520s`,
     `build_geometry=23.289802s`, `export_json=53.351159s`, `total=96.247233s`

