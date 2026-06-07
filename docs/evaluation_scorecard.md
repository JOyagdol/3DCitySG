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

Note:

- Spatial-specific metrics are reported as additional diagnostics.
- They are currently **not** included in the weighted `overall` score.

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
  - `HAS_SURFACE_TYPE`
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
- Runtime-augmented v2 spatial extension relations (`HOSTED_BY`, `ADJACENT_SURFACE`, `ATTACHED_TO`, `ABOVE`, `BELOW`)
  are reported in graph outputs but are not used as direct source-structure denominators in relation coverage.

3. Property expected totals
- Expected properties are counted only when direct child tags actually exist on supported semantic elements.
- Generic attributes are counted from `gen:*Attribute` entries that are currently parsed into `attr_*` fields.

## Spatial Diagnostic Metrics (v2)

Scorecard reports density-oriented and quality-oriented spatial diagnostics separately:

1. `spatial_coverage` (v2 definition)
- Meaning: raw candidate hit-rate over active pair families.
- Based on **undirected** candidate pairs (not directed edge count).
- `expected_total` is built from candidate pair enumeration (graph-structural scope + availability checks),
  not from epsilon threshold checks.
- Thresholds (`touch_epsilon`, `adjacent_epsilon`, `intersection_epsilon`) affect inferred edges (`actual_total`),
  not candidate pool size (`expected_total`), except the explicit CONNECTS fallback floor policy.
- Scope families:
  - `furniture_boundary_surface`
  - `furniture_opening` (door/window opening subtype only)
  - `furniture_furniture`
  - `opening_room_connects` (`CONNECTS`, Door->Room only)
- `opening_room_connects` candidate pairs are derived from structural chain:
  - `Room -[:BOUNDED_BY]-> BoundarySurface -[:HAS_OPENING]-> Opening`
  - fallback strategy: `max(source_expected_connects, structural_chain_candidates, inferred_connect_pairs_floor)`
  - this prevents `expected_total=0` when `CONNECTS` relations are inferred
- Family weights:
  - `furniture_boundary_surface`: `0.30`
  - `furniture_opening`: `0.25`
  - `furniture_furniture`: `0.25`
  - `opening_room_connects`: `0.20`
- Main fields:
  - `actual_total`: inferred undirected pair count
  - `expected_total`: candidate undirected pair count
  - `actual_directed_total`: inferred directed relation count (compatibility/debug)
  - `expected_directed_total`: candidate directed pair count (compatibility/debug)
  - families with `expected_total=0` are reported as `N/A` (`null`) at family score level
  - top-level totals are aggregated over active families (`expected_total > 0`)

2. `spatial_plausible_coverage` (supplementary denominator)
- Meaning: epsilon-aware plausible candidate hit-rate, reported as a supplementary view.
- Denominator:
  - `plausible_expected_total` = candidates that pass epsilon-aware plausibility check
  - computed with current runtime thresholds (`touch_epsilon`, `adjacent_epsilon`, `intersection_epsilon`)
- Purpose:
  - keeps operational/history comparability by preserving `spatial_coverage` denominator
  - adds a threshold-aware denominator for interpretation
- Main fields:
  - `actual_total`
  - `plausible_expected_total`
  - `expected_total` (raw denominator retained for side-by-side reading)

3. `spatial_density`
- Meaning: family-weighted normalized density summary, separated from quality sanity.
- Main fields:
  - `score`: weighted family-normalized score
  - `family_weighted_score`
  - `family_unweighted_score`
  - `active_family_count`
- Only active families (`expected_total > 0`) participate in weighted normalization.

4. `spatial_precision_sanity`
- Meaning: quality-only no-GT sanity score for inferred spatial edges.
- It is the average of:
  - metadata validity ratio
  - schema validity ratio
  - precedence consistency ratio
- Main fields:
  - `metadata_score`
  - `schema_score`
  - `precedence_score`
  - `pair_conflict_count`

5. `spatial_quality`
- Alias-style quality block for explicit density/quality separation in downstream reporting.
- Uses the same quality components as `spatial_precision_sanity`.

6. `spatial_pair_stats`
- Pair-family breakdown with both pair-level and directed totals.
- Per family:
  - `candidate_pairs`
  - `plausible_candidate_pairs`
  - `candidate_pairs_directed`
  - `inferred_pair_total`
  - `inferred_total`
  - `coverage_score`
  - `relation_counts`

7. `spatial_pair_family_scores`
- Family-level normalized score entries.
- Per family:
  - `score`
  - `actual_total`
  - `expected_total`
  - `weight`
  - `weighted_score_contribution`
  - `score=null` when `expected_total=0` (N/A policy)

8. `spatial_family_normalized_coverage`
- Aggregated family-normalized summary with explicit weight map.

9. `spatial_coverage_policy`
- Runtime policy metadata:
  - `include_connects_family=true`
  - `zero_candidate_score_policy="N/A(null)"`
  - `plausible_expected_policy="epsilon-aware plausible candidates reported as supplementary denominator"`

## Interpretation

- High node score with low relation score usually means hierarchy links are partially missing or schema constraints block links.
- High node/relation with low property score usually means extracted objects exist but metadata fields are not yet fully mapped.
- Compare score trends between commits, not only one absolute number.
- Spatial diagnostics should be read together:
  - low `spatial_coverage` means low overall raw hit-rate (`actual_total/expected_total`)
  - low `spatial_plausible_coverage` means low hit-rate even after threshold-aware plausible denominator adjustment
  - low `spatial_density` means weak performance in weighted family-normalized density
  - low `spatial_quality`/`spatial_precision_sanity` indicates metadata/schema/precedence consistency issues

Decision rubric (practical):
1. Spatial relation quality is considered strong when:
   - `spatial_coverage` is stable/acceptable for dataset scale,
   - `spatial_density` is stable with no critical family collapse,
   - `spatial_quality` (or `spatial_precision_sanity`) remains high,
   - and key family scores (for the target use case) are not near zero.
2. High quality score alone does not imply sufficient relation richness.
3. High coverage alone does not imply schema/metadata correctness.

## Update Rule

When relation/property extraction logic changes, update both:

1. `src/citygml_sg/app/pipeline.py` scorecard comments/constants
2. This document
