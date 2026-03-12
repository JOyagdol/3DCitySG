<<<<<<< HEAD
# 3DCitySG
=======
# CityGML Scene Graph

A Python-based research framework for constructing **semantic-spatial scene graphs** from **CityGML** building models.

This project is a Python migration and redesign of an existing Java-based CityGML-to-Neo4j pipeline.
It focuses on transforming CityGML building data into an enriched graph representation that includes:

- semantic object hierarchy
- geometric metadata
- spatial relations
- graph persistence in Neo4j

The framework is being developed as the implementation basis for research on **CityGML-based spatial scene graph construction**.

---

## Overview

CityGML provides rich semantic and geometric information for 3D city models, but many practical applications require a more explicit and queryable graph representation.

This project bridges that gap by converting CityGML building-related objects into a structured scene graph that supports:

- semantic hierarchy extraction
- geometry-aware graph enrichment
- indoor/outdoor spatial relation modeling
- graph-based querying and analysis

The current priority is building-centric graph construction with support for:

- Building
- BuildingPart
- Room
- BoundarySurface
- Opening
- Door
- Window
- BuildingFurniture

---

## Objectives

1. Parse CityGML building-related objects into explicit internal data models
2. Normalize geometry-derived metadata such as bounding boxes and centroids
3. Extract semantic and spatial relations between objects
4. Construct an internal scene graph representation
5. Persist the graph into Neo4j for querying and downstream analysis
6. Provide a research-friendly architecture for future extension into:
   - ontology alignment
   - sensor linkage
   - document linkage
   - LLM/agent-based reasoning
   - multimodal scene understanding

---

## Research Contributions

This research implementation contributes:

- A CityGML-specific semantic-spatial graph construction pipeline (not a generic GIS parser)
- Explicit treatment of `BuildingFurniture` as a first-class indoor scene object in v1
- Separation of concerns between parsing, relation extraction, graph construction, and persistence
- A practical bridge from CityGML semantics to graph-native querying workflows
- A modular base for future ontology/agent/multimodal research extensions

---

## Key Features

### Semantic object parsing

Parse building-related CityGML objects into structured Python domain models.

### Geometry normalization

Extract and compute geometry metadata such as:

- LoD
- bounding boxes
- centroids
- geometry references

### Scene graph construction

Construct internal graph nodes and edges for:

- hierarchical structure
- semantic containment
- opening relationships
- boundary associations

### Spatial relation extraction

Support enrichment with:

- `CONTAINS`
- `INSIDE`
- `BOUNDED_BY`
- `HAS_OPENING`
- `ADJACENT_TO`
- `TOUCHES`
- `INTERSECTS`
- `CONNECTS`

### Neo4j persistence

Store enriched graph objects in Neo4j for graph querying and analysis.

### Research-oriented modularity

Keep parsing, graph construction, relation extraction, and database persistence separated for clean experimentation and future expansion.

---

## Requirements

- Python 3.10+
- `pip`
- Optional: Neo4j 5.x (for persistence stage)

Current dependencies are managed in `pyproject.toml`.

---

## Installation and Setup

### 1) Clone and enter project directory

```bash
git clone <your-repo-url>
cd 3DCitySG
```

### 2) Create and activate virtual environment

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

### 3) Install package in editable mode

```bash
python -m pip install -U pip
pip install -e .
```

---

## How To Run

### Quick test with provided sample

```bash
python scripts/run_import.py --input data/input/sample_citygml_v2.gml
```

### Run with your own CityGML file

```bash
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json
```

### Run via package CLI

```bash
python -m citygml_sg.app.cli import --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json
```

Output JSON is written to:

- `data/output/import_summary.json` (default), or
- the file passed to `--output`

---

## Current Scope

### In scope

Priority object families:

- Building
- BuildingPart
- Room
- BoundarySurface
- Opening
- Door
- Window
- BuildingFurniture

Priority relation families:

- hierarchy relations
- containment relations
- adjacency relations
- contact/intersection relations
- connectivity relations

### Out of scope for now

- full IFC/BIM support
- point cloud pipelines
- computer vision pipelines
- UI/dashboard development
- cloud deployment
- microservice decomposition
- production-scale optimization
- broad support for all CityGML modules at once

---

## Why BuildingFurniture Matters

`BuildingFurniture` is treated as a first-class object in this project.

It strengthens indoor scene graph representation and enables future reasoning over:

- room interior composition
- furniture containment
- furniture-to-wall adjacency
- furniture accessibility and connectivity
- indoor semantic-spatial analysis

This is part of intended v1 scope, not an optional add-on.

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

- This is a migration project, but not a line-by-line Java translation.
- Keep parsing, relation extraction, graph construction, and persistence decoupled.
- Prefer clear typed data models and testable functions.
- Avoid overengineering and premature abstraction.
>>>>>>> Initial Python migration skeleton for CityGML scene graph
