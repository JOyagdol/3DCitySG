# Query Benchmark Guide (v1)

Baseline: CityGML 2.0 / spatial relations v1 (`INSIDE`, `CONNECTS`, `ADJACENT_TO`, `TOUCHES`, `INTERSECTS`)

## 1. Goal

1. Validate whether the graph supports interpretable spatial querying.
2. Detect regressions after pipeline updates.
3. Track accuracy/consistency/performance with reproducible measurements.

## 2. Recommended Query Set

### 2.1 Intersection

1. Furniture-furniture `INTERSECTS` pairs
2. Furniture-door/window `INTERSECTS` pairs

### 2.2 Touch

1. Furniture-boundary `TOUCHES`
2. Furniture-door/window `TOUCHES`

### 2.3 Adjacency

1. Furniture-furniture `ADJACENT_TO`
2. Furniture-boundary `ADJACENT_TO`

### 2.4 Connectivity

1. Openings connected to a room via `CONNECTS`
2. Door/window connectivity distribution

### 2.5 Composite

1. Furniture `INSIDE` a room and `TOUCHES` an opening
2. Top-N furniture by adjacency count inside a room

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

Alternative:

```bash
python -m citygml_sg.app.cli benchmark --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
```

## 4. Recording Template

| Query ID | Goal | Cypher Summary | Result Count | Avg Time (ms) | P95 (ms) | Note |
|---|---|---|---:|---:|---:|---|
| Q1 | Intersection (Furniture-Furniture) | `MATCH ... INTERSECTS ...` | 0 | 0.0 | 0.0 | |
| Q2 | Touch (Furniture-Opening) | `MATCH ... TOUCHES ...` | 0 | 0.0 | 0.0 | |

Output file:

- `data/output/benchmark_report.json`

JSON fields:

1. `summary`
2. `queries[*].result_count`
3. `queries[*].avg_ms`
4. `queries[*].min_ms`
5. `queries[*].max_ms`
6. `queries[*].std_ms`

## 5. Interpretation

1. Accuracy:
   - compare counts with domain expectation
   - inspect large spikes/drops in relation counts
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

