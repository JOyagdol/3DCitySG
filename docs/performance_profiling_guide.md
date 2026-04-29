# Large-Scale Performance Profiling Guide (v1)

Baseline scope: import pipeline profiling for CityGML 2.0 experiments.

## 1. Goal

1. Quantify stage-level bottlenecks.
2. Compare tuning results in a reproducible way.
3. Provide evidence for research reporting.

## 2. Tool

Script: `scripts/profile_import_runs.py`

What it does:

1. Repeats import N times
2. Collects wall time and `summary.stage_durations` per run
3. Aggregates avg/min/max/std
4. Writes JSON report

## 3. Example Commands

Without Neo4j export:

```bash
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --config configs/default.yaml
```

With Neo4j export:

```bash
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --to-neo4j --config configs/default.yaml
```

Outputs:

1. Per-run: `data/output/profiling/import_run_<n>.json`
2. Aggregated: `data/output/import_profile_report.json`

## 4. Metrics

### 4.1 Per Run

1. `return_code`
2. `wall_time_seconds`
3. `node_count`, `edge_count`
4. `stage_durations`:
   - `parse_xml`
   - `collect_semantics`
   - `build_nodes`
   - `build_semantic_edges`
   - `build_geometry`
   - `export_neo4j`
   - `export_json`
   - `total`

### 4.2 Aggregated

For each metric:

1. `avg`
2. `min`
3. `max`
4. `std`

## 5. Recommended Tuning Scenarios

1. Compare `neo4j.batch_size` values: 2000 / 5000 / 10000
2. Compare different `spatial.*` epsilon sets
3. Run at least 3 repeats per setting and record mean/std

## 6. Interpretation

1. If `build_geometry` dominates:
   - inspect geometry volume and bbox computation cost
2. If `export_neo4j` dominates:
   - tune batch size and inspect DB resources
3. If std is high:
   - increase repeats and stabilize runtime environment

## 7. Deliverables Checklist

1. Baseline profile report
2. Post-tuning profile report
3. Improvement summary table (%)
4. Accuracy impact check (relation counts and scorecard)

## 8. Large-Scale Baseline Check (201dong)

Use the fixed baseline file to perform pass/fail checks on import + profiling outputs:

```bash
python scripts/check_large_scale_baseline.py --baseline configs/baselines/201dong_v1_baseline.json --import-summary data/output/E-TYPE_201dong_after_boundarytype.json --profile-report data/output/import_profile_report_201dong_after_boundarytype.json
```

Baseline source:

1. `configs/baselines/201dong_v1_baseline.json`
