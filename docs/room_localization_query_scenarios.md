> Latest retrieval numbers should be read from docs/retrieval/raw_json_sync_review_ko.md first. Some legacy tables in this document may still contain older heuristic values until the raw-JSON sync script regenerates them.

# Room Localization Cypher Scenario Guide

Purpose:
1. Test whether an image-derived view graph schema can be converted into Neo4j world-graph queries.
2. Treat each `Room` as a candidate location and rank it using object, opening, and spatial-relation evidence.
3. Validate the world graph as a localization prior, not just as a spatial-relation extraction output.

Result notes:

1. Latest paper-oriented result summary: `docs/room_localization_query_results.md`
2. Latest raw report: `data/output/e_type_kitchen_view_query_report.json`
3. World Graph Retrieval handoff notes: `docs/world_graph_retrieval_handoff_ko.md`
4. Observed view graph schema draft: `docs/schemas/observed_view_graph.schema.json`

## 1) Prerequisites

1. Neo4j must be running.
2. The target dataset must already be synchronized to Neo4j.
3. For E-TYPE, run `run_import.py --to-neo4j` or `refresh_latest_reports.py --to-neo4j` first.

## 2) Commands

Run all scenarios:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_room_localization_query_report.json --scenario all --limit 10
```

Run only the combined room score:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_room_localization_query_report.json --scenario combined_room_score --limit 10 --furniture-keywords storage fridge table sofa
```

Check only sofa-table pair relations:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_sofa_table_query_report.json --scenario furniture_pair_relation --limit 10 --source-keywords sofa --target-keywords table
```

Run the SmartCity Lab window/boundary view scenario:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/smartcity_lab_corridor_window_query_report.json --scenario opening_boundary_room_score --view-graph docs/examples/observed_view_graph_smartcity_corridor_window.json
```

## 3) Scenario Set

1. `room_inventory`: per-room furniture/opening inventory.
2. `object_keyword_candidates`: room ranking using observed furniture categories. Each object receives one normalized category only.
3. `opening_host_surface`: `Opening --HOSTED_BY--> BoundarySurface` inspection.
4. `surface_attachment`: furniture-surface evidence inspection.
5. `furniture_pair_relation`: sofa-table style pair relation inspection.
6. `opening_boundary_room_score`: furniture-sparse corridor/lab-view ranking using window, door, wall/floor boundary, wall-floor topology, and room-installation evidence.
7. `combined_room_score`: combined ranking using object, door, floor-attachment, and furniture-pair evidence.

## 4) View Graph Schema Concept

```json
{
  "objects": [
    {"alias": "sofa", "type": "BuildingFurniture", "category": "sofa"},
    {"alias": "table", "type": "BuildingFurniture", "category": "table"},
    {"alias": "storage", "type": "BuildingFurniture", "category": "storage"},
    {"alias": "fridge", "type": "BuildingFurniture", "category": "fridge"},
    {"alias": "window", "type": "Opening", "category": "Window"},
    {"alias": "door", "type": "Opening", "category": "Door"},
    {"alias": "column", "type": "IntBuildingInstallation", "category": "column"}
  ],
  "relations": [
    ["sofa", "NEAR|ADJACENT_TO", "table"],
    ["sofa", "ON_FLOOR|ATTACHED_TO", "FloorSurface"],
    ["table", "ON_FLOOR|ATTACHED_TO", "FloorSurface"],
    ["window", "HOSTED_BY", "WallSurface"],
    ["Room", "ROOM_INSTALLATION", "column"]
  ]
}
```

## 5) Output

Default output:

```text
data/output/e_type_room_localization_query_report.json
```

Key fields:

1. `scenarios[*].top_room`
2. `scenarios[*].rows`
3. `matched_furniture_keywords`
4. `score_breakdown`

`combined_room_score` is a relative ranking score, not a fixed 100-point score.

Scoring policy:

1. Each object is assigned one normalized category only.
   - Priority: `sink > counter > cabinet > storage > fridge/freezer/refrigerator > sofa > tv/display > table`
2. Kitchen categories are strong evidence.
   - `sink`, `counter`, `cabinet`, `storage`, `fridge`, `kitchen`: `4.0` each
3. Living/general furniture categories are weaker evidence.
   - `sofa`, `table`, `tv`: `1.0` each
4. Door connectivity contributes `1.0` when at least one connected door exists.
5. Floor attachment is counted only for matched objects.
   - kitchen object attached to floor: `1.0`
   - `sofa/table/tv` attached to floor: `0.25`
6. Spatial relation between matched object pairs contributes `1.0` per pair.

## 6) observed_view_graph.json-Based Scoring Input

The script now supports two modes.

1. Heuristic mode
   - When `--view-graph` is not provided, the script keeps using `--furniture-keywords` and built-in category weights.
   - Kitchen evidence (`storage`, `fridge`, `sink`, `counter`, `cabinet`) is weighted strongly; living/general evidence (`sofa`, `table`, `tv`) is weighted weakly.
2. Observed view graph mode
   - When `--view-graph observed_view_graph.json` is provided, room ranking uses the JSON `objects` as observed evidence.
   - Per-object score is `weight * confidence * visibility`.
   - Missing `weight` falls back to the existing heuristic default.
   - Missing `confidence` or `visibility` defaults to `1.0`.

Example input file:

```text
docs/examples/observed_view_graph_kitchen.json
```

Example command:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/e_type_kitchen_view_graph_query_report.json --scenario combined_room_score --limit 10 --view-graph docs/examples/observed_view_graph_kitchen.json
```

Example schema:

```json
{
  "objects": [
    {"alias": "storage", "type": "BuildingFurniture", "category": "storage", "weight": 4.0, "confidence": 0.95, "visibility": 1.0},
    {"alias": "fridge", "type": "BuildingFurniture", "category": "fridge", "weight": 4.0, "confidence": 0.9, "visibility": 1.0},
    {"alias": "sofa", "type": "BuildingFurniture", "category": "sofa", "weight": 1.0, "confidence": 0.65, "visibility": 0.35}
  ],
  "relations": [
    ["storage", "ATTACHED_TO", "FloorSurface"],
    ["fridge", "ATTACHED_TO", "FloorSurface"]
  ]
}
```

Interpretation:

1. This is not full 2D view-graph matching yet. It is an intermediate bridge that injects observed object evidence into world-graph room ranking.
2. When the image pipeline starts producing `observed_view_graph.json`, the same query runner can be reused with fewer heuristic keyword arguments.
3. `relations` are currently preserved in the report and can be used later for relation-aware scoring.

## 7) Latest Recorded Result

Source:

```text
data/output/e_type_kitchen_view_query_report.json
```

Run:

1. dataset: E-TYPE 201dong
2. scenario: `combined_room_score`
3. input mode: heuristic object categories
4. furniture keywords: `storage`, `fridge`, `table`, `sofa`
5. row_count: `10`
6. elapsed_ms: `3170.910`

Top candidates:

| Rank | Room | Score | Matched Categories | Score Breakdown | Interpretation |
|---:|---|---:|---|---|---|
| 1 | E103 | 11.0 | fridge, storage | object=8.0, door=1.0, floor=2.0, relation=0.0 | strongest kitchen-like evidence |
| 2 | E102 | 9.5 | sofa, table, fridge | object=6.0, door=1.0, floor=1.5, relation=1.0 | plausible mixed living/kitchen candidate |

Paper interpretation:

1. The world graph can rank room candidates from observed object/spatial cues.
2. Strong kitchen cues (`fridge`, `storage`) outweighed a larger but weaker mixed furniture set (`sofa`, `table`, `fridge`).
3. This result is a queryable localization-prior test, not final image-based localization accuracy.

## 8) SmartCity Lab Window/Boundary View Scenario

This scenario is intended for a furniture-sparse corridor or lab image where visible cues are mostly windows/openings, wall surfaces, floor surfaces, and wall-floor junctions.

Input JSON:

```text
docs/examples/observed_view_graph_smartcity_corridor_window.json
```

Command:

```powershell
python scripts/retrieval/room_localization_queries.py --config configs/default.yaml --output data/output/smartcity_lab_corridor_window_query_report.json --scenario opening_boundary_room_score --view-graph docs/examples/observed_view_graph_smartcity_corridor_window.json
```

Scored evidence:

1. `window_score`: room-boundary window evidence.
2. `door_score`: door-room `CONNECTS` evidence.
3. `wall_surface_score`: room wall boundary evidence.
4. `floor_surface_score`: room floor boundary evidence.
5. `boundary_topology_score`: `WallSurface --ADJACENT_SURFACE-- FloorSurface` evidence.
6. `installation_score`: observed column/installation evidence matched through `Room -ROOM_INSTALLATION-> IntBuildingInstallation`.
   - If an observed object has `target_id` or `target_ids`, the query reports the node under `target_installation_evidence`.
   - Explicit target evidence confirms the node exists, but it contributes to `installation_score` only when the node is room-linked through `ROOM_INSTALLATION`.

For datasets with sparse room-level boundary links, the scenario also uses fallback evidence:

1. wall fallback: `Room <-CONNECTS- Opening -HOSTED_BY-> BoundarySurface`
2. floor fallback: connected opening host wall `--ADJACENT_SURFACE--` floor-like boundary
3. topology fallback: host-wall to floor adjacency around connected openings

Current limitation:

1. Visible columns/pillars are represented as `IntBuildingInstallation`/installation cues and scored when the world graph exposes room-level `ROOM_INSTALLATION` evidence.
2. If the SmartCity Lab graph has sparse `Room -BOUNDED_BY` or window links, the result may have low scores or ties.
3. After running, record the top candidates and score breakdown in `docs/room_localization_query_results_ko.md`.
