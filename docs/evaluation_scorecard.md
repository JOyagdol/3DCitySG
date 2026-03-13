# Evaluation Scorecard (CityGML 2.0 Baseline)

This document defines the current import scorecard policy used in `src/citygml_sg/app/pipeline.py`.

## Scope

- Baseline target: **CityGML 2.0**
- Applies to v1-supported object families:
  - Building
  - BuildingPart
  - Room
  - BoundarySurface
  - Opening (Door/Window)
  - BuildingFurniture
- Applies to geometry subgraph channels:
  - Polygon
  - LinearRing
  - Position

## Formula

`overall = 0.40 * node + 0.30 * relation + 0.30 * property`

- Node coverage (40%)
- Relation coverage (30%)
- Property coverage (30%)

## Fair Denominator Policy

Expected totals must be computed from **supported extraction channels only**.

1. Node expected totals
- Semantic expected count: elements matching currently supported object parser tags.
- Geometry expected count: Polygon/LinearRing/Position items attached to supported semantic ancestors.

2. Relation expected totals
- Expected relations are reconstructed from source structure only for supported relation families:
  - `HAS_CITY_OBJECT`
  - `HAS_GROUP_MEMBER`
  - `HAS_APPEARANCE`
  - `HAS_SURFACE_DATA`
  - `APPLIES_TO`
  - `CONTAINS`
  - `CONSISTS_OF_BUILDING_PART`
  - `INTERIOR_ROOM`
  - `OUTER_BUILDING_INSTALLATION`
  - `INTERIOR_BUILDING_INSTALLATION`
  - `ROOM_INSTALLATION`
  - `INSIDE`
  - `BOUNDED_BY`
  - `HAS_OPENING`
  - `HAS_ADDRESS`
  - `HAS_LOD_GEOMETRY`
  - `HAS_GEOMETRY_COMPONENT`
  - `HAS_GEOMETRY_MEMBER`
  - `CONNECTS`
  - `HAS_GEOMETRY`
  - `HAS_RING`
  - `HAS_POS`
- This avoids unfair penalties from unsupported CityGML relation channels.

3. Property expected totals
- Expected properties are counted only when direct child tags actually exist on supported semantic elements.
- Generic attributes are counted from `gen:*Attribute` entries that are currently parsed into `attr_*` fields.

## Interpretation

- High node score with low relation score usually means hierarchy links are partially missing or schema constraints block links.
- High node/relation with low property score usually means extracted objects exist but metadata fields are not yet fully mapped.
- Compare score trends between commits, not only one absolute number.

## Update Rule

When relation/property extraction logic changes, update both:

1. `src/citygml_sg/app/pipeline.py` scorecard comments/constants
2. This document
