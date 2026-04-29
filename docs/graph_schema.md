# Graph Schema

Nodes are stored with base label `CityObject` plus type labels and `node_type` property.

## Core Relation Families

1. Hierarchy: `CONTAINS`, `CONSISTS_OF_BUILDING_PART`, `INTERIOR_ROOM`
2. Installation/Furniture: `OUTER_BUILDING_INSTALLATION`, `INTERIOR_BUILDING_INSTALLATION`, `ROOM_INSTALLATION`, `INTERIOR_FURNITURE`
3. Boundary/Opening: `BOUNDED_BY`, `HAS_SURFACE_TYPE`, `HAS_OPENING`, `CONNECTS`
4. Spatial: `INSIDE`, `ADJACENT_TO`, `TOUCHES`, `INTERSECTS`
5. Appearance: `HAS_APPEARANCE`, `HAS_SURFACE_DATA`, `APPLIES_TO`
6. Geometry: `HAS_LOD_GEOMETRY`, `HAS_GEOMETRY_COMPONENT`, `HAS_GEOMETRY_MEMBER`, `HAS_GEOMETRY`, `HAS_RING`, `HAS_POS`

## Spatial Pair Scope (v1)

Spatial inference is enabled for:

1. `BuildingFurniture -> BoundarySurface`
2. `BuildingFurniture -> Door|Window` (Opening subtype by `opening_type`)
3. `BuildingFurniture -> BuildingFurniture`
4. inferred spatial edges are stored in both directions

## Spatial Precedence

For the same `(source_id, target_id)`:

1. `INTERSECTS > TOUCHES > ADJACENT_TO`
