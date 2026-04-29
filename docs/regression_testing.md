# Regression Testing Guide

This document explains why regression testing is required in this project and how to run/extend it.

## Why We Do Regression Tests

CityGML Scene Graph logic is rule-heavy and can break silently when relation/property logic changes.
Regression tests protect core guarantees:

1. semantic relation rules stay stable across refactors
2. scorecard output shape stays stable for experiments
3. appearance fallback behavior stays stable for root-level `appearanceMember` data

Without regression tests, it is easy to get "looks fine" output that actually changed relation semantics.

## Scope of Current Regression Tests

Current baseline tests cover:

1. `HAS_APPEARANCE` fallback link creation for global `Appearance`
2. no duplicate `CONTAINS` when a specialized relation exists
3. summary contract checks (`scorecard`, `appearance_coverage`, spatial diagnostic fields)
4. spatial precedence normalization (`INTERSECTS > TOUCHES > ADJACENT_TO`)
5. spatial pair generation for `Furniture-Door/Window`, `Furniture-BoundarySurface`, and `Furniture-Furniture` (`ADJACENT_TO`, `TOUCHES`)
6. bidirectional materialization checks for inferred spatial relations
7. negative checks for non-contact/non-adjacent/non-intersecting pairs
8. boundary surface subtype preservation checks (`BoundarySurfaceType` node + `HAS_SURFACE_TYPE` relation)

Test file:

- `tests/test_pipeline_regression.py`
- `tests/test_spatial_priority.py`
- `tests/test_spatial_relation_pairs.py`

## How To Run

1. install dev dependencies

```bash
pip install -e .[dev]
```

2. run all regression tests

```bash
pytest tests/test_pipeline_regression.py
```

3. run all tests

```bash
pytest
```

## How To Add a New Regression Test

1. encode the smallest reproducible XML fixture
2. run pipeline to temporary output JSON
3. assert one invariant per test (relations/properties/summary)
4. avoid brittle checks on huge absolute counts unless the value is intentionally fixed

Recommended style:

1. use one focused fixture per behavior
2. assert both existence and non-existence for overlap-prone relations
3. keep assertions close to user-facing guarantees (JSON summary + graph edges)

## Relation Regression Policy

For hierarchy overlap prevention:

1. if specialized relation exists (`CONSISTS_OF_BUILDING_PART`, `INTERIOR_ROOM`, etc.), do not emit duplicate `CONTAINS`
2. test both positive and negative side in the same scenario

## Appearance Regression Policy

For `Appearance` handling:

1. if semantic ancestor exists, use ancestor owner
2. if not, fallback owner resolution must still create `HAS_APPEARANCE` when an eligible semantic owner exists
3. unresolved appearances must be visible in `summary.appearance_coverage`

## DoD for Regression Updates

Any change to relation extraction, scorecard, or appearance ownership is complete only when:

1. regression tests are updated/added
2. this document is updated when policy changed
