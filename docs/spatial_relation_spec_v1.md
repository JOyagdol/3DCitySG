# Spatial Relation Spec v1 (CityGML 2.0, Building-Centric)

This spec fixes relation scope and precedence before implementation changes.
It targets two goals:

1. Comparable topology signals against SLAM-style exploration outputs
2. Human-readable graph querying for indoor spatial understanding

## v1 Relation Set

1. `INSIDE` (existing)
2. `CONNECTS` (existing)
3. `TOUCHES` (implemented in spatial inference)
4. `INTERSECTS` (implemented in spatial inference)
5. `ADJACENT_TO` (implemented in spatial inference)

## v1 Pair Scope

Spatial inference in v1 is computed for:

1. `BuildingFurniture -> BoundarySurface`
2. `BuildingFurniture -> Door|Window` (stored as `Opening` node with `opening_type`)
3. `BuildingFurniture -> BuildingFurniture`
4. inferred spatial edges are materialized as bidirectional pairs

## Precedence (exclusive)

For the same `(source_id, target_id)`:

1. `INTERSECTS`
2. `TOUCHES`
3. `ADJACENT_TO`

If a higher relation is true, weaker relations are removed.

## AABB Decision Rules

Parameters:

1. `eps_touch`
2. `eps_adjacent`
3. `eps_intersection`

Current default values (`configs/default.yaml` baseline):

1. `eps_touch = 0.05`
2. `eps_adjacent = 0.50`
3. `eps_intersection = 1e-6`

Rules:

1. `INTERSECTS`: overlap on all axes greater than `eps_intersection`
2. `TOUCHES`: not intersecting, and minimum bbox distance `<= eps_touch`
3. `ADJACENT_TO`: not intersecting, and `eps_touch < distance <= eps_adjacent`

## Computation Pipeline (How It Is Calculated)

Spatial inference is geometry-derived and bbox-based:

1. collect object geometry points from graph edges:
2. `Object -HAS_GEOMETRY-> Polygon -HAS_RING-> LinearRing -HAS_POS-> Position(x,y,z)`
3. build per-node AABB (`min(x,y,z)`, `max(x,y,z)`) from those positions
4. evaluate pair relation by AABB:
5. if axis overlap on x/y/z all exceed `eps_intersection` => `INTERSECTS`
6. else compute minimum AABB gap distance
7. if distance `<= eps_touch` => `TOUCHES`
8. else if `eps_touch < distance <= eps_adjacent` => `ADJACENT_TO`
9. after generation, apply precedence normalization:
10. for same `(source_id, target_id)`, keep only strongest relation (`INTERSECTS > TOUCHES > ADJACENT_TO`)

Notes:

1. this is an AABB approximation, not exact mesh/solid intersection
2. relation quality depends on parsed geometry completeness and numeric tolerance

## Edge Metadata (required)

Spatial edges store:

1. `method`
2. `distance`
3. `epsilon_touch`
4. `epsilon_adjacent`
5. `epsilon_intersection`
6. `confidence`
7. `computed_at`

## Query Validation Set

Minimum query checks:

1. furniture touching wall/floor/ceiling
2. furniture intersecting wall/opening
3. furniture adjacent to opening without touching
4. furniture-to-furniture proximity/conflict

## DoD

1. relation generation connected to import pipeline
2. precedence normalization enabled
3. metadata written on spatial edges
4. regression tests updated and passing
5. docs synced (`README`, relation/schema docs, this spec)
