# Representation CityGML Building Models into a Queryable Semantic-Spatial Scene Graph

A Python-based research framework for constructing queryable semantic-spatial scene graphs from CityGML building models.

Current baseline: **CityGML 2.0 building-focused pipeline**.

## 1. Purpose

CityGML contains semantic hierarchy and geometry, but downstream query, benchmark, and localization tasks need an explicit graph representation. This project converts CityGML building models into a semantic-spatial scene graph and supports Neo4j-based analysis workflows.

Primary goals:

1. Parse CityGML building-related semantic objects.
2. Normalize geometry metadata such as bbox, centroid, polygon, ring, and position structures.
3. Construct semantic, geometry, and spatial graph relations.
4. Export graph results to JSON and Neo4j.
5. Evaluate graph quality with scorecards, benchmarks, and retrieval scenarios.
6. Support research extensions toward observed-view-graph retrieval and room localization.

## 2. Supported Object Scope

Current supported building object families:

1. `Building`
2. `BuildingPart`
3. `Room`
4. `BoundarySurface`
5. `Opening`
6. `Door`
7. `Window`
8. `BuildingFurniture`
9. `BuildingInstallation` / `IntBuildingInstallation` where present

## 3. Domain Layout

The project is organized around three research domains while keeping the stable CityGML import core intact.

```text
OVG(ImageToGraph)
-> WorldGraph(CityGMLtoGraph + Anchor)
-> Retrieval(Query Generator + Graph Matching)
```

Current layout:

| Area | Path | Role |
|---|---|---|
| Stable core | `src/citygml_sg/app/`, `parsers/`, `modules/`, `extractors/`, `relations/`, `graph/`, `storage/` | CityGML scene graph construction and export |
| OVG | `src/citygml_sg/ovg/` | Observed View Graph schema validation and future image-output adapters |
| WorldGraph | `src/citygml_sg/world_graph/` | RoomSignature, RoomAnchor, and future precomputed anchor features |
| Retrieval | `src/citygml_sg/retrieval/` | Cypher templates, scoring params, graph matching, result reporting |
| Scripts | `scripts/`, `scripts/retrieval/` | Public commands and retrieval experiment commands |
| Docs | `docs/`, `docs/ovg/`, `docs/world_graph/`, `docs/retrieval/` | Research notes, command guides, result summaries |

Detailed ownership: `docs/project_structure.md`.

## 4. Current Key Modules

| Module | Purpose |
|---|---|
| `src/citygml_sg/app/pipeline.py` | Stable import pipeline orchestration |
| `src/citygml_sg/app/reporting.py` | Terminal conversion report and stage timeline helpers |
| `src/citygml_sg/evaluation/scorecard.py` | Node/relation/property scorecard construction |
| `src/citygml_sg/evaluation/spatial_metrics.py` | Spatial coverage, density, plausible coverage, and precision sanity metrics |
| `src/citygml_sg/relations/spatial_inference.py` | Spatial relation inference primitives |
| `src/citygml_sg/relations/spatial_scope.py` | Room-scoped spatial candidate maps and layered boundary representative selection |
| `src/citygml_sg/relations/spatial_edges.py` | Spatial edge generation and `CONNECTS` fallback augmentation |
| `src/citygml_sg/ovg/validation/observed_view_graph.py` | OVG JSON validation and parameter normalization |
| `src/citygml_sg/retrieval/query_generator/room_localization.py` | Room localization Cypher query templates and scenario registry |
| `src/citygml_sg/retrieval/scoring/view_params.py` | Retrieval parameter builder from CLI/OVG input |
| `src/citygml_sg/retrieval/graph_matching/signature_similarity.py` | RoomSignature similarity helper |
| `src/citygml_sg/retrieval/reporting/json_safe.py` | Neo4j result to JSON-safe value conversion |
| `src/citygml_sg/world_graph/signatures/room_signature.py` | Room-level signature dataclass |
| `src/citygml_sg/world_graph/anchor/room_anchor.py` | Room anchor dataclass for future precomputed retrieval |

## 5. Spatial Relations

Current relation set includes semantic, geometry, and inferred spatial relations.

Important spatial/retrieval-facing relations:

1. `INSIDE`
2. `ADJACENT_TO`
3. `TOUCHES`
4. `INTERSECTS`
5. `CONNECTS`
6. `HOSTED_BY`
7. `ADJACENT_SURFACE`
8. `ATTACHED_TO`
9. `ABOVE`
10. `BELOW`

Detailed specs:

1. `docs/spatial_relation_spec_v1.md`
2. `docs/spatial_relation_v2_algorithm_notes.md`
3. `docs/relation_definitions.md`

## 6. Setup

Install dependencies in your Python environment:

```powershell
python -m pip install -U pip
```

```powershell
pip install -e .
```

Configure runtime settings in `configs/default.yaml` or pass another config with `--config`.

Neo4j settings example:

```yaml
neo4j:
  uri: bolt://localhost:7687
  username: neo4j
  password: <your-password>
  database: neo4j
  batch_size: 5000
```

Spatial threshold settings example:

```yaml
spatial:
  touch_epsilon: 0.05
  adjacent_epsilon: 0.50
  intersection_epsilon: 0.000001
```

## 7. Quick Commands

Command source-of-truth: `docs/command_cheatsheet.md`.

Run E-type import and export to Neo4j:

```powershell
python scripts/run_import.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --output data/output/e_type_import.json --to-neo4j --config configs/default.yaml
```

Refresh latest E-type reports with Neo4j sync:

```powershell
python scripts/refresh_latest_reports.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --config configs/default.yaml --dataset-tag "e_type_201dong_ifc4" --to-neo4j --skip-baseline
```

Run benchmark only:

```powershell
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
```

Run E-type kitchen room retrieval from OVG JSON:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_kitchen_view_graph_query_report.json --scenario combined_room_score --limit 10 --view-graph docs/examples/observed_view_graph_kitchen.json
```

Regenerate retrieval result notes from raw JSON:

```powershell
python scripts/retrieval/sync_room_retrieval_docs.py --output docs/retrieval/raw_json_sync_review_ko.md
```

## 8. Script Policy

1. Stable CityGML import commands remain under root `scripts/`.
2. Retrieval experiment commands are canonical under `scripts/retrieval/`.
3. Root-level retrieval wrappers have been removed.
4. Future OVG commands should go under `scripts/ovg/`.
5. Future WorldGraph/RoomSignature commands should go under `scripts/world_graph/`.

## 9. Evaluation and Results

Core evaluation docs:

1. `docs/evaluation_scorecard.md`
2. `docs/testing_and_scoring_guide.md`
3. `docs/query_benchmark_guide.md`
4. `docs/dataset_result_comparison.md`
5. `docs/experiment_results.md`
6. `docs/retrieval/raw_json_sync_review_ko.md`

Raw output policy:

1. `data/output/` is ignored by git.
2. Latest numeric tables should be synchronized from raw JSON outputs.
3. Historical result tables should be kept separate from latest result docs.

## 10. Tests

Run targeted tests as needed:

```powershell
pytest tests/test_pipeline_regression.py
```

```powershell
pytest tests/test_spatial_relation_pairs.py
```

```powershell
pytest tests/test_spatial_inference_refinement.py
```

Future domain tests should be added under:

1. `tests/ovg/`
2. `tests/world_graph/`
3. `tests/retrieval/`

## 11. Main Documentation

1. Project structure: `docs/project_structure.md`
2. Architecture: `docs/architecture.md`
3. Command cheatsheet: `docs/command_cheatsheet.md`
4. OVG domain: `docs/ovg/README.md`
5. WorldGraph domain: `docs/world_graph/README.md`
6. Retrieval domain: `docs/retrieval/README.md`
7. Pipeline refactor review: `docs/pipeline_refactor_review.md`
8. Paper outline mapping: `docs/paper_outline.md`

## 12. Development Policy

1. Keep parser, graph, relation, storage, and retrieval concerns separated.
2. Keep `app/pipeline.py` as the stable public orchestration entry point while extracted helpers are validated.
3. Document every research-facing change in the same work unit.
4. Treat raw JSON reports as the source-of-truth for numeric result tables.
5. Keep commands one-line and copyable in command docs.
