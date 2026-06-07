# Relation Definitions

Reference:

1. Spatial relation implementation policy: `docs/spatial_relation_spec_v1.md`
2. Algorithm details (v2): `Implemented Algorithms (v2, relation-by-relation)` section in `docs/spatial_relation_spec_v1.md`
3. Paper-oriented algorithm explanation: `docs/spatial_relation_v2_algorithm_notes.md`
4. Korean paper-oriented notes: `docs/spatial_relation_v2_algorithm_notes_ko.md`

## Semantic and Geometry Relations

1. `CONTAINS`: generic containment in semantic hierarchy
2. `CONSISTS_OF_BUILDING_PART`: `Building|BuildingPart -> BuildingPart`
3. `INTERIOR_ROOM`: `Building|BuildingPart -> Room`
4. `OUTER_BUILDING_INSTALLATION`: `Building|BuildingPart -> BuildingInstallation`
5. `INTERIOR_BUILDING_INSTALLATION`: `Building|BuildingPart -> IntBuildingInstallation`
6. `ROOM_INSTALLATION`: `Room -> IntBuildingInstallation`
7. `INTERIOR_FURNITURE`: `Room -> BuildingFurniture`
8. `HAS_CITY_OBJECT`: `CityObjectMember -> parsed top-level object` (for example `Building`, `CityObjectGroup`)
9. `HAS_GROUP_MEMBER`: `CityObjectGroup -> grouped semantic object`
10. `BOUNDED_BY`: object to `BoundarySurface`
11. `HAS_SURFACE_TYPE`: `BoundarySurface -> BoundarySurfaceType` (keeps original subtype such as `WallSurface`)
12. `HAS_OPENING`: `BoundarySurface -> Opening`
13. `HAS_ADDRESS`: `Building|BuildingPart -> Address`
14. `HAS_APPEARANCE`: semantic object to `Appearance`
15. `HAS_SURFACE_DATA`: `Appearance -> SurfaceData`
16. `APPLIES_TO`: `SurfaceData -> geometry/surface node`
17. `HAS_LOD_GEOMETRY`: object to `Geometry|ImplicitGeometry`
18. `HAS_GEOMETRY_COMPONENT`: `Geometry -> Solid|MultiSurface|MultiCurve`
19. `HAS_GEOMETRY_MEMBER`: `Solid|MultiSurface -> Polygon`
20. `HAS_GEOMETRY`: object to `Polygon`
21. `HAS_RING`: `Polygon -> LinearRing`
22. `HAS_POS`: `LinearRing -> Position`

## Spatial Relations

1. `INSIDE`: `BuildingFurniture -> Room` (existing semantic-spatial rule)
2. `CONNECTS`: `Opening(Door) -> Room` (door-only)
   - primary: room ancestry detected for opening
   - fallback: hierarchy + bbox-assisted augmentation when direct room ancestry is absent
3. `INTERSECTS`: AABB overlap on all axes above intersection epsilon
4. `TOUCHES`: non-intersecting and minimum distance within touch epsilon; v2 first-pass refinement also applies minimum contact area/length guards
5. `ADJACENT_TO`: non-intersecting and within adjacency threshold; v2 first-pass refinement suppresses pairs occluded by room boundary bboxes
6. `HOSTED_BY`: `Opening(Door|Window) -> BoundarySurface` (opening host surface)
7. `ADJACENT_SURFACE`: `BoundarySurface <-> BoundarySurface` (room-scope boundary contact via `Room -> BOUNDED_BY`; if missing, use container fallback with layered-surface collapse; `TOUCHES`/`INTERSECTS` candidate basis + polygon shared-edge length validation)
8. `ATTACHED_TO`: `BuildingFurniture -> BoundarySurface` (derived from `TOUCHES`, plus floor-contact vertical-gap fallback)
9. `ABOVE` / `BELOW`: vertical order over object scope (`BuildingFurniture`, `Door`, `Window`)
10. spatial thresholds are loaded from `configs/default.yaml` (`spatial.*`)
11. operational note: in layered fallback groups, non-representative walls may not carry direct `ADJACENT_SURFACE`; representative surfaces carry the relation set.
12. operational note: floor-like representatives prefer the highest usable top surface (`bbox.max_z`) and finish/flooring keywords; insulation/substrate keywords are de-prioritized.
13. operational note: floor-like furniture contacts can remain `ADJACENT_TO` when `TOUCHES`/gap criteria for `ATTACHED_TO` are not met.
14. operational note: spatial edges store `confidence` and `evidence_score` for later matching/ranking.

v1 inferred pair scope:

1. `BuildingFurniture -> BoundarySurface`
2. `BuildingFurniture -> Door|Window` (stored as `Opening` node with `opening_type`)
3. `BuildingFurniture -> BuildingFurniture`
4. inferred spatial pairs are materialized bidirectionally for graph query convenience

## Spatial Roadmap (v1 vs v2)

v1 (implemented):

1. `INSIDE` (`BuildingFurniture -> Room`)
2. `CONNECTS` (`Opening(Door) -> Room`)
3. `ADJACENT_TO`, `TOUCHES`, `INTERSECTS`
4. Pair scope:
5. `BuildingFurniture -> BoundarySurface`
6. `BuildingFurniture -> Door|Window`
7. `BuildingFurniture -> BuildingFurniture`

v2 (implemented in current pipeline):

1. `OBJECT --ABOVE/BELOW--> OBJECT`
   - current object scope: `BuildingFurniture`, `Door`, `Window`
2. `OPENING --HOSTED_BY--> BOUNDARY_SURFACE(subtype)`
3. `BOUNDARY_SURFACE --ADJACENT_SURFACE--> BOUNDARY_SURFACE`
4. `BuildingFurniture --ATTACHED_TO/TOUCHES--> BOUNDARY_SURFACE(subtype)`
5. keep core `CONNECTS` as `Door -> Room` (source relation)
6. exclude `ROOM --SHARES_DOOR_WITH--> ROOM` from v2 core graph
   - reason: corridor/hallway transition spaces can make direct room-room compression ambiguous
   - if needed later, materialize as optional derived layer only

v3+ (future expansion):

1. directional relations beyond vertical (for example `LEFT_OF`, `RIGHT_OF`, `IN_FRONT_OF`, `BEHIND`)
2. distance-binned relations (for example `NEAR`, `FAR`, configurable thresholds)
3. path/accessibility relations (for example walkable/reachable constraints)
4. optional relation confidence calibration per object family

Precedence (implemented):

1. `INTERSECTS > TOUCHES > ADJACENT_TO`
2. weaker relations are removed for the same `(source_id, target_id)`
