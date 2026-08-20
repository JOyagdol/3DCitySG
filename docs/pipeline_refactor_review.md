# Pipeline Refactor Review

Status: Phase 5 orchestration shrink and surface cleanup completed. Reporting, scorecard, spatial metrics, spatial edge/scope, geometry, and appearance builders are now split out of `pipeline.py`; user-run regression confirmation is still required after this cleanup.

## 1. Current State

`src/citygml_sg/app/pipeline.py` is the stable orchestration file for the CityGML import pipeline. It now stays focused on stage orchestration while reporting, scorecard, spatial metrics, spatial scope, spatial edge builders, geometry builders, and appearance builders live in dedicated modules. It still works as the public import path through `scripts/run_import.py`.

The file currently owns several responsibilities at once:

| Responsibility | Current location | Refactor risk |
|---|---|---|
| XML record collection and object parser dispatch | `pipeline.py` record helpers | Medium |
| Semantic edge construction | `_build_semantic_edges` | Medium |
| LoD geometry and geometry subgraph construction | `_attach_lod_geometry_structure`, `_attach_geometry_subgraph` | High |
| Appearance graph construction | `_attach_appearance_subgraph` | Medium |
| Spatial relation construction | `relations/spatial_edges.py` | High |
| CONNECTS fallback augmentation | `relations/spatial_edges.py` | High |
| Spatial scope and representative boundary selection | `relations/spatial_scope.py` | High |
| Spatial score metrics | `evaluation/spatial_metrics.py` | Medium |
| Scorecard construction | `evaluation/scorecard.py` | Medium |
| Terminal conversion report and timeline logging | `app/reporting.py` | Low |
| Neo4j export | `_write_graph_to_neo4j` | Medium |
| Benchmark execution | `run_benchmark_pipeline` | Low/Medium |
| Public import orchestration | `run_import_pipeline` + small local helper wrappers | Medium |

## 2. Refactor Policy

Do not split the pipeline by moving large blocks at once. The safe direction is to extract read-only or low-mutation helpers first, then move graph-mutating builders only after snapshot checks are stable.

The immediate goal is not to redesign the pipeline. The goal is to reduce surface complexity while preserving output compatibility.

## 3. Required Snapshot Checks

Before and after each refactor step, compare:

1. Node type counts.
2. Relation type counts.
3. Scorecard top-level keys and scores.
4. Spatial relation counts.
5. `HOSTED_BY`, `ATTACHED_TO`, `ADJACENT_SURFACE`, `ABOVE`, `BELOW` counts.
6. Neo4j benchmark query counts when Neo4j is used.
7. Retrieval scenario top-k room candidates when retrieval output is affected.

Recommended smoke commands are documented in `docs/command_cheatsheet.md`.

## 4. Recommended Refactor Phases

### Phase 0: Freeze Behavior Contract

Create a small comparison checklist using current outputs from at least:

1. FZK Haus import without Neo4j.
2. E-type import without Neo4j.
3. E-type import with Neo4j when available.
4. E-type kitchen and living retrieval scenarios.

No source movement should happen until these checks are accepted as the behavior contract.

### Phase 1: Extract Reporting Helpers

Candidate target:

```text
src/citygml_sg/app/reporting.py
```

Current status: completed for terminal/timeline reporting helpers.

Move low-risk helpers:

1. `_format_counter`
2. `_avg`
3. `_log_separator`
4. `_log_metric`
5. `_log_section`
6. `_progress_bar`
7. `_duration_bar`
8. `_log_stage_timeline`
9. `_emit_conversion_report`

Implementation note: `reporting.py` does not import `pipeline.py`. Pipeline-owned constants and callback helpers are passed explicitly into `_emit_conversion_report` to avoid circular imports and keep ownership visible.

Reason: these functions mostly read counters and log values. They do not construct graph topology.

### Phase 2: Extract Scorecard and Metrics

Candidate targets:

```text
src/citygml_sg/evaluation/scorecard.py
src/citygml_sg/evaluation/spatial_metrics.py
```

Current status: code extraction completed and user-reported targeted tests passed after import boundary fixes.

Move:

1. `_safe_ratio`
2. `_spatial_pair_family`
3. `_build_spatial_score_metrics`
4. `_build_scorecard`

This step is useful because scorecard logic is now research-facing and changes often. It should not live inside import orchestration long term.

Risk: `_build_spatial_score_metrics` depends on spatial scope helpers, bbox/point builders, relation metadata policy, and CONNECTS candidate policy. Move dependencies deliberately, not by copying duplicate logic.

Implementation note: `scorecard.py` and `spatial_metrics.py` do not import `pipeline.py`. Pipeline-owned helpers are passed as callbacks to keep the split behavior-preserving and avoid circular imports.

### Phase 3: Extract Spatial Scope and Spatial Edge Builder

Candidate targets:

```text
src/citygml_sg/relations/spatial_scope.py
src/citygml_sg/relations/spatial_edges.py
```

Move:

1. `_build_room_spatial_scope`
2. layered boundary collapse helpers
3. representative surface selection helpers
4. `_add_spatial_edges_for_pairs`
5. `_build_spatial_edges`
6. `_augment_connects_edges`
7. vertical relation helper logic

This is the first high-risk phase. It changes where graph-mutating relation code lives, so it needs full relation-count and example-case validation.

Current status: code extraction completed. E-type 201dong import with Neo4j completed after the extraction:

1. `nodes=1,076,200`
2. `edges=1,240,562`
3. Neo4j writer reported `written_nodes=1,076,200`, `written_edges=1,240,562`, `success=true`
4. Spatial relation counts: `CONNECTS=37`, `HOSTED_BY=24`, `INTERSECTS=4`, `ADJACENT_TO=74`, `TOUCHES=18`, `ADJACENT_SURFACE=142`, `ATTACHED_TO=10`
5. Scorecard: `overall=98.04`, `spatial_coverage=23.81`, `spatial_plausible_coverage=90.43`, `spatial_density=28.85`, `spatial_precision_sanity=100.0`

FZK Haus smoke import also completed after the JSON stage-duration patch:

1. `nodes=80`
2. `edges=90`
3. `overall=100.0`
4. `spatial_coverage=100.0`
5. `summary.stage_durations.export_json=0.005615`
6. `summary.stage_durations.total=0.036073`

Phase 3 lock basis:

1. E-type Neo4j smoke passed.
2. FZK Haus smoke passed.
3. JSON stage duration patch is verified on newly generated FZK output.
4. Targeted regression test confirmation remains required before treating Phase 3 as fully locked.

Implementation note: `spatial_edges.py` and `spatial_scope.py` do not import `pipeline.py`. Pipeline-owned graph utility callbacks are injected from `run_import_pipeline` and from `evaluation/spatial_metrics.py` to preserve behavior and avoid circular imports.

### Phase 4: Extract Geometry and Appearance Graph Builders

Candidate targets:

```text
src/citygml_sg/world_graph/citygml_to_graph/geometry_subgraph.py
src/citygml_sg/world_graph/citygml_to_graph/appearance_subgraph.py
```

Move:

1. `_attach_lod_geometry_structure` -> `attach_lod_geometry_structure`
2. `_attach_geometry_subgraph` -> `attach_geometry_subgraph`
3. `_attach_appearance_subgraph` -> `attach_appearance_subgraph`
4. geometry point/ring parsing helpers -> `iter_ring_positions` and private parse helpers
5. appearance target normalization -> `normalize_target_refs`

Current status: code extraction completed. FZK Haus smoke import passed after extraction:

1. `nodes=80`
2. `edges=90`
3. `overall=100.0`
4. `spatial_coverage=100.0`
5. `summary.stage_durations.export_json=0.004477`
6. `summary.stage_durations.total=0.017169`
7. Relation counts remained stable: `BOUNDED_BY=7`, `HAS_GEOMETRY=7`, `HAS_GEOMETRY_COMPONENT=8`, `HAS_GEOMETRY_MEMBER=7`, `HAS_LOD_GEOMETRY=8`, `HAS_POS=37`, `HAS_RING=7`, `HAS_SURFACE_TYPE=7`

Remaining verification:

1. Confirm targeted regression test results.
2. Optionally rerun E-type import without Neo4j if Phase 4 needs a large-dataset smoke before Phase 5.

Implementation note: `geometry_subgraph.py` and `appearance_subgraph.py` do not import `pipeline.py`. Pipeline-owned helpers for parent maps, ancestor lookup, fallback IDs, and edge validation are injected as callbacks.

Risk: this area previously hit memory limits on large datasets. Avoid changing data structures in the same step as moving code.

### Phase 5: Shrink Public Orchestration

After phases 1-4, `run_import_pipeline` should become a thin stage runner:

```text
read CityGML
collect semantic records
build semantic nodes
build semantic edges
build geometry/appearance
build spatial relations
score
export Neo4j
export JSON
emit report
```

At this point, consider an explicit `ImportPipelineResult` dataclass only if it reduces parameter passing. Do not introduce a framework-style abstraction before the helper extraction proves stable.

Current status: completed as a behavior-preserving orchestration cleanup.

Implementation changes:

1. Added `_StageTimeline` to replace nested `_stage_start`, `_stage_done`, and `_stage_skip` closures.
2. Added `_build_import_nodes` for semantic node construction.
3. Added `_build_import_geometry_and_spatial` for LoD geometry, polygon/ring/position graph construction, appearance graph construction, `CONNECTS` fallback, and spatial edge generation.
4. Added `_build_import_scorecard` as the scorecard adapter boundary from pipeline-owned callbacks to `evaluation/scorecard.py`.
5. Added `_write_import_json_output` for streaming JSON export and stage-duration patching.
6. Removed non-functional `relations` and `export` CLI commands because the real public commands are `import` and `benchmark`.
7. Removed unused root-level stub scripts: `scripts/run_relations.py` and `scripts/run_export_graph.py`.
8. Removed placeholder-only relation modules that were not wired into active code: `candidate_search.py`, `directional.py`, `intersection.py`, and `semantic_filters.py`.

Verification still required by user-run commands:

1. targeted regression tests
2. FZK smoke import without Neo4j
3. optional E-type import smoke if large-dataset confidence is needed before Phase 6

### Phase 6: Memory and Streaming Redesign

Only after behavior-preserving extraction:

1. Revisit `SceneGraph.edges` in-memory accumulation.
2. Consider chunked relation storage.
3. Keep huge JSON disabled or summary-first by default.
4. Add explicit checkpoint/resume boundaries.

This phase is not a cleanup phase. It is a behavior/runtime design phase and should be handled separately.

## 5. Recommended Next Task

Phase 4 code extraction is complete and FZK smoke passed. The next task is to confirm targeted regression tests, then decide whether to run an E-type no-Neo4j smoke before Phase 5.

Reason:

1. Phase 4 moved graph-mutating geometry and appearance code.
2. Node counts, relation counts, appearance coverage, geometry density, and scorecard values must be verified.
3. Runtime checks are needed because the extracted builders now receive pipeline utilities through callback injection.

Do not start Phase 5 until Phase 4 regression tests are confirmed. If a stricter gate is needed, run E-type without Neo4j first because `_attach_geometry_subgraph` was central to geometry counts and large-file memory behavior.

## 6. Definition of Done

Each phase is complete only when:

1. Existing targeted tests pass.
2. Static references use the new module path.
3. Public commands remain unchanged.
4. JSON output schema remains compatible.
5. Relation and scorecard counts are either unchanged or intentionally documented.
6. Relevant docs are updated in the same work unit.
