# Architecture

This project has two layers:

1. Stable CityGML scene graph construction core.
2. Research-facing OVG, WorldGraph anchor, and Retrieval extensions.

## 1. Stable Core

| Package | Role |
|---|---|
| `app` | Pipeline orchestration, reporting helpers, and package CLI entry points |
| `parsers` | Raw CityGML/CityJSON loading and namespace handling |
| `modules` | Object-family-specific parsing and mapping |
| `extractors` | Geometry, bbox, centroid, and metadata extraction |
| `relations` | Spatial relation inference, room-scoped candidate selection, and spatial edge generation |
| `evaluation` | Scorecard and spatial metric construction |
| `graph` | In-memory graph schema and builders |
| `storage` | JSON and Neo4j persistence adapters |
| `config` | Runtime configuration and CityGML version policy |
| `utils` | Shared utility helpers |

## 2. Research Domains

| Package | Role |
|---|---|
| `ovg` | Observed View Graph validation and future image-output adapters |
| `world_graph` | RoomSignature, RoomAnchor, and future precomputed world graph features |
| `retrieval` | OVG-to-Cypher templates, scoring params, graph matching, and reports |

## 3. Execution Policy

1. Core import commands remain at root `scripts/` for stability.
2. Retrieval commands are canonical under `scripts/retrieval/`.
3. Root-level retrieval wrappers have been removed.
4. `app/pipeline.py` remains the stable public orchestration entry point while reporting, scorecard, and spatial relation helpers are extracted behind compatible callbacks.

Detailed file ownership: `docs/project_structure.md`.
Command source-of-truth: `docs/command_cheatsheet.md`.
Pipeline split plan: `docs/pipeline_refactor_review.md`.
