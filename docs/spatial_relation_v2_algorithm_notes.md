# Spatial Relation v2 Algorithm Notes

Baseline: CityGML 2.0 building-centric pipeline  
Purpose: paper-oriented explanation of how v2 spatial relations are computed, why the rules exist, and how to interpret edge outputs.

This document is the detailed companion to `docs/spatial_relation_spec_v1.md`.

## 1. Design Intent

v1 generated AABB-based `ADJACENT_TO`, `TOUCHES`, and `INTERSECTS` relations. This was fast and reproducible, but insufficient for image-to-world graph matching because a room localization query needs structural cues: which wall hosts a window, which surface a furniture object is attached to, and how wall/floor/ceiling surfaces form a room topology.

v2 therefore adds invariant structural relations and conservative refinement rules:

1. `HOSTED_BY`: `Opening(Door|Window) -> BoundarySurface`
2. `ADJACENT_SURFACE`: `BoundarySurface <-> BoundarySurface`
3. `ATTACHED_TO`: `BuildingFurniture -> BoundarySurface`
4. `ABOVE` / `BELOW`: vertical ordering over `BuildingFurniture`, `Door`, and `Window`
5. two-stage spatial inference for AABB false-positive reduction
6. layered-boundary collapse and representative-surface selection
7. relation metadata (`method`, `confidence`, `evidence_score`, and relation-specific evidence fields)

## 2. Geometry Source

Spatial inference collects geometry from graph nodes:

```text
Object -HAS_GEOMETRY-> Polygon -HAS_RING-> LinearRing -HAS_POS-> Position(x,y,z)
```

The pipeline builds per-node AABB from all collected positions and keeps point/ring lists for OBB/polygon refinement and shared-edge validation.

## 3. Room-Level Scope

Spatial relations are computed within a room scope to avoid global cross-room noise.

1. Furniture scope: `BuildingFurniture -INSIDE-> Room`
2. Boundary scope: `Room -BOUNDED_BY-> BoundarySurface`
3. Opening scope: `BoundarySurface -HAS_OPENING-> Opening`
4. If a room has no direct boundary, the pipeline falls back to parent `BuildingPart|Building` boundaries.
5. Fallback boundaries are collapsed to representative surfaces before spatial inference.

## 4. Layered-Surface Collapse

IFC-derived CityGML often contains multiple layers for the same physical wall/floor: structure, finish, insulation, substrate, and so on. If every layer is used directly, boundary-surface adjacency and furniture-surface relations become noisy.

Layered candidates are grouped when:

1. `surface_type` is the same
2. inferred plane axis is the same
3. normal-axis center gap is small (`<= 0.25`)
4. tangent-axis overlap ratio is high (`>= 0.85`)

Representative selection:

1. general boundaries: maximum projected area
2. floor-like boundaries: highest usable top surface (`bbox.max_z`) first
3. finish/flooring keywords are preferred
4. insulation/substrate keywords are de-prioritized

This is why a non-representative source wall ID may have no direct `ADJACENT_SURFACE`; the relation can be concentrated on the representative surface.

## 5. AABB Relations and Two-Stage Refinement

Stage 1:

1. `INTERSECTS`: overlap on x/y/z greater than `eps_intersection`
2. `TOUCHES`: not intersecting and bbox distance `<= eps_touch`
3. `ADJACENT_TO`: `eps_touch < distance <= eps_adjacent`

Stage 2 is applied to Stage-1 `INTERSECTS` candidates:

1. build XY point sets
2. compute PCA-based OBB axes
3. compute convex hull polygon axes
4. run SAT overlap checks for OBB and polygon hulls
5. require positive z-overlap

If Stage 2 fails, an AABB intersection is demoted and may become `ADJACENT_TO` or no relation. This reduces cases where rotated or concave objects have overlapping axis-aligned boxes but do not physically overlap.

## 6. Conservative `TOUCHES`

`TOUCHES` requires meaningful contact:

1. face contact: contact area `>= 0.01`
2. edge contact: contact length `>= 0.10`
3. point contact or very small contact is suppressed

This avoids treating numerical artifacts as strong contact evidence.

## 7. Conservative `ADJACENT_TO`

For non-boundary object pairs in the same room scope, `ADJACENT_TO` is suppressed if the centroid-to-centroid segment intersects another room-boundary bbox. This is a conservative occlusion guard. It is not exact polygon visibility, but it reduces obvious wall-through adjacency false positives.

## 8. `ADJACENT_SURFACE`

`ADJACENT_SURFACE` is not a pure distance relation. It is intended to represent boundary topology: wall-wall, wall-floor, wall-ceiling, and related surface junctions.

Computation:

1. generate boundary pairs inside room boundary scope
2. use collapsed representative surfaces when fallback boundaries are used
3. for wall-wall pairs, currently require both surfaces to be exterior-like and skip parallel layered wall pairs
4. run AABB inference and keep only `TOUCHES`/`INTERSECTS` basis candidates
5. compare polygon ring segments
6. create `ADJACENT_SURFACE` only if max shared 3D edge length is at least `0.10`
7. write bidirectional edges and metadata:
   - `basis_relation`
   - `shared_edge_length`
   - `min_shared_edge_length`
   - `shared_edge_line_tolerance`
   - `adjacent_surface_method=polygon_shared_edge_v1`

Wall-wall example:

```text
Wall A
  |
  +---- Wall B
```

The pair becomes `ADJACENT_SURFACE` only when both walls are in the same room scope, survive representative-surface selection, pass wall-wall guards, are AABB `TOUCHES`/`INTERSECTS` candidates, and share a sufficiently long polygon edge. A visual corner is not enough if the raw IDs are non-representative layers or their polygon segments do not share an edge.

## 9. `ATTACHED_TO`

`ATTACHED_TO` is materialized as `BuildingFurniture -> BoundarySurface`.

Sources:

1. primary: existing furniture-boundary `TOUCHES`
2. floor fallback:
   - boundary type in `FloorSurface|OuterFloorSurface|GroundSurface`
   - XY bbox overlap
   - vertical gap `|furniture.min_z - floor.max_z| <= max(eps_touch, 0.10)`

This supports practical queries such as “which room has furniture placed on the floor” even when mesh coordinates leave a small vertical gap.

## 10. `ABOVE` / `BELOW`

Vertical relations are generated for `BuildingFurniture`, `Door`, and `Window`.

Rules:

1. XY overlap is required
2. if `first.min_z >= second.max_z + eps_touch`, create `first ABOVE second` and inverse `second BELOW first`
3. if the opposite is true, create the inverse pair

These relations are view-invariant, unlike left/right/front/back relations.

## 11. Metadata

Spatial edges include provenance and evidence:

1. `method`
2. `distance`
3. `epsilon_touch`
4. `epsilon_adjacent`
5. `epsilon_intersection`
6. `confidence`
7. `evidence_score`
8. `computed_at`
9. optional Stage-2 fields (`stage2_obb_overlap`, `stage2_polygon_overlap`, `stage2_z_overlap`)
10. optional contact/shared-edge fields

This makes spatial relation extraction inspectable and usable for later graph matching/ranking.

## 12. Paper-Ready Summary

The v2 spatial enrichment extends AABB proximity extraction with invariant structural relations and conservative geometric validation. Boundary topology is represented through representative-surface `ADJACENT_SURFACE` edges validated by polygon shared-edge length, while furniture-surface attachment and opening-host relations provide room-level cues for view-graph localization. The design prioritizes queryable structural evidence over exhaustive raw mesh contact preservation.

