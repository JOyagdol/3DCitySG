# Graph Schema

Nodes are stored with base label `CityObject` plus type labels and `node_type` property.

Spatial-relation computation details:

1. `docs/spatial_relation_spec_v1.md`
2. `docs/spatial_relation_v2_algorithm_notes.md`
3. `docs/spatial_relation_v2_algorithm_notes_ko.md`

## Core Relation Families

1. Hierarchy: `CONTAINS`, `CONSISTS_OF_BUILDING_PART`, `INTERIOR_ROOM`
2. Installation/Furniture: `OUTER_BUILDING_INSTALLATION`, `INTERIOR_BUILDING_INSTALLATION`, `ROOM_INSTALLATION`, `INTERIOR_FURNITURE`
3. Boundary/Opening: `BOUNDED_BY`, `HAS_SURFACE_TYPE`, `HAS_OPENING`, `HOSTED_BY`, `CONNECTS` (`Door -> Room`)
4. Spatial: `INSIDE`, `ADJACENT_TO`, `TOUCHES`, `INTERSECTS`, `ADJACENT_SURFACE`, `ATTACHED_TO`, `ABOVE`, `BELOW`
5. Appearance: `HAS_APPEARANCE`, `HAS_SURFACE_DATA`, `APPLIES_TO`
6. Geometry: `HAS_LOD_GEOMETRY`, `HAS_GEOMETRY_COMPONENT`, `HAS_GEOMETRY_MEMBER`, `HAS_GEOMETRY`, `HAS_RING`, `HAS_POS`

## Spatial Pair Scope (v1)

Spatial inference is enabled for:

1. `BuildingFurniture -> BoundarySurface`
2. `BuildingFurniture -> Door|Window` (Opening subtype by `opening_type`)
3. `BuildingFurniture -> BuildingFurniture`
4. inferred spatial edges are stored in both directions

## v2 Spatial Extension Scope

1. `OPENING --HOSTED_BY--> BOUNDARY_SURFACE`
2. `BOUNDARY_SURFACE --ADJACENT_SURFACE--> BOUNDARY_SURFACE`
3. `BuildingFurniture --ATTACHED_TO--> BOUNDARY_SURFACE` (derived from `TOUCHES`)
4. `OBJECT --ABOVE/BELOW--> OBJECT` with object scope:
   - `BuildingFurniture`
   - `Door`
   - `Window`

## Spatial Precedence

For the same `(source_id, target_id)`:

1. `INTERSECTS > TOUCHES > ADJACENT_TO`
