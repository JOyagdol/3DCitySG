# Project Structure

This document defines the current folder ownership and cleanup policy.

## 1. Domain Flow

```text
OVG(ImageToGraph)
-> WorldGraph(CityGMLtoGraph + Anchor)
-> Retrieval(Query Generator + Graph Matching)
```

The original CityGML import pipeline remains stable, while new retrieval-facing code is separated into explicit domains.

## 2. Source Layout

| Path | Owner | Status |
|---|---|---|
| `src/citygml_sg/app/` | Core import/benchmark orchestration, reporting helpers, and CLI entrypoint | Stable core, Phase 5 orchestration shrink complete |
| `src/citygml_sg/parsers/` | CityGML parsing | Stable core |
| `src/citygml_sg/modules/` | Object-family extraction/mapping | Stable core |
| `src/citygml_sg/extractors/` | Geometry and metadata extraction | Stable core |
| `src/citygml_sg/relations/` | Spatial inference primitives, room-scoped candidates, and spatial edge builders | Stable core, Phase 3 extraction complete; placeholder-only relation stubs removed in Phase 5 |
| `src/citygml_sg/evaluation/` | Scorecard and metric computation | Stable core, Phase 2 extraction complete |
| `src/citygml_sg/graph/` | In-memory graph schema/builders | Stable core |
| `src/citygml_sg/storage/` | JSON/Neo4j persistence adapters | Stable core |
| `src/citygml_sg/ovg/` | Observed View Graph schema validation and future image-output adapters | New OVG domain |
| `src/citygml_sg/world_graph/` | CityGML-to-graph builders, Room signatures, anchors, and future precomputed world-graph features | New WorldGraph domain, Phase 4 geometry/appearance extraction added, FZK smoke passed |
| `src/citygml_sg/retrieval/` | Query templates, scoring params, graph matching, reporting | New Retrieval domain |

## 3. Script Layout

| Path | Role | Policy |
|---|---|---|
| `scripts/run_import.py` | Single CityGML import/export run | Keep as public stable command |
| `scripts/refresh_latest_reports.py` | Import + benchmark + profile refresh | Keep as public stable command |
| `scripts/benchmark_queries.py` | Neo4j benchmark query run | Keep as public stable command |
| `scripts/profile_import_runs.py` | Import performance profiling | Keep as public stable command |
| `scripts/check_large_scale_baseline.py` | Baseline validation | Keep as public stable command |
| `scripts/retrieval/` | Canonical retrieval experiment scripts | Use for all retrieval commands |
| `scripts/ovg/` | Future OVG command location | Placeholder, no active script yet |
| `scripts/world_graph/` | Future RoomSignature/AnchorGraph command location | Placeholder, no active script yet |

Root-level retrieval wrappers and inactive relation/export stubs were removed. Use `scripts/retrieval/...` for retrieval commands and `scripts/run_import.py` or `scripts/benchmark_queries.py` for core graph runs.

## 4. Documentation Layout

| Path | Role |
|---|---|
| `README.md` | Project overview and quick start |
| `docs/command_cheatsheet.md` | Single command source-of-truth |
| `docs/project_structure.md` | Folder ownership and cleanup policy |
| `docs/architecture.md` | Architecture summary |
| `docs/ovg/README.md` | OVG domain notes |
| `docs/world_graph/README.md` | WorldGraph and Anchor/Signature notes |
| `docs/retrieval/README.md` | Retrieval domain notes |
| `docs/pipeline_refactor_review.md` | Pipeline split risk map and refactor phases |
| `docs/retrieval/raw_json_sync_review_ko.md` | Raw JSON source-of-truth for retrieval result tables |
| `docs/room_localization_query_scenarios.md` | Scenario/query interpretation guide |
| `docs/room_localization_query_results.md` | Paper-oriented room retrieval notes |

## 5. Result and History Policy

1. `data/output/` is ignored by git and is the raw experiment output location.
2. Retrieval result numbers should be synchronized from raw JSON reports.
3. Current retrieval sync source is `docs/retrieval/raw_json_sync_review_ko.md`.
4. Historical result tables should live in history/archive docs, not in latest result docs.
5. Korean paper notes are local-only according to `.gitignore`, but should still be kept current for writing.

## 6. Cleanup Policy

1. Keep `src/citygml_sg/app/pipeline.py` as the stable public orchestration entry point.
2. Put new OVG code under `src/citygml_sg/ovg/`.
3. Put new RoomSignature/AnchorGraph code under `src/citygml_sg/world_graph/`.
4. Put new retrieval query/scoring/matching/reporting code under `src/citygml_sg/retrieval/`.
5. Use `scripts/retrieval/...` as the only documented retrieval command path.
6. Generated cache folders such as `__pycache__/` and `.pytest_cache/` are ignored and can be removed locally, but they are not part of source cleanup.
7. Keep inactive placeholder files out of active source folders unless they have a documented owner and promotion path.
8. Follow `docs/pipeline_refactor_review.md` before changing memory, streaming, or checkpoint behavior.

## 7. Current Extracted Core Modules

| Path | Responsibility |
|---|---|
| `src/citygml_sg/app/reporting.py` | Terminal report and stage timeline logging |
| `src/citygml_sg/evaluation/scorecard.py` | Top-level scorecard construction |
| `src/citygml_sg/evaluation/spatial_metrics.py` | Spatial score submetrics and family-level scoring |
| `src/citygml_sg/relations/spatial_scope.py` | Room-scoped furniture/boundary/opening maps and layered boundary representative selection |
| `src/citygml_sg/relations/spatial_edges.py` | Spatial relation edge generation, `ADJACENT_SURFACE`, `ATTACHED_TO`, vertical relations, and `CONNECTS` fallback |
| `src/citygml_sg/world_graph/citygml_to_graph/geometry_subgraph.py` | LoD geometry, geometry component, polygon, ring, and position subgraph construction |
| `src/citygml_sg/world_graph/citygml_to_graph/appearance_subgraph.py` | Appearance, surface data, and `APPLIES_TO` subgraph construction |

## 8. Phase 5 Cleanup Result

Phase 5 reduced the public orchestration surface without changing the intended import behavior:

1. `run_import_pipeline` now delegates node building, geometry/spatial construction, scorecard assembly, and JSON export to small helper boundaries.
2. CLI exposes only active core commands: `import` and `benchmark`.
3. Removed root-level inactive scripts: `scripts/run_relations.py`, `scripts/run_export_graph.py`.
4. Removed placeholder-only relation modules: `candidate_search.py`, `directional.py`, `intersection.py`, `semantic_filters.py`.
