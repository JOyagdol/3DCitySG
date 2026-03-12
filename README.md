# CityGML Semantic-Spatial Scene Graph

A Python-based research framework for constructing semantic-spatial scene graphs from CityGML building models.

This project is research-first: it focuses on semantic and spatial scene graph construction for indoor/outdoor building context, not on generic GIS conversion.

---

## Overview

CityGML contains rich semantic and geometric structure, but many downstream tasks need an explicit graph representation.
This framework converts building-related CityGML objects into a scene graph that supports:

- semantic hierarchy extraction
- geometry-aware enrichment
- spatial relation modeling
- graph-ready outputs for Neo4j and analysis workflows

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
- `BOUNDED_BY`
- `HAS_OPENING`
- `INSIDE`
- `ADJACENT_TO`
- `TOUCHES`
- `INTERSECTS`
- `CONNECTS`

### Neo4j persistence

Provides a dedicated storage layer (`storage/neo4j`) so DB integration stays decoupled from core graph logic.

---

## Requirements

- Python 3.10+
- pip
- Optional: Neo4j 5.x for DB persistence experiments

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

### Run via module CLI

```bash
python -m citygml_sg.app.cli import --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json
```

Generated output:

- default: `data/output/import_summary.json`
- custom: path passed via `--output`

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
- Added node property enrichment from CityGML content:
  - `gml:name` -> `gml_name`, `gml_name_all`
  - `gen:*Attribute` -> flattened node properties (e.g., `attr_grossplannedarea`)
- Added graph build path that currently generates:
  - `CONTAINS` (Building/BuildingPart/Room hierarchy and Room->Furniture)
  - `BOUNDED_BY` (Room->BoundarySurface)
  - `HAS_OPENING` (BoundarySurface->Opening)
  - `CONNECTS` (Opening->Room)
  - `INSIDE` (Furniture->Room)
- Added geometry subgraph extraction:
  - object -> `HAS_GEOMETRY` -> Polygon
  - Polygon -> `HAS_RING` -> LinearRing
  - LinearRing -> `HAS_POS` -> Position(x, y, z, order)
- Added JSON export for parsed graph summary:
  - node counts, relation counts, node list, edge list
- Added sample CityGML input for quick smoke tests:
  - `data/input/sample_citygml_v2.gml`

### Design principles

- Keep parser, relation extraction, graph builder, and storage layers decoupled
- Prefer typed, testable, explicit modules over deep abstraction
- Focus on research iteration speed and reproducibility
