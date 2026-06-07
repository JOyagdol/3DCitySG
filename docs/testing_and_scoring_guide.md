# Testing and Scoring Guide (v1, CityGML 2.0)

This document explains, in one place, how testing and scoring work in this project.
It is intended as an operational guide for developers and experiment operators.

Command source of truth:

1. `docs/command_cheatsheet.md`

## 1. Scope and Intent

This guide covers:

1. automated test structure (`tests/*`)
2. import-time scorecard structure (`summary.scorecard`)
3. large-scale baseline validation workflow (`201dong`)
4. practical run commands and interpretation rules

This guide does not replace:

1. relation policy details in `docs/relation_definitions.md`
2. score policy source of truth in `docs/evaluation_scorecard.md`
3. profiling-only focus in `docs/performance_profiling_guide.md`
4. query benchmark details in `docs/query_benchmark_guide.md`
5. detailed spatial-relation v2 algorithm notes in `docs/spatial_relation_v2_algorithm_notes.md`

## 2. Test System Overview

The project currently uses three complementary validation channels:

1. regression tests (logic correctness and contract stability)
2. scorecard metrics (quality telemetry per import run)
3. large-scale baseline check (pass/fail thresholds for real dataset runs)

You should read them as one system:

1. regression tests protect rule behavior
2. scorecard quantifies quality and coverage
3. baseline check enforces reproducible large-scale quality/performance bounds

## 3. Regression Test Suite

Current tracked tests:

1. `tests/test_pipeline_regression.py`
2. `tests/test_spatial_priority.py`
3. `tests/test_spatial_relation_pairs.py`
4. `tests/test_spatial_inference_refinement.py`

### 3.1 `test_pipeline_regression.py`

Main purpose:

1. guard import output contracts and semantic edge policy

Current checks include:

1. `HAS_APPEARANCE` fallback link creation for global appearance nodes
2. no duplicate `CONTAINS` when specialized relations are emitted
3. scorecard and appearance coverage keys in summary
4. boundary subtype preservation:
   - `BoundarySurfaceType` node existence
   - `BoundarySurface -[:HAS_SURFACE_TYPE]-> BoundarySurfaceType`

### 3.2 `test_spatial_priority.py`

Main purpose:

1. ensure precedence normalization behavior is stable

Current checks include:

1. `INTERSECTS > TOUCHES > ADJACENT_TO`
2. reverse direction independence (`A->B` and `B->A` handled separately)
3. non-priority relations are preserved

### 3.3 `test_spatial_relation_pairs.py`

Main purpose:

1. verify spatial inference pair-family generation and negative cases

Current v2 checks also cover:

1. `HOSTED_BY`, `ADJACENT_SURFACE`, `ATTACHED_TO`, `ABOVE`, `BELOW`
2. Door-only `CONNECTS` scope
3. AABB candidate filtering plus OBB/Polygon refinement
4. polygon shared-edge validation for `ADJACENT_SURFACE`

Current checks include:

1. `Furniture <-> Door|Window` inferred relations
2. `Furniture <-> Furniture` inferred relations
3. `Furniture <-> BoundarySurface` inferred relations
4. bidirectional materialization for inferred spatial edges
5. negative checks for far/non-contact pairs

### 3.4 How to Run

Conda environment example:

```powershell
conda activate 3DCitySG
python -m pytest tests/test_pipeline_regression.py -q
python -m pytest tests/test_spatial_priority.py -q
python -m pytest tests/test_spatial_relation_pairs.py -q
```

All tests:

```powershell
python -m pytest -q
```

## 4. Scorecard System (Import-Time)

Scorecard is computed during `run_import_pipeline` in:

1. `src/citygml_sg/app/pipeline.py` (`_build_scorecard`)

It is exported to:

1. `output_json.summary.scorecard`

### 4.1 Top-Level Formula

`overall = 0.40 * node + 0.30 * relation + 0.30 * property`

Notes:

1. each component is a percentage-based ratio
2. the formula is a weighted sum multiplied to 100 scale
3. spatial diagnostics are reported separately and not added to `overall`

### 4.2 Node Coverage

Node coverage compares:

1. expected semantic + geometry nodes from supported extraction channels
2. actual semantic + geometry nodes produced by pipeline

Important implementation detail:

1. `BoundarySurfaceType` is a support taxonomy node
2. it is intentionally excluded from semantic coverage denominator and numerator
3. therefore `summary.node_count` can be larger than `scorecard.node_coverage.actual_total`

### 4.3 Relation Coverage

Relation coverage is built from supported relation families only.
Current expected set includes, among others:

1. `HAS_CITY_OBJECT`
2. `HAS_GROUP_MEMBER`
3. `CONTAINS`
4. `CONSISTS_OF_BUILDING_PART`
5. `INTERIOR_ROOM`
6. `OUTER_BUILDING_INSTALLATION`
7. `INTERIOR_BUILDING_INSTALLATION`
8. `ROOM_INSTALLATION`
9. `INSIDE`
10. `BOUNDED_BY`
11. `HAS_SURFACE_TYPE`
12. `HAS_OPENING`
13. `HAS_ADDRESS`
14. `HAS_LOD_GEOMETRY`
15. `HAS_GEOMETRY_COMPONENT`
16. `HAS_GEOMETRY_MEMBER`
17. `HAS_GEOMETRY`
18. `HAS_RING`
19. `HAS_POS`
20. `HAS_APPEARANCE`
21. `HAS_SURFACE_DATA`
22. `APPLIES_TO`
23. `CONNECTS`
   - `CONNECTS` scope in v2 policy: `Opening(Door) -> Room` (window excluded)

Computation detail:

1. per-relation ratio is computed with safe denominator logic
2. relation coverage score uses the mean of per-relation ratios where expected > 0
3. relation `actual_total` and `expected_total` are also reported for context

### 4.4 Property Coverage

Property coverage compares expected vs actual property extraction on semantic nodes:

1. `gml_name`
2. `gml_description`
3. `creation_date`
4. `relative_to_terrain`
5. `class_code`
6. `function_code`
7. `usage_code`
8. `year_of_construction`
9. `roof_type_code`
10. `measured_height`
11. `storeys_above_ground`
12. `storeys_below_ground`
13. generic attributes (`gen:*Attribute -> attr_*`)

Policy:

1. expected totals only count fields that are structurally present in source elements
2. this prevents unfair penalties for unsupported/unavailable channels

### 4.5 Spatial Diagnostics

Additional metrics in scorecard:

1. `spatial_coverage`
2. `spatial_plausible_coverage`
3. `spatial_density`
4. `spatial_precision_sanity`
5. `spatial_quality`
6. `spatial_pair_stats`
7. `spatial_pair_family_scores`
8. `spatial_family_normalized_coverage`
9. `spatial_coverage_policy`

Interpretation:

1. `spatial_coverage` is raw hit-rate (`actual_total/expected_total`) over active families
2. `spatial_plausible_coverage` is supplementary hit-rate (`actual_total/plausible_expected_total`)
3. `spatial_density` is weighted family-normalized density score
4. low `spatial_coverage` with higher `spatial_plausible_coverage` usually means denominator conservatism in raw candidate pool
5. low `spatial_coverage` with higher `spatial_density` means overall pair volume is sparse but normalized family behavior is relatively stable
6. low `spatial_density` indicates poor weighted family-level balance (one or more important families underperform)
7. low `spatial_precision_sanity`/`spatial_quality` indicates metadata/schema/precedence inconsistency
8. `pair_conflict_count` should be near zero under precedence normalization
9. `spatial_pair_family_scores` and `spatial_family_normalized_coverage` help isolate which pair family improved or regressed
10. families with `expected_total=0` are reported as `N/A` (`null`), not `100`
11. `expected_total` is candidate-pool size from structural scope/enumeration, not epsilon-threshold filtering.
12. `plausible_expected_total` is epsilon-aware plausible candidate size, reported as a supplementary denominator.

## 5. Large-Scale Baseline Validation (`201dong`)

Baseline files:

1. `configs/baselines/201dong_v1_baseline.json`
2. `scripts/check_large_scale_baseline.py`

### 5.1 What It Checks

Import summary checks:

1. node and edge count ranges
2. minimum score thresholds (`overall`, node/relation/property, spatial diagnostics)
3. fixed node-type counts for key semantic nodes
4. fixed relation counts for key relations including `HAS_SURFACE_TYPE`

Profiling checks:

1. run success counts
2. wall-time avg/std upper bounds
3. stage duration avg/std upper bounds

### 5.2 Recommended Execution Sequence

```powershell
python scripts/run_import.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --output data/output/E-TYPE_201dong_after_boundarytype.json --config configs/default.yaml
python scripts/profile_import_runs.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --runs 3 --config configs/default.yaml --output-dir data/output/profiling_201dong_after_boundarytype --report data/output/import_profile_report_201dong_after_boundarytype.json
python scripts/check_large_scale_baseline.py --baseline configs/baselines/201dong_v1_baseline.json --import-summary data/output/E-TYPE_201dong_after_boundarytype.json --profile-report data/output/import_profile_report_201dong_after_boundarytype.json
```

Return code rule:

1. `0` means PASS
2. non-zero means at least one baseline rule failed

## 6. How to Read Failures

If regression tests fail:

1. likely relation logic or output contract regression
2. inspect fixture XML and expected edge triples first

If scorecard drops but tests pass:

1. likely extraction volume/coverage drift, not strict rule break
2. inspect relation expectations and property mapping changes

If baseline check fails:

1. check whether change is intended (feature expansion, denominator shift, threshold policy change)
2. if intended, update baseline JSON and runbook in same change set
3. if unintended, treat as regression and investigate before updating baseline

## 7. Update Discipline

When changing extraction logic, thresholds, or scoring semantics:

1. update tests (`tests/*`) as needed
2. update score policy docs (`docs/evaluation_scorecard.md`)
3. update this guide
4. update runbook and baseline JSON if large-scale expected values changed

This keeps implementation, evaluation policy, and operational commands synchronized.
