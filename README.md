# CityGML Semantic-Spatial Scene Graph

A Python-based research framework for constructing semantic-spatial scene graphs from CityGML building models.

This project is research-first: it focuses on semantic and spatial scene graph construction for indoor/outdoor building context, not on generic GIS conversion.
Current conversion baseline is **CityGML 2.0**.

---

## Overview

CityGML contains rich semantic and geometric structure, but many downstream tasks need an explicit graph representation.
This framework converts building-related CityGML objects into a scene graph that supports:

- semantic hierarchy extraction
- geometry-aware enrichment
- spatial relation modeling
- graph-ready outputs for Neo4j and analysis workflows

Current stable parsing and scorecard assumptions are aligned to **CityGML 2.0 building module structures**.

Priority object families:

- Building
- BuildingPart
- Room
- BoundarySurface
- Opening (Door, Window)
- BuildingFurniture

---

## Objectives

1. Parse CityGML building-related objects into explicit internal models
2. Normalize geometry metadata (LoD, bbox/centroid pipeline-ready fields)
3. Extract semantic and spatial relations
4. Construct an internal scene graph
5. Persist graph data to Neo4j
6. Support future research extensions:
   - ontology alignment
   - sensor/document linkage
   - LLM or agent-based querying
   - multimodal scene understanding

---

## Research Contributions

- CityGML-specific semantic-spatial graph construction pipeline for building scenes
- Explicit v1 support for BuildingFurniture as a first-class indoor object
- Clear separation between parsing, relation logic, graph construction, and persistence
- Reproducible graph output path for experimentation and paper-oriented analysis

---

## Key Features

### Semantic object parsing

Parses CityGML object families into structured domain representations.

### Scene graph construction

Builds internal node and edge structures from parsed semantics.

### Spatial-semantic relations

Targets relation enrichment for:

- `CONTAINS`
- `CONSISTS_OF_BUILDING_PART`
- `INTERIOR_ROOM`
- `OUTER_BUILDING_INSTALLATION`
- `INTERIOR_BUILDING_INSTALLATION`
- `ROOM_INSTALLATION`
- `BOUNDED_BY`
- `HAS_OPENING`
- `HAS_APPEARANCE`
- `HAS_SURFACE_DATA`
- `APPLIES_TO`
- `INSIDE`
- `ADJACENT_TO`
- `TOUCHES`
- `CONNECTS`
- `INTERSECTS` (planned; extraction not enabled in current pipeline)

### Neo4j persistence

Provides a dedicated storage layer (`storage/neo4j`) so DB integration stays decoupled from core graph logic.

---

## Requirements

- Python 3.10+
- pip
- Optional: Neo4j 5.x for DB persistence experiments
- CityGML 2.0 input files for v1 baseline runs (3.0 expansion path reserved in config)

Dependencies are defined in `pyproject.toml`.

---

## Installation and Setup

### 1) Clone repository

```bash
git clone https://github.com/<YOUR_ID>/3DCitySG.git
cd 3DCitySG
```

### 2) Create virtual environment

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
. .venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3) Install in editable mode

```bash
python -m pip install -U pip
pip install -e .
```

### 4) Configure your own Neo4j connection

Before running `--to-neo4j`, set your local Neo4j connection in
`configs/default.yaml` (or pass your own config file with `--config`).

Use values from your own environment:

```yaml
neo4j:
  uri: bolt://<host>:<port>
  username: <your_username>
  password: <your_password>
  database: <your_database>
  batch_size: 5000
```
Example (local default install): `bolt://localhost:7687`, `neo4j`, `<your-password>`, `neo4j`.
For large imports, tune `batch_size` (e.g., `2000`~`10000`) based on memory and throughput.

---

## How To Run

### Run with sample CityGML

```bash
python scripts/run_import.py --input data/input/sample_citygml_v2.gml
```

### Run with your dataset

```bash
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json
```

### Run and persist to Neo4j

```bash
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json --to-neo4j --config configs/default.yaml
```

### Run via module CLI

```bash
python -m citygml_sg.app.cli import --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json
```

```bash
python -m citygml_sg.app.cli import --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json --to-neo4j --config configs/default.yaml
```

Generated output:

- default: `data/output/import_summary.json`
- custom: path passed via `--output`

Runtime log now includes in-progress timeline, for example:

```text
[Timeline] [1/6] [--------------------------] parse_xml START
[Timeline] [1/6] [####----------------------] parse_xml DONE (2.184s)
[Timeline] [2/6] [####----------------------] collect_semantics START
...
```

When `--to-neo4j` is enabled, both node and edge export progress are printed as percent bars.

---

## CityGML Version Policy

- v1 default target: **CityGML 2.0**
- Config field: `project.citygml_version` (in `configs/default.yaml`)
- Code constants:
  - `citygml_sg.config.DEFAULT_CITYGML_VERSION`
  - `citygml_sg.config.SUPPORTED_CITYGML_VERSIONS`
- `3.0` is reserved for extension; do not switch default baseline without explicit scope update.

---

## Evaluation Scorecard

- Score formula: `overall = 0.40 * node + 0.30 * relation + 0.30 * property`
- Fairness rule: expected totals are computed from currently supported extraction scope, not every possible CityGML tag.
- Detailed criteria and interpretation guide: `docs/evaluation_scorecard.md`

---

## Regression Testing

- Guide (why/how/policy): `docs/regression_testing.md`
- Quick run:

```bash
pytest tests/test_pipeline_regression.py
```

---

## Planned Stubs

- Placeholder modules not wired in v1 runtime path are tracked in:
  - `docs/module_stubs.md`

---

## Development Summary (Korean)

- 한국어 개발 진행 요약: `docs/development_summary_ko.md`

---

## Current Scope

### In scope (v1 priority)

- Building
- BuildingPart
- Room
- BoundarySurface
- Opening, Door, Window
- BuildingFurniture

### Out of scope (current stage)

- full IFC/BIM conversion
- point cloud and CV pipelines
- UI/dashboard development
- cloud/microservice deployment
- production-scale optimization

---

## Why BuildingFurniture Matters

`BuildingFurniture` is treated as mandatory in v1, not optional.
It strengthens indoor scene semantics and enables future reasoning on:

- room interior composition
- furniture containment
- furniture-to-boundary relations
- accessibility/connectivity analysis

---

## Architecture

```text
src/citygml_sg/
|-- app/
|-- config/
|-- domain/
|-- parsers/
|-- extractors/
|-- modules/
|   |-- building/
|   |-- building_part/
|   |-- room/
|   |-- boundary_surface/
|   |-- opening/
|   `-- building_furniture/
|-- relations/
|-- graph/
|-- storage/
|   `-- neo4j/
`-- utils/
```

---

## Development Notes

### Updated implementation status

- Added import runner with explicit file I/O arguments:
  - `python scripts/run_import.py --input <path> --output <path>`
- Added module-level parsing hooks for:
  - Building, BuildingPart, Room, BoundarySurface, Opening (Door/Window), BuildingFurniture
- Added schema-alignment object parsing:
  - BuildingInstallation, IntBuildingInstallation, Address
- Added BoundarySurface subtype coverage:
  - OuterCeilingSurface, OuterFloorSurface
- Added node property enrichment from CityGML content:
  - `gml:name` -> `gml_name`, `gml_name_all`
  - `gen:*Attribute` -> flattened node properties (e.g., `attr_grossplannedarea`)
- Added graph build path that currently generates:
  - `CONTAINS` (Building/BuildingPart/Room hierarchy and Room->Furniture)
  - `CONSISTS_OF_BUILDING_PART` (Building/BuildingPart->BuildingPart)
  - `INTERIOR_ROOM` (Building/BuildingPart->Room)
  - `OUTER_BUILDING_INSTALLATION` (Building/BuildingPart->BuildingInstallation)
  - `INTERIOR_BUILDING_INSTALLATION` (Building/BuildingPart->IntBuildingInstallation)
  - `ROOM_INSTALLATION` (Room->IntBuildingInstallation)
  - `BOUNDED_BY` (Building/BuildingPart/Room/Installation->BoundarySurface)
  - `HAS_OPENING` (BoundarySurface->Opening)
  - `HAS_APPEARANCE` / `HAS_SURFACE_DATA` / `APPLIES_TO` (Appearance subgraph)
  - `CONNECTS` (Opening->Room)
  - `INSIDE` (Furniture->Room)
- Added geometry subgraph extraction:
  - object -> `HAS_GEOMETRY` -> Polygon
  - Polygon -> `HAS_RING` -> LinearRing
  - LinearRing -> `HAS_POS` -> Position(x, y, z, order)
- Added LoD geometry structure preservation:
  - object -> `HAS_LOD_GEOMETRY` -> Solid/MultiSurface/MultiCurve
  - Solid/MultiSurface -> `HAS_GEOMETRY_MEMBER` -> Polygon
- Added JSON export for parsed graph summary:
  - node counts, relation counts, node list, edge list
- Added import execution timeline logs:
  - per-stage START/DONE/SKIP messages with progress bar
  - final stage timeline with duration bars
- Added sample CityGML input for quick smoke tests:
  - `data/input/sample_citygml_v2.gml`

### Design principles

- Keep parser, relation extraction, graph builder, and storage layers decoupled
- Prefer typed, testable, explicit modules over deep abstraction
- Focus on research iteration speed and reproducibility
