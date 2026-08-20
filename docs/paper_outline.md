# Paper Outline Mapping

This document maps paper sections to implementation and result artifacts.

## 1. Method Sections

| Paper section | Implementation artifacts | Documentation |
|---|---|---|
| Semantic Object Parsing | `src/citygml_sg/parsers/`, `src/citygml_sg/modules/` | `docs/architecture.md` |
| Geometry Normalization | `src/citygml_sg/extractors/`, `src/citygml_sg/app/pipeline.py` | `docs/spatial_relation_v2_algorithm_notes.md` |
| Spatial Relation Extraction | `src/citygml_sg/relations/`, `src/citygml_sg/app/pipeline.py` | `docs/spatial_relation_spec_v1.md`, `docs/spatial_relation_v2_algorithm_notes.md` |
| Scene Graph Construction | `src/citygml_sg/graph/`, `src/citygml_sg/storage/neo4j/` | `docs/graph_schema.md`, `docs/relation_definitions.md` |
| Observed View Graph Input | `src/citygml_sg/ovg/validation/observed_view_graph.py` | `docs/schemas/observed_view_graph.schema.json`, `docs/ovg/README.md` |
| Room Retrieval Query Generation | `src/citygml_sg/retrieval/query_generator/room_localization.py` | `docs/room_localization_query_scenarios.md`, `docs/retrieval/README.md` |
| Room Retrieval Scoring | `src/citygml_sg/retrieval/scoring/view_params.py`, `scripts/retrieval/room_localization_queries.py` | `docs/room_localization_query_results.md` |
| Signature/Anchor Retrieval Extension | `src/citygml_sg/world_graph/signatures/room_signature.py`, `src/citygml_sg/world_graph/anchor/room_anchor.py`, `src/citygml_sg/retrieval/graph_matching/signature_similarity.py` | `docs/world_graph/README.md`, `docs/retrieval/README.md` |

## 2. Experiment Sections

| Experiment section | Artifacts |
|---|---|
| Dataset-level result comparison | `docs/dataset_result_comparison.md` |
| Latest experiment results | `docs/experiment_results.md` |
| Query benchmark | `docs/query_benchmark_guide.md`, `data/output/benchmark_report.json` |
| Room-localization scenario results | `docs/room_localization_query_results.md`, `docs/retrieval/raw_json_sync_review_ko.md` |
| Room retrieval metrics | `data/output/e_type_room_retrieval_metrics.json`, `scripts/retrieval/evaluate_room_retrieval_metrics.py` |
| Timing profile | `scripts/retrieval/profile_room_localization_stages.py`, stage profile JSON outputs |
| World Graph Retrieval handoff/design | `docs/world_graph_retrieval_handoff_ko.md` |

## 3. Source-of-Truth Policy

1. Raw experiment outputs in `data/output/` are the source-of-truth for numeric tables.
2. Retrieval result tables should be regenerated with `scripts/retrieval/sync_room_retrieval_docs.py`.
3. Latest docs should not mix old heuristic numbers with raw JSON synchronized values.
4. Historical values should be moved to history/archive docs.
