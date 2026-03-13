# Planned Module Stubs (v1)

This file tracks modules that exist as placeholders but are not wired into the active v1 import pipeline.

## Why This Exists

The repository contains exploratory modules for research extension.
Without explicit status labeling, these can be mistaken for active runtime code.

## Status Policy

`Planned module stub` means:

1. module file is intentionally present for architecture direction
2. not currently imported by the main v1 pipeline path
3. behavior is not part of current scorecard guarantees

## Current Stub List

- `src/citygml_sg/evaluation/ablation.py`
- `src/citygml_sg/evaluation/query_cases.py`
- `src/citygml_sg/evaluation/relation_metrics.py`
- `src/citygml_sg/evaluation/statistics.py`
- `src/citygml_sg/extractors/geometry_extractor.py`
- `src/citygml_sg/extractors/hierarchy_extractor.py`
- `src/citygml_sg/extractors/lod_extractor.py`
- `src/citygml_sg/extractors/semantic_extractor.py`
- `src/citygml_sg/modules/boundary_surface/mapper.py`
- `src/citygml_sg/modules/building/mapper.py`
- `src/citygml_sg/modules/building/validator.py`
- `src/citygml_sg/modules/building_part/mapper.py`
- `src/citygml_sg/modules/generic/mapper.py`
- `src/citygml_sg/modules/generic/parser.py`
- `src/citygml_sg/modules/opening/mapper.py`
- `src/citygml_sg/modules/room/mapper.py`
- `src/citygml_sg/relations/candidate_search.py`
- `src/citygml_sg/relations/directional.py`
- `src/citygml_sg/relations/intersection.py`
- `src/citygml_sg/relations/semantic_filters.py`
- `src/citygml_sg/utils/crs.py`

## Promotion Rule (Stub -> Active)

Before promoting a stub module into active runtime path:

1. implement functional logic
2. add unit/regression tests
3. wire into pipeline explicitly
4. update `README.md` and relevant docs with new support scope
