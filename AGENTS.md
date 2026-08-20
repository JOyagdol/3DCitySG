# AGENTS.md

## Project Overview

This project is a **research-focused CityGML semantic-spatial scene graph framework**.
Current implementation baseline is **CityGML 2.0**.

The codebase is informed by prior Java work, but the primary goal is not one-to-one migration.
It targets:

1. CityGML semantic object parsing
2. Geometry normalization
3. Spatial relation extraction
4. Scene graph construction
5. Neo4j graph persistence
6. Research extensibility for:
   - ontology alignment
   - sensor/document linkage
   - LLM/agent-based querying
   - multimodal scene understanding

This codebase is the implementation basis for research on **CityGML-based spatial scene graph construction (CityGML 2.0 baseline)**.

## Primary Goal

Build a Python-based CityGML scene graph pipeline that supports:

- Building
- BuildingPart
- Room
- BoundarySurface
- Opening
- Door
- Window
- BuildingFurniture

The system must support both:

- semantic hierarchy extraction
- spatial relation enrichment

This is specifically a **CityGML indoor/outdoor semantic-spatial graph construction** project.

## Current Scope

### In Scope

- Parse CityGML building-related objects
- Create internal graph node/edge representations
- Extract geometry metadata:
  - geometry references
  - bounding boxes
  - centroids
  - LoD
- Generate hierarchy relations:
  - `CONTAINS`
  - `BOUNDED_BY`
  - `HAS_OPENING`
- Generate spatial relations:
  - `INSIDE`
  - `ADJACENT_TO`
  - `TOUCHES`
  - `INTERSECTS`
  - `CONNECTS`
- Persist enriched graphs to Neo4j

### Explicitly In Scope for v1

- Building
- BuildingPart
- Room
- BoundarySurface
- Opening
- Door
- Window
- BuildingFurniture

### Out of Scope for Now

- full IFC/BIM conversion
- point cloud processing pipelines
- computer vision pipelines
- UI/dashboard development
- document ingestion systems
- RAG/chat systems
- production-scale optimization
- cloud deployment infrastructure
- microservice architecture
- support for every CityGML module at once

## Development Philosophy

This is a migration project, but **not** a line-by-line translation project.

The Python codebase should:

- preserve useful semantic structure from the Java project
- improve modularity and research extensibility
- separate parsing, graph construction, relation extraction, and storage concerns
- stay clean, typed, and easy to iterate on

Do **not** mechanically mirror Java classes if better Python structure exists.

Prefer:

- simplicity
- explicitness
- modular design
- testable functions
- typed dataclasses and clean models

Avoid:

- premature abstraction
- unnecessary deep inheritance
- database-coupled business logic
- overengineering

## Engineering Conventions

- Keep parser logic and relation logic separated.
- Keep graph model and persistence adapter separated (`graph/` vs `storage/neo4j/`).
- Treat `BuildingFurniture` as a first-class v1 object.
- Use clear type hints for all public functions.
- Keep relation labels uppercase and explicit (`CONTAINS`, `INSIDE`, etc.).
- Implement v1 functions first; avoid speculative framework code.
- Add concise docstrings for non-trivial modules.
- Keep documentation synchronized with code changes in every task.
- Paper-oriented documentation is required for research-facing changes:
  - When adding or changing query scenarios, scoring logic, spatial-relation logic, benchmark behavior, or experiment outputs, update the relevant paper/reference docs in the same work unit.
  - For room-localization or view-graph matching scenarios, document the scenario definition, command, raw result path, top candidates, score breakdown, interpretation, limitations, and paper-ready summary.
  - Keep Korean paper notes synchronized first for active thesis/paper writing, and update English counterparts when the change affects shared project documentation.
- Python command execution ownership:
  - The user runs Python/Conda commands locally.
  - The assistant provides exact commands and expected checks, but does not execute those Python commands.
- When behavior/scope/commands/metrics change, update related docs in the same work unit:
  - `README.md`
  - `docs/*` (scorecard, schema, relations, regression, stubs, summaries)
  - `AGENTS.md` conventions when policy changes

## Behavioral Execution Principles

The project follows Karpathy-inspired behavioral guidelines for coding-agent execution.

1. Think Before Coding
   - State assumptions explicitly.
   - If requirements are ambiguous, surface interpretations instead of silently picking one.
   - Ask clarifying questions when uncertainty changes implementation risk.
   - Push back when a clearly simpler and safer approach exists.

2. Simplicity First
   - Implement the minimum change that solves the requested task.
   - Avoid speculative abstractions/configurability not requested by the user.
   - Avoid overengineering and impossible-scenario handling unless required by scope.

3. Surgical Changes
   - Change only lines directly required for the request.
   - Do not refactor or reformat unrelated code.
   - Preserve existing style and structure.
   - Remove only dead code introduced by your own change; report unrelated dead code separately.

4. Goal-Driven Execution
   - Define concrete success criteria before implementation for non-trivial tasks.
   - For multi-step work, map each step to a verification check.
   - Prefer verifiable outcomes (tests, metrics, checks) over subjective completion.

## CityGML Version Baseline (Required)

- Default conversion target is **CityGML 2.0** for current v1 research experiments.
- Keep this explicit in documentation (`README.md`, scorecard docs, run guides).
- Keep version constants/config variables ready for future expansion:
  - `project.citygml_version` in config
  - `SUPPORTED_CITYGML_VERSIONS` / `DEFAULT_CITYGML_VERSION` in code
- If adding CityGML 3.0 parsing paths, do not silently change v1 defaults.

## Runtime Reporting Convention (Required)

For all import/transform pipeline executions, print a **terminal conversion report** and keep it maintained as features evolve.

Minimum required report content:

- Building-centric main feature count (`Building` count)
- Theme counts:
  - semantic nodes
  - geometry nodes
  - semantic relations
  - spatial relations
  - geometry relations
- Node type counts and relation type counts
- Property enrichment stats:
  - `gml_name` coverage
  - generic attribute coverage
- Geometry density stats:
  - rings per polygon
  - positions per ring
- Per-building breakdown:
  - parts, rooms, boundaries, openings, furniture
  - polygons, rings, positions
  - naming/attribute stats
- Stage checklist and completion status (`DONE`/`NONE`)
- Stage durations (seconds) and total runtime
- In-progress timeline logs during execution:
  - per-stage `START` / `DONE` / `SKIP`
  - stage progress bar (`[####-----]`) and elapsed time

When new transformation steps are added, update this report in the same commit.

Also include and maintain scorecard criteria comments in both code and docs:

- `overall = 0.40 * node + 0.30 * relation + 0.30 * property`
- Expected totals must be computed from **currently supported extraction scope** (fair denominator policy), not from all possible CityGML tags.
- Detailed scoring policy source of truth: `docs/evaluation_scorecard.md`.

## Target Package Structure

```text
src/citygml_sg/
|-- app/
|-- config/
|-- domain/
|-- ovg/
|   |-- image_to_graph/
|   |-- adapters/
|   `-- validation/
|-- world_graph/
|   |-- citygml_to_graph/
|   |-- anchor/
|   `-- signatures/
|-- retrieval/
|   |-- query_generator/
|   |-- graph_matching/
|   |-- scoring/
|   `-- reporting/
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

## Definition of Done (v1-oriented)

For v1 tasks, prioritize completion in this order:

1. Parse target object families reliably from CityGML
2. Build consistent internal graph nodes/edges
3. Add hierarchy and core spatial relations
4. Persist graph to Neo4j
5. Provide runnable scripts and reproducible outputs
