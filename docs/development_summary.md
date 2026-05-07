# 3DCitySG Development Summary

Baseline date: 2026-05-07

## 1. Current Baseline

1. Research focus: CityGML semantic-spatial scene graph construction
2. Experiment baseline: CityGML 2.0
3. v1 core object families:
   - Building
   - BuildingPart
   - Room
   - BoundarySurface
   - Opening (Door/Window)
   - BuildingFurniture

## 2. Completed Work

### 2.1 Parsing and Graph Construction

1. Core object families are parsed as nodes with hierarchical relations.
2. Geometry subgraph links are generated for Polygon, LinearRing, and Position.
3. Appearance/SurfaceData owner fallback linking is implemented.
4. Boundary surface subtype preservation is implemented:
   - `BoundarySurface -> HAS_SURFACE_TYPE -> BoundarySurfaceType`
   - original subtype (for example `WallSurface`, `FloorSurface`) is preserved in graph-level semantics.

### 2.2 Spatial Relations (v1)

1. Relation set: `INSIDE`, `CONNECTS`, `ADJACENT_TO`, `TOUCHES`, `INTERSECTS`
2. Priority/exclusivity: `INTERSECTS > TOUCHES > ADJACENT_TO`
3. Pair families:
   - Furniture <-> BoundarySurface
   - Furniture <-> Door|Window
   - Furniture <-> Furniture
4. Computation method: coordinate-based AABB approximation
5. Spatial edge metadata:
   - `method`, `distance`
   - `epsilon_touch`, `epsilon_adjacent`, `epsilon_intersection`
   - `confidence`, `computed_at`

### 2.3 Configuration, Scoring, and Tests

1. Epsilon parameters externalized to `configs/default.yaml` under `spatial.*`.
2. Spatial diagnostics added to scorecard:
   - `spatial_coverage`
   - `spatial_precision_sanity`
   - `spatial_pair_stats`
   - `spatial_pair_family_scores`
3. Regression tests expanded:
   - positive cases
   - precedence/exclusivity cases
   - negative cases (non-touching, non-adjacent, non-intersecting)

### 2.4 Documentation and Tooling

1. Query benchmark guide added.
2. Feature implementation and validation guide added.
3. Large-scale profiling guide added.
4. `scripts/benchmark_queries.py` implemented as a runnable benchmark tool.
5. `scripts/profile_import_runs.py` added for repeated import profiling.
6. `scripts/check_large_scale_baseline.py` and `configs/baselines/201dong_v1_baseline.json` added for pass/fail baseline validation.
7. `scripts/refresh_latest_reports.py` added for one-command refresh and default report promotion.
8. Benchmark query set restructured into:
   - baseline tier (`B1..B7`)
   - hard tier (`H1..H5`)
   - scenario tier (`S1..S5`)
9. Dataset-level result tracking document added:
   - `docs/dataset_result_comparison.md`

### 2.5 Latest Execution Snapshot (2026-05-07)

1. E-TYPE_201dong (`data/output/e_type_201dong_ifc4__*.json`):
   - benchmark: `query_total=17`, `query_failed=0`, `avg_query_time_ms=4.065`
   - tier nonzero: `B=6/7`, `H=4/5`, `S=4/5`
   - relation counts: `CONNECTS=63`, `ADJACENT_TO=8`, `TOUCHES=4`, `INTERSECTS=4`
   - profile: `stage.total.avg=90.642`, `wall_time.avg=141.727`
   - current baseline check status: `FAIL` (spatial coverage threshold mismatch; profile total is now under threshold)
2. FZK Haus LoD2 (`data/output/fzk_haus_lod2_v2__*.json`):
   - benchmark: `query_total=17`, `query_failed=0`, `avg_query_time_ms=7.799`
   - tier nonzero: `B=2/7`, `H=0/5`, `S=0/5`
   - compact dataset with no v1 spatial candidate pairs, so hard/scenario counts stay zero by design.
3. Snowdon Towers (`data/output/snowdon_towers_ifc4__*.json`):
   - import: nodes=`16,960,567`, edges=`19,779,555`, overall=`99.87`, spatial coverage=`5.85`
   - benchmark: `query_total=17`, `query_failed=0`, `avg_query_time_ms=5.128`
   - tier nonzero: `B=6/7`, `H=4/5`, `S=4/5`
   - profile: resumed after interruption, final aggregate `runs_success=3`, `wall_time.avg=1510.059`
4. CONNECTS generation now includes fallback augmentation:
   - hierarchy + bbox-assisted link recovery when direct room ancestry is missing.

## 3. Partially Completed

1. Large-scale profiling:
   - scripts and guide are ready
   - dataset-level result accumulation is still ongoing
2. Final document sync:
   - most core docs are synchronized
   - one final pass is still recommended after the next implementation cycle

## 4. Remaining

1. Benchmark result accumulation across datasets
2. Before/after tuning comparison tables (`batch_size`, epsilon combinations)
3. v2 spatial extensions:
   - direction relations (left/right/up/down/front/back)
   - distance-bin relations (near/far)
   - accessibility/path relations

## 5. Next Priorities

1. Review `CONNECTS` extraction behavior and decide whether to keep hard-tier queries that depend on it.
2. Re-tune or split profiling baseline thresholds (`with Neo4j` vs `without Neo4j`) for stable gating.
3. Continue dataset-by-dataset accumulation in `docs/dataset_result_comparison.md`.
