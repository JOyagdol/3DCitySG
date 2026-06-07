# Feature Implementation and Validation Guide (v1)

Baseline: CityGML 2.0  
Goal: define stable implementation/validation criteria for core features.

Command source of truth:
1. `docs/command_cheatsheet.md`

Detailed spatial-relation v2 algorithm notes:
1. `docs/spatial_relation_v2_algorithm_notes.md`
2. `docs/spatial_relation_v2_algorithm_notes_ko.md`

## 1. Spatial Threshold Parameters (`spatial.*`)

### 1.1 Goal

1. Tune relation sensitivity (`TOUCHES`, `ADJACENT_TO`, `INTERSECTS`) per dataset.
2. Keep experiments reproducible without code changes.

Current v2 relation scope (implemented in pipeline):
1. `OBJECT --ABOVE/BELOW--> OBJECT` (object scope: `BuildingFurniture`, `Door`, `Window`)
2. `OPENING --HOSTED_BY--> BOUNDARY_SURFACE(subtype)`
3. `BOUNDARY_SURFACE --ADJACENT_SURFACE--> BOUNDARY_SURFACE`
4. `BuildingFurniture --ATTACHED_TO/TOUCHES--> BOUNDARY_SURFACE(subtype)`
5. keep `Door -> Room (CONNECTS)` as source relation
6. exclude `ROOM --SHARES_DOOR_WITH--> ROOM` from v2 core graph

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
2. `spatial_plausible_coverage`
3. `spatial_density`
4. `spatial_precision_sanity`
5. `spatial_quality`
6. `spatial_pair_stats`
7. `spatial_pair_family_scores`
8. `spatial_family_normalized_coverage`
9. `spatial_coverage_policy`

Source of truth for formula/definition: `docs/evaluation_scorecard.md`.

Final v2 interpretation policy:
1. `spatial_coverage`: raw hit-rate with base denominator (`expected_total`)
2. `spatial_plausible_coverage`: supplementary hit-rate with plausible denominator (`plausible_expected_total`)
3. `spatial_density`: weighted family-normalized density score
4. `spatial_quality` / `spatial_precision_sanity`: quality sanity axis

### 2.3 Validation

1. Ensure all spatial scorecard fields are present.
2. Read density and quality separately:
   - raw coverage: `spatial_coverage` (`actual_total/expected_total`)
   - plausible coverage: `spatial_plausible_coverage` (`actual_total/plausible_expected_total`)
   - normalized density: `spatial_density` (weighted family-normalized)
   - quality: `spatial_precision_sanity`, `spatial_quality`
3. Monitor `pair_conflict_count` and keep it near 0.
4. Check pair-family distribution and weighted family score against domain expectations.
5. Verify zero-candidate families are reported as `N/A` (`null`) rather than `100`.

## 3. Regression Testing (Including Negative Cases)

### 3.1 Goal

1. Prevent over-generation (false positives).
2. Detect precedence/exclusivity regressions early.

### 3.2 Current Scope

1. Positive cases
2. Precedence/exclusive cases (`INTERSECTS > TOUCHES > ADJACENT_TO`)
3. Negative cases (non-touching, non-adjacent, non-intersecting)

### 3.3 Execution Reference

1. Use `docs/command_cheatsheet.md` for exact test commands.

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
