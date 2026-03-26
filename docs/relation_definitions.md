# Relation Definitions

Reference:

1. Spatial relation implementation policy: `docs/spatial_relation_spec_v1.md`

## Semantic and Geometry Relations

1. `CONTAINS`: generic containment in semantic hierarchy
2. `CONSISTS_OF_BUILDING_PART`: `Building|BuildingPart -> BuildingPart`
3. `INTERIOR_ROOM`: `Building|BuildingPart -> Room`
4. `OUTER_BUILDING_INSTALLATION`: `Building|BuildingPart -> BuildingInstallation`
5. `INTERIOR_BUILDING_INSTALLATION`: `Building|BuildingPart -> IntBuildingInstallation`
6. `ROOM_INSTALLATION`: `Room -> IntBuildingInstallation`
7. `INTERIOR_FURNITURE`: `Room -> BuildingFurniture`
8. `HAS_CITY_OBJECT`: `cityObjectMember -> CityObject`
9. `HAS_GROUP_MEMBER`: `CityObjectGroup -> groupMember CityObject`
10. `BOUNDED_BY`: object to `BoundarySurface`
11. `HAS_OPENING`: `BoundarySurface -> Opening`
12. `HAS_ADDRESS`: `Building|BuildingPart -> Address`
13. `HAS_APPEARANCE`: semantic object to `Appearance`
14. `HAS_SURFACE_DATA`: `Appearance -> SurfaceData`
15. `APPLIES_TO`: `SurfaceData -> geometry/surface node`
16. `HAS_LOD_GEOMETRY`: object to `Geometry|ImplicitGeometry`
17. `HAS_GEOMETRY_COMPONENT`: `Geometry -> Solid|MultiSurface|MultiCurve`
18. `HAS_GEOMETRY_MEMBER`: `Solid|MultiSurface -> Polygon`
19. `HAS_GEOMETRY`: object to `Polygon`
20. `HAS_RING`: `Polygon -> LinearRing`
21. `HAS_POS`: `LinearRing -> Position`

## Spatial Relations

1. `INSIDE`: `BuildingFurniture -> Room` (existing semantic-spatial rule)
2. `CONNECTS`: `Opening -> Room` (existing semantic-spatial rule)
3. `INTERSECTS`: AABB overlap on all axes above intersection epsilon
4. `TOUCHES`: non-intersecting and minimum distance within touch epsilon
5. `ADJACENT_TO`: non-intersecting and within adjacency threshold
6. spatial thresholds are loaded from `configs/default.yaml` (`spatial.*`)

v1 inferred pair scope:

1. `BuildingFurniture -> BoundarySurface`
2. `BuildingFurniture -> Door|Window` (stored as `Opening` node with `opening_type`)
3. `BuildingFurniture -> BuildingFurniture`
4. inferred spatial pairs are materialized bidirectionally for graph query convenience

## Spatial Roadmap (v1 vs v2)

v1 (implemented):

1. `INSIDE` (`BuildingFurniture -> Room`)
2. `CONNECTS` (`Opening -> Room`)
3. `ADJACENT_TO`, `TOUCHES`, `INTERSECTS`
4. Pair scope:
5. `BuildingFurniture -> BoundarySurface`
6. `BuildingFurniture -> Door|Window`
7. `BuildingFurniture -> BuildingFurniture`

v2 (planned):

1. directional relations (for example `LEFT_OF`, `RIGHT_OF`, `ABOVE`, `BELOW`, `IN_FRONT_OF`, `BEHIND`)
2. distance-binned relations (for example `NEAR`, `FAR`, configurable thresholds)
3. path/accessibility relations (for example walkable/reachable constraints)
4. optional relation confidence calibration per object family

Precedence (implemented):

1. `INTERSECTS > TOUCHES > ADJACENT_TO`
2. weaker relations are removed for the same `(source_id, target_id)`
