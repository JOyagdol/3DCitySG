# 3DCitySG Development Summary

Baseline date: 2026-03-26

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

1. Publish first benchmark report on real datasets.
2. Publish first import profiling report (mean/std-based).
3. Finalize documentation sync across README and `docs/*`.

