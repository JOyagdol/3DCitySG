# Spatial Relation Spec v1 (CityGML 2.0, Building-Centric)

This spec fixes relation scope and precedence before implementation changes.
It targets two goals:

1. Comparable topology signals against SLAM-style exploration outputs
2. Human-readable graph querying for indoor spatial understanding

Detailed paper-oriented algorithm notes:

1. English: `docs/spatial_relation_v2_algorithm_notes.md`
2. Korean: `docs/spatial_relation_v2_algorithm_notes_ko.md`

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

## v2 Implemented Extension Set

Implemented in the current pipeline as v2 extension:

1. `OPENING --HOSTED_BY--> BOUNDARY_SURFACE`
2. `BOUNDARY_SURFACE --ADJACENT_SURFACE--> BOUNDARY_SURFACE`
3. `BuildingFurniture --ATTACHED_TO--> BOUNDARY_SURFACE` (derived from `TOUCHES`, plus floor-contact vertical-gap fallback)
4. `OBJECT --ABOVE/BELOW--> OBJECT`
   - object scope: `BuildingFurniture`, `Door`, `Window`
5. keep `CONNECTS` as `Door -> Room` source relation
6. exclude `ROOM --SHARES_DOOR_WITH--> ROOM` from core graph

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

## Implemented Algorithms (v2, relation-by-relation)

### 1) Shared candidate scope build

1. Build room-scoped maps: `room_to_furniture`, `room_to_boundary`, `room_to_opening`.
2. Base boundary scope: `Room -BOUNDED_BY-> BoundarySurface`.
3. Fallback (when room has no direct boundary): use parent `BuildingPart|Building -BOUNDED_BY-> BoundarySurface`.
4. Before using fallback boundaries, apply layered-surface collapse:
   - same `surface_type`
   - same inferred plane axis (smallest bbox span axis)
   - normal-axis center gap `<= 0.25`
   - overlap ratio on tangent axes `>= 0.85`
   - for general boundaries, choose the representative by maximum projected area
   - for floor-like surfaces, choose the highest usable top/finish surface first (`bbox.max_z`), then prefer finish/flooring keywords and de-prioritize insulation/substrate keywords

### 2) `ADJACENT_TO` / `TOUCHES` / `INTERSECTS`

1. Geometry source: `HAS_GEOMETRY -> HAS_RING -> HAS_POS` positions.
2. Build per-node AABB.
3. Stage-1 (candidate filtering): apply AABB `infer_spatial_relation(first_bbox, second_bbox)`:
   - `INTERSECTS` if all-axis overlap `> eps_intersection`
   - else `TOUCHES` if min bbox gap `<= eps_touch`
   - else `ADJACENT_TO` if `eps_touch < gap <= eps_adjacent`
4. Stage-2 (precise check, for Stage-1 `INTERSECTS` candidates only):
   - OBB overlap check in XY (PCA-based oriented axes + SAT)
   - Polygon overlap check in XY (convex hull + SAT)
   - Z-overlap check (`overlap_z > eps_intersection`)
   - if Stage-2 fails, demote candidate to distance-based `TOUCHES`/`ADJACENT_TO` (or no relation)
5. Precedence normalization keeps only strongest relation per directed pair.
6. Conservative `ADJACENT_TO` policy: inside the same room scope, suppress adjacency if
   the source-target centroid segment is occluded by another `BoundarySurface` bbox.
7. Conservative `TOUCHES` policy: suppress point/edge-noise by minimum contact constraints:
   - face-contact (2-axis overlap): contact area `>= 0.01`
   - edge-contact (1-axis overlap): contact length `>= 0.10`
   - candidates demoted from Stage-1 `INTERSECTS` by Stage-2 refinement are further demoted to `ADJACENT_TO`

Follow-up refinement target:

1. Current `ADJACENT_TO` occlusion uses room boundary bboxes.
2. Next, use actual room boundary polygons as occluders and test whether the centroid segment/ray between objects intersects a boundary polygon.
3. This reduces false positives caused by broad bboxes and keeps adjacency closer to actual visibility/accessibility cues.

### 3) `CONNECTS` (Door -> Room)

1. Scope: door openings only (`opening_type == Door`).
2. Primary path: semantic ancestry-derived room association.
3. Candidate augmentation: room-boundary-opening structural chain via fallback boundary scope.
4. If needed, apply hierarchy+bbox fallback augmentation (`method=hierarchy_bbox_fallback_v1`).

### 4) `HOSTED_BY` (Opening -> BoundarySurface)

1. Created directly when `HAS_OPENING` semantic edge is created.
2. For each `BoundarySurface -HAS_OPENING-> Opening`, add `Opening -HOSTED_BY-> BoundarySurface`.

### 5) `ADJACENT_SURFACE` (BoundarySurface <-> BoundarySurface)

1. Boundary pairs are generated inside room boundary scope (including fallback+collapse result).
2. For each pair, run the same AABB spatial inference.
3. Only pairs whose basis relation is `TOUCHES` or `INTERSECTS` remain as `ADJACENT_SURFACE` candidates.
4. Store `basis_relation` in edge metadata.
5. Conservative wall-wall policy:
   - allow only exterior wall pairs (`is_external`-like flag true on both surfaces)
   - suppress parallel layered-wall pairs (same inferred plane axis)

Polygon shared-edge validation:

1. AABB/axis basis relations (`TOUCHES`/`INTERSECTS`) are only the candidate filter.
2. Candidate boundary pairs are then checked against actual polygon ring segments.
3. Create `ADJACENT_SURFACE` only when the maximum shared 3D edge length is at least `L_min=0.10`.
4. Shared-edge line tolerance is `0.01`.
5. Edge metadata records `shared_edge_length`, `min_shared_edge_length`,
   `shared_edge_line_tolerance`, and `adjacent_surface_method=polygon_shared_edge_v1`.
6. This reduces duplicate false positives from inner/finish/insulation layers whose bboxes overlap but do not provide a meaningful boundary junction.
7. Representative-surface collapse remains, but representative pairs must still pass polygon shared-edge validation.

### 6) `ATTACHED_TO` (BuildingFurniture -> BoundarySurface)

1. Primary: derive from existing furniture-boundary `TOUCHES`.
2. Floor-like fallback (`FloorSurface|OuterFloorSurface|GroundSurface`):
   - XY overlap is required
   - vertical gap `|furniture_min_z - floor_max_z| <= max(eps_touch, 0.10)`
3. If conditions are satisfied, materialize `ATTACHED_TO` with attachment metadata.

### 7) `ABOVE` / `BELOW` (object vertical relation)

1. Object scope: `BuildingFurniture`, `Door`, `Window`.
2. Require XY overlap first.
3. If `first.min_z >= second.max_z + eps_touch` => `ABOVE`.
4. If `second.min_z >= first.max_z + eps_touch` => `BELOW`.
5. Otherwise no vertical relation.

Room-boundary fallback policy:

1. if `Room -> BOUNDED_BY -> BoundarySurface` exists, use it directly
2. if a room has no direct `BOUNDED_BY`, fallback to its container (`BuildingPart|Building`) boundaries
3. fallback boundaries are layer-collapsed before spatial inference:
4. same `surface_type` + near-parallel plane + small normal-gap + strong tangent overlap => one representative boundary
5. floor-like representatives use top/finish preference so furniture relations target the usable floor layer rather than insulation/slab layers
6. this collapsed fallback scope is used for `CONNECTS`, `ADJACENT_SURFACE`, and furniture-boundary spatial inference

ATTACHED_TO policy:

1. primary: derive from existing `TOUCHES` between `BuildingFurniture` and `BoundarySurface`
2. fallback: for floor-like surfaces (`FloorSurface`, `OuterFloorSurface`, `GroundSurface`), also allow attachment when:
3. XY bbox overlaps and vertical gap `|furniture_min_z - boundary_max_z| <= max(eps_touch, 0.10)`

Current operational behavior (latest E-TYPE validation):

1. In fallback rooms, layered boundaries are collapsed to representative surfaces before
   `ADJACENT_SURFACE` and furniture-boundary inference.
2. Non-representative layered walls can therefore have no direct `ADJACENT_SURFACE` edges
   even when visually adjacent; relations are concentrated on representative surfaces.
3. Floor-like representatives are selected by highest top surface first, then finish/flooring evidence,
   while insulation/substrate evidence is de-prioritized.
4. `ATTACHED_TO` is currently derived mainly from `TOUCHES` outcomes; floor-like attachments
   can still appear as `ADJACENT_TO` when touch/gap conditions are not satisfied.

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
7. `evidence_score` (0.0~1.0, relation evidence strength)
8. `computed_at`
9. optional Stage-2 fields (when two-stage refinement is enabled):
   - `stage2_refinement` (`obb_polygon_v2` or `skipped_insufficient_points`)
   - `stage2_obb_overlap`
   - `stage2_polygon_overlap`
   - `stage2_z_overlap`

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
