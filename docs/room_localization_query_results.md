> Latest retrieval numbers should be read from docs/retrieval/raw_json_sync_review_ko.md first. Some legacy tables in this document may still contain older heuristic values until the raw-JSON sync script regenerates them.

# Room Localization Query Results for Paper Notes

Baseline date: 2026-06-04  
Dataset: E-TYPE 201dong IFC4-derived CityGML  
Source report: `data/output/e_type_kitchen_view_query_report.json`

This document records the current query-scenario experiment for paper writing.
It complements:

1. scenario definitions: `docs/room_localization_query_scenarios.md`
2. spatial-relation method details: `docs/spatial_relation_v2_algorithm_notes.md`
3. latest dataset/import results: `docs/experiment_results.md`
4. dataset-level comparison: `docs/dataset_result_comparison.md`
5. follow-up World Graph Retrieval handoff: `docs/world_graph_retrieval_handoff_ko.md`

## 1. Research Purpose

The goal is to test whether the CityGML world graph can support room localization from image-derived view cues.
At this stage, the image pipeline is not yet connected end-to-end. The current experiment approximates an observed view graph with manually selected object categories and spatial evidence terms.

The tested localization logic is:

1. Treat each `Room` node as a candidate location.
2. Match observed object categories against `BuildingFurniture` inside each room.
3. Add evidence from door connectivity.
4. Add evidence from furniture-floor attachment.
5. Add evidence from spatial relations among matched furniture objects.
6. Rank rooms by a relative score.

This is not a fixed 100-point accuracy score. It is a relative candidate-ranking score for comparing rooms within the same graph state.

## 2. Current Scenario

Scenario ID:

```text
combined_room_score
```

Current query input:

```text
furniture_keywords = storage, fridge, table, sofa
source_keywords = sofa
target_keywords = table
min_doors = 1
limit = 10
```

Interpretation:

1. `storage` and `fridge` are treated as strong kitchen evidence.
2. `sofa` and `table` are treated as weaker living/general evidence.
3. Door connectivity is a weak structural prior.
4. Floor attachment is counted only for matched objects.
5. Spatial relation between matched furniture pairs contributes additional evidence.

## 3. Scoring Formula

The current heuristic score is:

```text
total_score =
  object_keyword_score
  + door_score
  + floor_attachment_score
  + furniture_relation_score
```

Object category score:

1. `storage`, `fridge`, `sink`, `counter`, `cabinet`, `kitchen`: `4.0` each
2. `sofa`, `table`, `tv`: `1.0` each
3. other matched categories: fallback weight

Door score:

1. if `door_count >= min_doors`, add `1.0`
2. otherwise add `0.0`

Floor attachment score:

1. matched kitchen object attached to floor: `1.0`
2. matched `sofa/table/tv` attached to floor: `0.25`

Furniture relation score:

1. matched furniture pair with `ADJACENT_TO|TOUCHES|INTERSECTS|ABOVE|BELOW`: `1.0` per pair

## 4. Latest Result Summary

Run summary:

1. output: `data/output/e_type_kitchen_view_query_report.json`
2. started_at: `2026-06-04T01:25:16.294818+00:00`
3. finished_at: `2026-06-04T01:25:19.466820+00:00`
4. scenario: `combined_room_score`
5. row_count: `10`
6. elapsed_ms: `3170.910`

Top candidate:

1. room: `E103`
2. room_id: `GML_1kHyG8MyvB0f943gqBRd9w`
3. total_score: `11.0`
4. matched categories: `fridge`, `storage`
5. score breakdown:
   - object keyword: `8.0`
   - door: `1.0`
   - floor attachment: `2.0`
   - furniture relation: `0.0`

Second candidate:

1. room: `E102`
2. room_id: `GML_1HHLF7HWPDMPZRByktc79s`
3. total_score: `9.5`
4. matched categories: `sofa`, `table`, `fridge`
5. score breakdown:
   - object keyword: `6.0`
   - door: `1.0`
   - floor attachment: `1.5`
   - furniture relation: `1.0`

## 5. Candidate Ranking Table

| Rank | Room | Score | Matched Categories | Object Score | Door Score | Floor Score | Relation Score | Interpretation |
|---:|---|---:|---|---:|---:|---:|---:|---|
| 1 | E103 | 11.0 | fridge, storage | 8.0 | 1.0 | 2.0 | 0.0 | strongest kitchen-like evidence |
| 2 | E102 | 9.5 | sofa, table, fridge | 6.0 | 1.0 | 1.5 | 1.0 | mixed living/kitchen-like evidence |
| 3 | E201 | 1.0 | none | 0.0 | 1.0 | 0.0 | 0.0 | door-only weak candidate |
| 4 | E204 | 1.0 | none | 0.0 | 1.0 | 0.0 | 0.0 | door-only weak candidate |
| 5 | E104 | 1.0 | none | 0.0 | 1.0 | 0.0 | 0.0 | door-only weak candidate |
| 6 | E203 | 1.0 | none | 0.0 | 1.0 | 0.0 | 0.0 | door-only weak candidate |
| 7 | E105 | 1.0 | none | 0.0 | 1.0 | 0.0 | 0.0 | door-only weak candidate |
| 8 | E101 | 1.0 | none | 0.0 | 1.0 | 0.0 | 0.0 | door-only weak candidate |
| 9 | E205 | 1.0 | none | 0.0 | 1.0 | 0.0 | 0.0 | door-only weak candidate |
| 10 | E202 | 1.0 | none | 0.0 | 1.0 | 0.0 | 0.0 | door-only weak candidate |

## 6. Matched Object Evidence

### 6.1 E103

Matched objects:

1. `fridge`
   - id: `GML_1eSSaZ_qKT7jxaJWocOugaK`
   - name: `FP-Revit-RS90AU1-IntegratedFrenchDoorFridgeFreezer-NZ-90001397A:...:2237942`
2. `storage`
   - id: `GML_3r5aiwEHf57xz4XDiKpoeR`
   - name: `STORAGE 01:STORAGE 01:2256319`

Interpretation:

1. Both matched objects are strong kitchen-like cues.
2. Both are floor-attached, contributing `2.0` additional score.
3. The absence of matched furniture-pair spatial relation does not prevent E103 from ranking first because object evidence is strong.

### 6.2 E102

Matched objects:

1. `sofa`
   - id: `GML_1mOyQWSSon0EwrQoyEt3AHg`
2. `table`
   - id: `GML_3kmAd72ILBWOXB9hMPpyRl`
3. `fridge`
   - id: `GML_1mOyQWSSon0EwrQoyEt38cw`

Interpretation:

1. E102 has more matched objects, but two of them are weaker general/living cues.
2. Its furniture-pair relation contributes `1.0`, which helps but does not overcome E103's stronger kitchen evidence.
3. This result shows why category weighting matters: object count alone would over-favor E102.

## 7. Paper Interpretation

The result supports the following claim:

```text
The CityGML-derived world graph can be queried as a room-candidate prior using object categories and spatial-relation evidence. In a kitchen-like view scenario, strong semantic cues such as fridge/storage and floor-attachment evidence ranked E103 above other rooms, while E102 remained a plausible secondary candidate due to mixed sofa/table/fridge evidence.
```

The result should be presented as a proof-of-concept for queryable localization prior, not as final image-based localization accuracy.

## 8. Current Limitation

1. The current run uses heuristic keyword input, not an automatically extracted image view graph.
2. The newly added `--view-graph` mode allows the same query runner to consume `observed_view_graph.json`, but a fresh observed-view-graph result has not been recorded in this report yet.
3. Relation-aware scoring currently stores `relations` from observed view graphs but does not fully score all relation patterns yet.
4. The top-2 margin is `1.5`, so the result is informative but still needs scenario expansion and multiple views for stronger localization confidence.

## 9. Next Experiment to Record

Recommended next run:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_kitchen_view_graph_query_report.json --scenario combined_room_score --limit 10 --view-graph docs/examples/observed_view_graph_kitchen.json
```

After that run, update this document with a second table comparing:

1. heuristic keyword mode
2. observed view graph mode
3. ranking stability
4. score changes by `confidence` and `visibility`

The follow-up `World Graph Retrieval` project should generalize this from a fixed scenario query into schema-validated observed-view-graph retrieval with JSON-to-Cypher generation, relation-aware scoring, and explainable ranked responses.
