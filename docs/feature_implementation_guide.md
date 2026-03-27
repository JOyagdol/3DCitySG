# Feature Implementation and Validation Guide (v1)

Baseline: CityGML 2.0  
Goal: define stable implementation/validation criteria for core features.

## 1. Spatial Threshold Parameters (`spatial.*`)

### 1.1 Goal

1. Tune relation sensitivity (`TOUCHES`, `ADJACENT_TO`, `INTERSECTS`) per dataset.
2. Keep experiments reproducible without code changes.

### 1.2 Configuration

File: `configs/default.yaml`

```yaml
spatial:
  touch_epsilon: 0.05
  adjacent_epsilon: 0.50
  intersection_epsilon: 0.000001
```

Parameter meaning:

1. `touch_epsilon`: max distance for `TOUCHES` when not intersecting.
2. `adjacent_epsilon`: max distance for `ADJACENT_TO` beyond touch range.
3. `intersection_epsilon`: minimum overlap required for `INTERSECTS`.

### 1.3 Validation

1. Confirm relation distribution changes as thresholds change.
2. Extreme-case checks:
   - very small `touch_epsilon` should reduce `TOUCHES`
   - larger `adjacent_epsilon` should increase `ADJACENT_TO`

## 2. Spatial Scorecard Diagnostics

### 2.1 Goal

1. Evaluate spatial quality separately from global `overall` score.
2. Distinguish relation volume from relation consistency.

### 2.2 Fields

In `summary.scorecard`:

1. `spatial_coverage`
2. `spatial_precision_sanity`
3. `spatial_pair_stats`

Source of truth for formula/definition: `docs/evaluation_scorecard.md`.

### 2.3 Validation

1. Ensure all spatial scorecard fields are present.
2. Monitor `pair_conflict_count` and keep it near 0.
3. Check pair-family distribution against domain expectations.

## 3. Regression Testing (Including Negative Cases)

### 3.1 Goal

1. Prevent over-generation (false positives).
2. Detect precedence/exclusivity regressions early.

### 3.2 Current Scope

1. Positive cases
2. Precedence/exclusive cases (`INTERSECTS > TOUCHES > ADJACENT_TO`)
3. Negative cases (non-touching, non-adjacent, non-intersecting)

### 3.3 Run Commands

```powershell
python -m pytest tests/test_spatial_priority.py -q
python -m pytest tests/test_spatial_relation_pairs.py -q
python -m pytest tests/test_pipeline_regression.py -q
```

## 4. Large-Scale Performance Profiling

### 4.1 Goal

1. Quantify bottlenecks across parsing, graph build, and export.
2. Validate improvements with before/after measurements.

### 4.2 Measured Items

1. Stage durations
2. Total runtime
3. Node/edge counts
4. Throughput across `neo4j.batch_size` settings

### 4.3 Recommended Experiments

1. Compare `batch_size` = 2000 / 5000 / 10000
2. Compare epsilon sets under same dataset
3. Run each setting at least 3 times and record mean/std

## 5. Document Sync Policy

If implementation or policy changes, update in the same work unit:

1. `README.md`
2. `docs/evaluation_scorecard.md`
3. `docs/relation_definitions.md`
4. `docs/graph_schema.md`
5. `docs/regression_testing.md`
6. `docs/development_summary.md`

