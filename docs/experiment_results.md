# v1 Experiment Results Record

This document records measured v1 baseline results.

## 1. Experiment Metadata

1. Date: 2026-03-26
2. Operator: OKLab
3. Git commit: `84e37e2`
4. Dataset: `data/input/(210812)E-TYPE_201dong-IFC4.gml`
5. Neo4j version/DB: Local Neo4j (version not logged) / `neo4j`
6. Config file: `configs/default.yaml`

## 2. Command Log

```powershell
# import + neo4j
python scripts/run_import.py --input "<input.gml>" --output "<output.json>" --to-neo4j --config configs/default.yaml

# benchmark
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3

# profiling
python scripts/profile_import_runs.py --input "<input.gml>" --runs 3 --config configs/default.yaml
```

## 3. Import Summary

| Metric | Value |
|---|---|
| node_count | 1,076,195 |
| edge_count | 1,240,071 |
| scorecard.overall_score | 97.97 |
| scorecard.spatial_coverage.score | 57.14 (8/14) |
| scorecard.spatial_precision_sanity.score | 100.00 (inferred=8, metadata_valid=8, schema_valid=8, pair_conflicts=0) |
| import total runtime | 306.559s (`--to-neo4j`) |

## 4. Query Benchmark Results

Source: `data/output/benchmark_report.json`

| Query ID | Query Name | Result Count | Avg(ms) | Min(ms) | Max(ms) | Std(ms) | Note |
|---|---|---:|---:|---:|---:|---:|---|
| Q1 | furniture_furniture_intersects_pairs | 0 | 10.629 | 8.878 | 11.645 | 1.243 | No matching pairs in this dataset |
| Q2 | furniture_opening_touches | 0 | 5.744 | 4.750 | 6.800 | 0.838 | No matching pairs in this dataset |
| Q3 | furniture_boundary_adjacent | 0 | 5.441 | 4.113 | 6.869 | 1.127 | No matching pairs in this dataset |
| Q4 | opening_room_connects | 0 | 7.424 | 6.305 | 8.317 | 0.837 | `CONNECTS` relation type warning in Neo4j notification |
| Q5 | room_internal_furniture_touching_opening | 0 | 5.775 | 5.237 | 6.130 | 0.387 | Join path depends on `CONNECTS` |

## 5. Import Profiling Results

Source: `data/output/import_profile_report.json`

### 5.1 Aggregated Summary

| Metric | Avg | Min | Max | Std |
|---|---:|---:|---:|---:|
| wall_time_seconds | 153.028553 | 149.791812 | 156.003975 | 2.542828 |
| node_count | 1076195.0 | 1076195.0 | 1076195.0 | 0.0 |
| edge_count | 1240071.0 | 1240071.0 | 1240071.0 | 0.0 |

### 5.2 Stage Durations

| Stage | Avg(s) | Min(s) | Max(s) | Std(s) |
|---|---:|---:|---:|---:|
| parse_xml | 5.753844 | 5.142485 | 6.840876 | 0.770641 |
| collect_semantics | 1.135243 | 1.069884 | 1.208718 | 0.056969 |
| build_nodes | 0.007367 | 0.006687 | 0.008230 | 0.000643 |
| build_semantic_edges | 0.455520 | 0.418494 | 0.497008 | 0.032208 |
| build_geometry | 23.289802 | 22.494518 | 24.832995 | 1.091374 |
| export_neo4j | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| export_json | 53.351159 | 51.160102 | 54.894664 | 1.591903 |
| total | 96.247233 | 92.040884 | 99.054131 | 3.029329 |

## 6. Analysis Notes

1. Main bottlenecks:
   - with `--to-neo4j`: `export_neo4j` and `export_json`
   - without `--to-neo4j`: `export_json` and `build_geometry`
2. Repeatability:
   - wall-time std is ~2.54s over 3 runs under the same condition
3. Accuracy impact:
   - node/edge counts and overall score remain stable across runs
4. Next actions:
   - implement or align `CONNECTS` generation with benchmark queries
   - use additional datasets that produce non-zero furniture-boundary/opening candidate pairs

