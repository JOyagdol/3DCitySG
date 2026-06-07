# Query Benchmark Guide (v1)

Baseline: CityGML 2.0 / spatial relations v1 (`INSIDE`, `CONNECTS`, `ADJACENT_TO`, `TOUCHES`, `INTERSECTS`)

Command source of truth:

1. `docs/command_cheatsheet.md`

Room-localization / view-graph matching query scenarios:

1. `docs/room_localization_query_scenarios.md`
2. Latest paper-oriented result notes: `docs/room_localization_query_results.md`

## 1. Goal

1. Validate whether the graph supports interpretable spatial querying.
2. Detect regressions after pipeline updates.
3. Track accuracy/consistency/performance with reproducible measurements.

## 2. Recommended Query Set

The built-in benchmark query set is split into three tiers.

### 2.1 Baseline Tier (`B*`)

Purpose: always produce interpretable counts for loaded graphs.

1. `B1 baseline__all_nodes`
2. `B2 baseline__buildings`
3. `B3 baseline__rooms`
4. `B4 baseline__openings`
5. `B5 baseline__furniture_inside_room_links`
6. `B6 baseline__room_boundary_links`
7. `B7 baseline__boundary_opening_links`

### 2.2 Hard Tier (`H*`)

Purpose: track sparse/high-selectivity spatial patterns.

1. `H1 hard__furniture_furniture_spatial_any`
2. `H2 hard__furniture_opening_spatial_any`
3. `H3 hard__furniture_boundary_spatial_any`
4. `H4 hard__opening_room_connects`
5. `H5 hard__room_internal_furniture_touching_opening`

Hard-tier zero counts are valid and informative when candidate pairs are absent in source data.

### 2.3 Scenario Tier (`S*`)

Purpose: emulate user-facing question patterns.

1. `S1 scenario__rooms_with_furniture`
2. `S2 scenario__rooms_with_installations`
3. `S3 scenario__door_opening_count`
4. `S4 scenario__rooms_with_internal_furniture_spatial_pairs`
5. `S5 scenario__room_to_room_pairs_via_same_buildingpart`

Note: exception-focused query (`missing CONNECTS`) is intentionally excluded from scenario tier.

## 3. Execution Rules

1. Run on a fixed dataset and fixed DB state.
2. Run each query at least 3 times.
3. Use 1 warm-up run before timed runs.
4. Record both result count and runtime.
5. Keep empty results as valid outcomes.

Command:

```bash
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
```

For guaranteed DB sync before benchmark, run import with Neo4j export first (or use `scripts/refresh_latest_reports.py --to-neo4j`).

Alternative:

```bash
python -m citygml_sg.app.cli benchmark --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
```

## 4. Recording Template

| Query ID | Goal | Cypher Summary | Result Count | Avg Time (ms) | P95 (ms) | Note |
|---|---|---|---:|---:|---:|---|
| B1 | Baseline total nodes | `MATCH (n) RETURN count(n)` | 0 | 0.0 | 0.0 | should be >0 on populated DB |
| H4 | Door-room connectivity | `MATCH (:Opening {opening_type: 'Door'})-[:CONNECTS]->(:Room)` | 0 | 0.0 | 0.0 | 0 can be valid per dataset |
| S5 | Room-to-room pairs (path-like) | `Room <-INTERIOR_ROOM- BuildingPart -INTERIOR_ROOM-> Room` | 0 | 0.0 | 0.0 | human-style navigation proxy |

Output files:

1. Latest default benchmark file:
   - `data/output/benchmark_report.json`
2. Dataset-tagged benchmark file (from `refresh_latest_reports.py`):
   - `data/output/<dataset_tag>__benchmark_report_YYYYMMDD_HHMMSS.json`
3. Note:
   - `benchmark_report.json` is overwritten by the latest promoted run.
   - Use dataset-tagged files for stable reproducible references.

JSON fields:

1. `summary`
2. `queries[*].result_count`
3. `queries[*].avg_ms`
4. `queries[*].min_ms`
5. `queries[*].max_ms`
6. `queries[*].std_ms`

## 5. Interpretation

1. Accuracy:
   - baseline tier should remain structurally stable
   - hard tier should be interpreted with candidate-pair sparsity
   - scenario tier should be interpreted as user-facing query behavior
2. Consistency:
   - check repeat stability on same dataset
3. Performance:
   - compare per-query timing trends
   - compare before/after index or label strategy changes

## 6. Deliverables

1. Raw execution logs
2. Query result summary table
3. Sample IDs for representative results
4. Before/after tuning notes

## 7. Latest Snapshot (`benchmark_report.json`)

Source:
1. `data/output/benchmark_report.json`
2. Dataset file: `data/output/snowdon_towers_ifc4__benchmark_report_20260507_104353.json`

Summary:
1. `query_total=17`, `query_success=17`, `query_failed=0`
2. `avg_query_time_ms=5.128`
3. Tier nonzero:
   - `B=6/7`
   - `H=4/5`
   - `S=4/5`

Selected query counts:
1. `B1 baseline__all_nodes = 16,960,567`
2. `H4 hard__opening_room_connects = 1,179`
3. `S5 scenario__room_to_room_pairs_via_same_buildingpart = 1,474`
