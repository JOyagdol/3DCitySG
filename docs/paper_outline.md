# Paper Outline Mapping

This document maps paper sections to implementation and result artifacts.

## Method Sections

1. Semantic Object Parsing
   - code: `src/citygml_sg/parsers/`, `src/citygml_sg/modules/`
2. Geometry Normalization
   - code: `src/citygml_sg/extractors/`
3. Spatial Relation Extraction
   - code: `src/citygml_sg/relations/`, `src/citygml_sg/app/pipeline.py`
   - docs: `docs/spatial_relation_v2_algorithm_notes.md`
4. Scene Graph Construction in Neo4j
   - code: `src/citygml_sg/graph/`, `src/citygml_sg/storage/neo4j/`
5. Query-Based Room Localization Prior
   - code: `scripts/room_localization_queries.py`
   - docs: `docs/room_localization_query_scenarios.md`, `docs/room_localization_query_results.md`
6. World Graph Retrieval Interface
   - schema: `docs/schemas/observed_view_graph.schema.json`
   - handoff/design notes: `docs/world_graph_retrieval_handoff_ko.md`

## Experiment Sections

1. Dataset-level result comparison: `docs/dataset_result_comparison.md`
2. Latest experiment results: `docs/experiment_results.md`
3. Query benchmark guide: `docs/query_benchmark_guide.md`
4. Room-localization query result notes: `docs/room_localization_query_results.md`
5. World Graph Retrieval handoff/design notes: `docs/world_graph_retrieval_handoff_ko.md`
