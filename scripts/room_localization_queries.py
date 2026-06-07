"""Run room-localization Cypher scenarios against the Neo4j world graph."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from citygml_sg.config.settings import load_project_config
from citygml_sg.storage.neo4j.client import Neo4jClient
from citygml_sg.utils.io import ensure_dir


DEFAULT_PARAMS: dict[str, object] = {
    "furniture_keywords": ["storage", "fridge", "sofa", "table"],
    "source_keywords": ["sofa"],
    "target_keywords": ["table"],
    "floor_surface_types": ["FloorSurface", "GroundSurface"],
    "wall_surface_types": ["WallSurface", "ClosureSurface"],
    "min_doors": 1,
    "min_windows": 1,
    "furniture_keyword_weight": 3.0,
    "default_object_weight": 3.0,
    "door_weight": 1.0,
    "installation_weight": 1.5,
    "installation_keywords": ["column", "pillar", "\uae30\ub465"],
    "installation_target_ids": [],
    "observed_objects": [],
    "observed_relations": [],
    "view_graph_path": None,
}

KITCHEN_FURNITURE_CATEGORIES = {"sink", "counter", "cabinet", "storage", "fridge", "kitchen"}
LOW_CONFIDENCE_FURNITURE_CATEGORIES = {"sofa", "table", "tv"}
NON_FURNITURE_VIEW_CATEGORIES = {
    "door",
    "window",
    "opening",
    "floor",
    "floor_surface",
    "floorsurface",
    "wall",
    "wall_surface",
    "wallsurface",
    "boundarysurface",
    "boundary_surface",
    "buildinginstallation",
    "building_installation",
    "intbuildinginstallation",
    "int_building_installation",
    "installation",
    "column",
    "pillar",
    "\uae30\ub465",
}
INSTALLATION_VIEW_CATEGORIES = {
    "buildinginstallation",
    "building_installation",
    "intbuildinginstallation",
    "int_building_installation",
    "installation",
    "column",
    "pillar",
    "\uae30\ub465",
}


ROOM_INVENTORY_QUERY = """
MATCH (r:Room)
OPTIONAL MATCH (f:BuildingFurniture)-[:INSIDE]->(r)
WITH r,
     count(DISTINCT f) AS furniture_count,
     [name IN collect(DISTINCT coalesce(f.gml_name, f.attr_ifc_object_type, f.id)) WHERE name IS NOT NULL] AS furniture_names
OPTIONAL MATCH (d:Opening {opening_type: 'Door'})-[:CONNECTS]->(r)
WITH r, furniture_count, furniture_names, count(DISTINCT d) AS door_count
OPTIONAL MATCH (r)-[:BOUNDED_BY]->(:BoundarySurface)-[:HAS_OPENING]->(w:Opening {opening_type: 'Window'})
RETURN
  r.id AS room_id,
  coalesce(r.gml_name, r.id) AS room_name,
  furniture_count,
  furniture_names,
  door_count,
  count(DISTINCT w) AS room_boundary_window_count
ORDER BY furniture_count DESC, door_count DESC, room_id
LIMIT $limit
"""


OBJECT_KEYWORD_QUERY = """
MATCH (r:Room)
OPTIONAL MATCH (f:BuildingFurniture)-[:INSIDE]->(r)
WITH r, collect(DISTINCT f) AS furniture
WITH r, furniture,
     [f IN furniture WHERE f IS NOT NULL |
       {
         id: f.id,
         name: coalesce(f.gml_name, f.attr_ifc_object_type, f.id),
         category:
           CASE
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'sink' THEN 'sink'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'counter' THEN 'counter'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'cabinet' THEN 'cabinet'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'storage' THEN 'storage'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'fridge'
               OR toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'freezer'
               OR toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'refrigerator' THEN 'fridge'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'sofa' THEN 'sofa'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'tv'
               OR toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'television'
               OR toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'display' THEN 'tv'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'table' THEN 'table'
             ELSE null
           END
       }
     ] AS categorized_objects
WITH r, furniture, [obj IN categorized_objects WHERE obj.category IN $furniture_keywords] AS matched_objects
OPTIONAL MATCH (d:Opening {opening_type: 'Door'})-[:CONNECTS]->(r)
WITH r, furniture, matched_objects, count(DISTINCT d) AS door_count
WITH r, furniture, matched_objects, door_count,
     reduce(total = 0.0, obj IN matched_objects |
       total + coalesce(
         head([obs IN $observed_objects
           WHERE toLower(coalesce(obs.category, '')) = obj.category |
           toFloat(coalesce(obs.weight, $default_object_weight))
           * toFloat(coalesce(obs.confidence, 1.0))
           * toFloat(coalesce(obs.visibility, 1.0))
         ]),
         CASE
           WHEN obj.category IN ['sink', 'counter', 'cabinet', 'storage', 'fridge', 'kitchen'] THEN 4.0
           WHEN obj.category IN ['sofa', 'table', 'tv'] THEN 1.0
           ELSE $furniture_keyword_weight
         END
       )
     )
     + CASE WHEN door_count >= $min_doors THEN $door_weight ELSE 0.0 END AS score
RETURN
  r.id AS room_id,
  coalesce(r.gml_name, r.id) AS room_name,
  score,
  [obj IN matched_objects | obj.category] AS matched_furniture_keywords,
  matched_objects,
  size(matched_objects) AS matched_furniture_keyword_count,
  [f IN furniture | coalesce(f.gml_name, f.attr_ifc_object_type, f.id)] AS furniture_names,
  door_count
ORDER BY score DESC, matched_furniture_keyword_count DESC, door_count DESC, room_id
LIMIT $limit
"""


OPENING_HOST_QUERY = """
MATCH (op:Opening)-[:HOSTED_BY]->(bs:BoundarySurface)
OPTIONAL MATCH (op)-[:CONNECTS]->(r:Room)
WITH
  coalesce(r.id, 'UNRESOLVED_ROOM') AS room_id,
  coalesce(r.gml_name, r.id, 'UNRESOLVED_ROOM') AS room_name,
  op,
  bs
RETURN
  room_id,
  room_name,
  count(DISTINCT CASE WHEN op.opening_type = 'Door' THEN op END) AS hosted_door_count,
  count(DISTINCT CASE WHEN op.opening_type = 'Window' THEN op END) AS hosted_window_count,
  collect(DISTINCT {
    opening_id: op.id,
    opening_name: coalesce(op.gml_name, op.id),
    opening_type: op.opening_type,
    host_surface_id: bs.id,
    host_surface_name: coalesce(bs.gml_name, bs.id),
    host_surface_type: bs.surface_type
  }) AS opening_hosts
ORDER BY room_id <> 'UNRESOLVED_ROOM' DESC, hosted_door_count DESC, hosted_window_count DESC, room_id
LIMIT $limit
"""


SURFACE_ATTACHMENT_QUERY = """
MATCH (r:Room)
OPTIONAL MATCH (f:BuildingFurniture)-[:INSIDE]->(r)
OPTIONAL MATCH (f)-[rel:ATTACHED_TO|TOUCHES|ADJACENT_TO]->(bs:BoundarySurface)
WITH r,
     collect(DISTINCT CASE
       WHEN rel IS NULL THEN null
       ELSE {
         furniture_id: f.id,
         furniture_name: coalesce(f.gml_name, f.attr_ifc_object_type, f.id),
         relation: type(rel),
         surface_id: bs.id,
         surface_name: coalesce(bs.gml_name, bs.id),
         surface_type: bs.surface_type,
         evidence_score: rel.evidence_score,
         confidence: rel.confidence
       }
     END) AS raw_surface_relations
WITH r, [item IN raw_surface_relations WHERE item IS NOT NULL] AS surface_relations
RETURN
  r.id AS room_id,
  coalesce(r.gml_name, r.id) AS room_name,
  size([item IN surface_relations WHERE item.relation = 'ATTACHED_TO']) AS attached_to_count,
  size([item IN surface_relations WHERE item.surface_type IN $floor_surface_types]) AS floor_relation_count,
  size([item IN surface_relations WHERE item.surface_type IN $wall_surface_types]) AS wall_relation_count,
  surface_relations
ORDER BY attached_to_count DESC, floor_relation_count DESC, wall_relation_count DESC, room_id
LIMIT $limit
"""


FURNITURE_PAIR_RELATION_QUERY = """
MATCH (r:Room)
MATCH (a:BuildingFurniture)-[:INSIDE]->(r)
MATCH (b:BuildingFurniture)-[:INSIDE]->(r)
WHERE a.id < b.id
WITH r, a, b,
     toLower(coalesce(a.gml_name, '') + ' ' + coalesce(a.attr_ifc_object_type, '') + ' ' + coalesce(a.id, '')) AS a_text,
     toLower(coalesce(b.gml_name, '') + ' ' + coalesce(b.attr_ifc_object_type, '') + ' ' + coalesce(b.id, '')) AS b_text
WHERE (
    any(kw IN $source_keywords WHERE a_text CONTAINS toLower(kw))
    AND any(kw IN $target_keywords WHERE b_text CONTAINS toLower(kw))
  ) OR (
    any(kw IN $source_keywords WHERE b_text CONTAINS toLower(kw))
    AND any(kw IN $target_keywords WHERE a_text CONTAINS toLower(kw))
  )
OPTIONAL MATCH (a)-[rel:ADJACENT_TO|TOUCHES|INTERSECTS|ABOVE|BELOW]-(b)
WITH r,
     collect(DISTINCT {
       source_id: a.id,
       source_name: coalesce(a.gml_name, a.attr_ifc_object_type, a.id),
       target_id: b.id,
       target_name: coalesce(b.gml_name, b.attr_ifc_object_type, b.id),
       relation: type(rel),
       evidence_score: rel.evidence_score,
       confidence: rel.confidence
     }) AS raw_pair_relations
WITH r, [item IN raw_pair_relations WHERE item.relation IS NOT NULL] AS pair_relations
RETURN
  r.id AS room_id,
  coalesce(r.gml_name, r.id) AS room_name,
  size(pair_relations) AS matched_pair_relation_count,
  pair_relations
ORDER BY matched_pair_relation_count DESC, room_id
LIMIT $limit
"""


OPENING_BOUNDARY_ROOM_SCORE_QUERY = """
MATCH (r:Room)
OPTIONAL MATCH (d:Opening {opening_type: 'Door'})-[:CONNECTS]->(r)
WITH r, count(DISTINCT d) AS door_count
CALL {
  WITH r
  OPTIONAL MATCH (r)-[:BOUNDED_BY]->(bs:BoundarySurface)-[:HAS_OPENING]->(w:Opening {opening_type: 'Window'})
  WITH r,
       collect(DISTINCT {
         opening_id: w.id,
         opening_name: coalesce(w.gml_name, w.id),
         host_surface_id: bs.id,
         host_surface_name: coalesce(bs.gml_name, bs.id),
         host_surface_type: bs.surface_type,
         evidence_source: 'room_boundary'
       }) AS direct_windows
  OPTIONAL MATCH (r)<-[:CONNECTS]-(connected_opening:Opening)-[:HOSTED_BY]->(host_wall:BoundarySurface)<-[:HOSTED_BY]-(hosted_window:Opening {opening_type: 'Window'})
  WITH direct_windows,
       collect(DISTINCT {
         opening_id: hosted_window.id,
         opening_name: coalesce(hosted_window.gml_name, hosted_window.id),
         host_surface_id: host_wall.id,
         host_surface_name: coalesce(host_wall.gml_name, host_wall.id),
         host_surface_type: host_wall.surface_type,
         evidence_source: 'connected_opening_host_wall'
       }) AS hosted_windows
  WITH [item IN direct_windows + hosted_windows WHERE item.opening_id IS NOT NULL] AS raw_windows
  WITH raw_windows, reduce(ids = [], item IN raw_windows | CASE WHEN item.opening_id IN ids THEN ids ELSE ids + item.opening_id END) AS window_ids
  WITH window_ids, [id IN window_ids | head([item IN raw_windows WHERE item.opening_id = id])] AS windows
  RETURN size(windows) AS window_count, windows[0..8] AS window_evidence
}
CALL {
  WITH r
  OPTIONAL MATCH (r)-[:BOUNDED_BY]->(wall:BoundarySurface)
  WHERE wall.surface_type IN $wall_surface_types
  WITH r,
       collect(DISTINCT wall) AS direct_walls,
       collect(DISTINCT {
         surface_id: wall.id,
         surface_name: coalesce(wall.gml_name, wall.id),
         surface_type: wall.surface_type,
         evidence_source: 'room_boundary'
       }) AS direct_wall_items
  OPTIONAL MATCH (r)<-[:CONNECTS]-(connected_opening:Opening)-[:HOSTED_BY]->(host_wall:BoundarySurface)
  WHERE host_wall.surface_type IN $wall_surface_types
  WITH direct_walls,
       direct_wall_items,
       collect(DISTINCT host_wall) AS host_walls,
       collect(DISTINCT {
         surface_id: host_wall.id,
         surface_name: coalesce(host_wall.gml_name, host_wall.id),
         surface_type: host_wall.surface_type,
         evidence_source: 'connected_opening_host_wall'
       }) AS host_wall_items
  WITH direct_wall_items + [item IN host_wall_items WHERE item.surface_id IS NOT NULL AND NOT item.surface_id IN [wall IN direct_walls | wall.id]] AS raw_walls
  WITH [item IN raw_walls WHERE item.surface_id IS NOT NULL] AS raw_walls
  WITH raw_walls, reduce(ids = [], item IN raw_walls | CASE WHEN item.surface_id IN ids THEN ids ELSE ids + item.surface_id END) AS wall_ids
  WITH wall_ids, [id IN wall_ids | head([item IN raw_walls WHERE item.surface_id = id])] AS walls
  WITH size(walls) AS wall_surface_count, walls AS raw_walls
  RETURN wall_surface_count, [item IN raw_walls WHERE item.surface_id IS NOT NULL][0..8] AS wall_surface_evidence
}
CALL {
  WITH r
  OPTIONAL MATCH (r)-[:BOUNDED_BY]->(floor:BoundarySurface)
  WHERE floor.surface_type IN $floor_surface_types
  WITH r,
       collect(DISTINCT floor) AS direct_floors,
       collect(DISTINCT {
         surface_id: floor.id,
         surface_name: coalesce(floor.gml_name, floor.id),
         surface_type: floor.surface_type,
         evidence_source: 'room_boundary'
       }) AS direct_floor_items
  OPTIONAL MATCH (r)<-[:CONNECTS]-(connected_opening:Opening)-[:HOSTED_BY]->(host_wall:BoundarySurface)-[:ADJACENT_SURFACE]-(host_floor:BoundarySurface)
  WHERE host_floor.surface_type IN $floor_surface_types
  WITH direct_floors,
       direct_floor_items,
       collect(DISTINCT {
         surface_id: host_floor.id,
         surface_name: coalesce(host_floor.gml_name, host_floor.id),
         surface_type: host_floor.surface_type,
         evidence_source: 'connected_opening_host_wall_adjacency'
       }) AS host_floor_items
  WITH direct_floor_items + [item IN host_floor_items WHERE item.surface_id IS NOT NULL AND NOT item.surface_id IN [floor IN direct_floors | floor.id]] AS raw_floors
  WITH [item IN raw_floors WHERE item.surface_id IS NOT NULL] AS raw_floors
  WITH raw_floors, reduce(ids = [], item IN raw_floors | CASE WHEN item.surface_id IN ids THEN ids ELSE ids + item.surface_id END) AS floor_ids
  WITH floor_ids, [id IN floor_ids | head([item IN raw_floors WHERE item.surface_id = id])] AS floors
  WITH size(floors) AS floor_surface_count, floors AS raw_floors
  RETURN floor_surface_count, [item IN raw_floors WHERE item.surface_id IS NOT NULL][0..8] AS floor_surface_evidence
}
CALL {
  WITH r
  OPTIONAL MATCH (r)-[:BOUNDED_BY]->(a:BoundarySurface)-[rel:ADJACENT_SURFACE]-(b:BoundarySurface)
  WHERE (
      a.surface_type IN $wall_surface_types AND b.surface_type IN $floor_surface_types
    ) OR (
      a.surface_type IN $floor_surface_types AND b.surface_type IN $wall_surface_types
    )
  WITH r,
       collect(DISTINCT {
         source_id: a.id,
         source_name: coalesce(a.gml_name, a.id),
         source_type: a.surface_type,
         target_id: b.id,
         target_name: coalesce(b.gml_name, b.id),
         target_type: b.surface_type,
         relation: type(rel),
         shared_edge_length: rel.shared_edge_length,
         evidence_score: rel.evidence_score,
         confidence: rel.confidence
       }) AS raw_wall_floor_adjacencies
  OPTIONAL MATCH (r)<-[:CONNECTS]-(connected_opening:Opening)-[:HOSTED_BY]->(host_wall:BoundarySurface)-[fallback_rel:ADJACENT_SURFACE]-(host_floor:BoundarySurface)
  WHERE (
      host_wall.surface_type IN $wall_surface_types AND host_floor.surface_type IN $floor_surface_types
    ) OR (
      host_wall.surface_type IN $floor_surface_types AND host_floor.surface_type IN $wall_surface_types
    )
  WITH raw_wall_floor_adjacencies,
       collect(DISTINCT {
         source_id: host_wall.id,
         source_name: coalesce(host_wall.gml_name, host_wall.id),
         source_type: host_wall.surface_type,
         target_id: host_floor.id,
         target_name: coalesce(host_floor.gml_name, host_floor.id),
         target_type: host_floor.surface_type,
         relation: type(fallback_rel),
         shared_edge_length: fallback_rel.shared_edge_length,
         evidence_score: fallback_rel.evidence_score,
         confidence: fallback_rel.confidence,
         evidence_source: 'connected_opening_host_wall_adjacency'
       }) AS fallback_wall_floor_adjacencies
  WITH raw_wall_floor_adjacencies + fallback_wall_floor_adjacencies AS raw_wall_floor_adjacencies
  WITH [item IN raw_wall_floor_adjacencies WHERE item.source_id IS NOT NULL AND item.target_id IS NOT NULL] AS raw_wall_floor_adjacencies
  WITH raw_wall_floor_adjacencies,
       reduce(ids = [], item IN raw_wall_floor_adjacencies |
         CASE
           WHEN (CASE WHEN item.source_id < item.target_id THEN item.source_id + '|' + item.target_id ELSE item.target_id + '|' + item.source_id END) IN ids
           THEN ids
           ELSE ids + (CASE WHEN item.source_id < item.target_id THEN item.source_id + '|' + item.target_id ELSE item.target_id + '|' + item.source_id END)
         END
       ) AS adjacency_ids
  WITH adjacency_ids,
       [id IN adjacency_ids |
         head([item IN raw_wall_floor_adjacencies WHERE (CASE WHEN item.source_id < item.target_id THEN item.source_id + '|' + item.target_id ELSE item.target_id + '|' + item.source_id END) = id])
       ] AS wall_floor_adjacencies
  RETURN size(wall_floor_adjacencies) AS wall_floor_adjacency_count,
         wall_floor_adjacencies[0..8] AS wall_floor_adjacency_evidence
}
CALL {
  WITH r
  OPTIONAL MATCH (r)-[:ROOM_INSTALLATION]->(inst)
  WITH collect(DISTINCT inst) AS raw_installations
  WITH [inst IN raw_installations
        WHERE inst IS NOT NULL
          AND ('IntBuildingInstallation' IN labels(inst) OR 'BuildingInstallation' IN labels(inst))
       ] AS installations
  WITH installations,
       [inst IN installations WHERE any(kw IN $installation_keywords
         WHERE toLower(
           coalesce(inst.gml_name, '') + ' ' +
           coalesce(inst.attr_ifc_object_type, '') + ' ' +
           coalesce(inst.attr_other_category_0, '') + ' ' +
           coalesce(inst.attr_other_family, '') + ' ' +
           coalesce(inst.id, '')
         ) CONTAINS toLower(kw)
       )] AS matched_installations
  OPTIONAL MATCH (target_int:IntBuildingInstallation)
  WHERE target_int.id IN $installation_target_ids OR target_int.gml_id IN $installation_target_ids
  WITH installations, matched_installations, collect(DISTINCT target_int) AS target_int_installations
  OPTIONAL MATCH (target_outer:BuildingInstallation)
  WHERE target_outer.id IN $installation_target_ids OR target_outer.gml_id IN $installation_target_ids
  WITH installations,
       matched_installations,
       target_int_installations,
       collect(DISTINCT target_outer) AS target_outer_installations
  WITH installations,
       matched_installations,
       target_int_installations + target_outer_installations AS target_installations
  WITH installations,
       matched_installations,
       target_installations,
       [inst IN target_installations
         WHERE inst.id IN [room_inst IN installations | room_inst.id]
            OR inst.gml_id IN [room_inst IN installations | room_inst.gml_id]
       ] AS room_target_installations
  WITH installations,
       target_installations,
       room_target_installations,
       matched_installations +
       [inst IN room_target_installations
         WHERE NOT inst.id IN [matched IN matched_installations | matched.id]
       ] AS scoring_installations
  RETURN size(installations) AS room_installation_count,
         size(scoring_installations) AS matched_installation_count,
         size(target_installations) AS target_installation_count,
         size(room_target_installations) AS room_target_installation_count,
         [inst IN scoring_installations | {
           installation_id: inst.id,
           installation_name: coalesce(inst.gml_name, inst.attr_ifc_object_type, inst.id),
           installation_type: coalesce(inst.installation_type, inst.object_type),
           category: coalesce(inst.attr_other_category_0, inst.attr_ifc_object_type)
         }][0..8] AS installation_evidence,
         [inst IN target_installations | {
           installation_id: inst.id,
           installation_name: coalesce(inst.gml_name, inst.attr_ifc_object_type, inst.id),
           installation_type: coalesce(inst.installation_type, inst.object_type),
           category: coalesce(inst.attr_other_category_0, inst.attr_ifc_object_type),
           room_linked: inst.id IN [room_inst IN room_target_installations | room_inst.id]
         }][0..8] AS target_installation_evidence
}
WITH r,
     door_count,
     window_count,
     wall_surface_count,
     floor_surface_count,
     wall_floor_adjacency_count,
     room_installation_count,
     matched_installation_count,
     target_installation_count,
     room_target_installation_count,
     window_evidence,
     wall_surface_evidence,
     floor_surface_evidence,
     wall_floor_adjacency_evidence,
     installation_evidence,
     target_installation_evidence,
     coalesce(
       head([obs IN $observed_objects
         WHERE toLower(coalesce(obs.category, '')) IN ['window', 'opening'] |
         toFloat(coalesce(obs.weight, 2.0))
         * toFloat(coalesce(obs.confidence, 1.0))
         * toFloat(coalesce(obs.visibility, 1.0))
       ]),
       2.0
     ) AS observed_window_weight,
     coalesce(
       head([obs IN $observed_objects
         WHERE toLower(coalesce(obs.category, '')) = 'door' |
         toFloat(coalesce(obs.weight, $door_weight))
         * toFloat(coalesce(obs.confidence, 1.0))
         * toFloat(coalesce(obs.visibility, 1.0))
       ]),
       $door_weight
     ) AS observed_door_weight,
     coalesce(
       head([obs IN $observed_objects
         WHERE toLower(coalesce(obs.category, '')) IN [
           'installation',
           'buildinginstallation',
           'building_installation',
           'intbuildinginstallation',
           'int_building_installation',
           'column',
           'pillar'
         ] |
         toFloat(coalesce(obs.weight, $installation_weight))
         * toFloat(coalesce(obs.confidence, 1.0))
         * toFloat(coalesce(obs.visibility, 1.0))
       ]),
       0.0
     ) AS observed_installation_weight
WITH r,
     door_count,
     window_count,
     wall_surface_count,
     floor_surface_count,
     wall_floor_adjacency_count,
     room_installation_count,
     matched_installation_count,
     target_installation_count,
     room_target_installation_count,
     window_evidence,
     wall_surface_evidence,
     floor_surface_evidence,
     wall_floor_adjacency_evidence,
     installation_evidence,
     target_installation_evidence,
     CASE WHEN window_count >= $min_windows THEN observed_window_weight ELSE 0.0 END AS window_score,
     CASE WHEN door_count >= $min_doors THEN observed_door_weight ELSE 0.0 END AS door_score,
     CASE WHEN wall_surface_count > 4 THEN 1.0 ELSE wall_surface_count * 0.25 END AS wall_surface_score,
     CASE WHEN floor_surface_count > 0 THEN 0.5 ELSE 0.0 END AS floor_surface_score,
     CASE WHEN wall_floor_adjacency_count > 4 THEN 1.0 ELSE wall_floor_adjacency_count * 0.25 END AS boundary_topology_score,
     CASE WHEN matched_installation_count > 0 THEN observed_installation_weight ELSE 0.0 END AS installation_score
WITH r,
     door_count,
     window_count,
     wall_surface_count,
     floor_surface_count,
     wall_floor_adjacency_count,
     room_installation_count,
     matched_installation_count,
     target_installation_count,
     room_target_installation_count,
     window_evidence,
     wall_surface_evidence,
     floor_surface_evidence,
     wall_floor_adjacency_evidence,
     installation_evidence,
     target_installation_evidence,
     window_score,
     door_score,
     wall_surface_score,
     floor_surface_score,
     boundary_topology_score,
     installation_score,
     window_score + door_score + wall_surface_score + floor_surface_score + boundary_topology_score + installation_score AS total_score
RETURN
  r.id AS room_id,
  coalesce(r.gml_name, r.id) AS room_name,
  total_score,
  window_count,
  door_count,
  wall_surface_count,
  floor_surface_count,
  wall_floor_adjacency_count,
  room_installation_count,
  matched_installation_count,
  target_installation_count,
  room_target_installation_count,
  window_evidence,
  wall_surface_evidence,
  floor_surface_evidence,
  wall_floor_adjacency_evidence,
  installation_evidence,
  target_installation_evidence,
  {
    window_score: window_score,
    door_score: door_score,
    wall_surface_score: wall_surface_score,
    floor_surface_score: floor_surface_score,
    boundary_topology_score: boundary_topology_score,
    installation_score: installation_score
  } AS score_breakdown
ORDER BY total_score DESC, matched_installation_count DESC, window_count DESC, door_count DESC, wall_floor_adjacency_count DESC, room_id
LIMIT $limit
"""


COMBINED_ROOM_SCORE_QUERY = """
MATCH (r:Room)
OPTIONAL MATCH (f:BuildingFurniture)-[:INSIDE]->(r)
WITH r, collect(DISTINCT f) AS furniture
WITH r,
     [f IN furniture | coalesce(f.gml_name, f.attr_ifc_object_type, f.id)] AS furniture_names,
     [f IN furniture WHERE f IS NOT NULL |
       {
         id: f.id,
         name: coalesce(f.gml_name, f.attr_ifc_object_type, f.id),
         category:
           CASE
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'sink' THEN 'sink'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'counter' THEN 'counter'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'cabinet' THEN 'cabinet'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'storage' THEN 'storage'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'fridge'
               OR toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'freezer'
               OR toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'refrigerator' THEN 'fridge'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'sofa' THEN 'sofa'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'tv'
               OR toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'television'
               OR toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'display' THEN 'tv'
             WHEN toLower(coalesce(f.gml_name, '') + ' ' + coalesce(f.attr_ifc_object_type, '') + ' ' + coalesce(f.id, '')) CONTAINS 'table' THEN 'table'
             ELSE null
           END
       }
     ] AS categorized_objects
WITH r,
     furniture_names,
     [obj IN categorized_objects WHERE obj.category IN $furniture_keywords] AS matched_objects
OPTIONAL MATCH (d:Opening {opening_type: 'Door'})-[:CONNECTS]->(r)
WITH r, furniture_names, matched_objects, count(DISTINCT d) AS door_count
CALL {
  WITH matched_objects
  OPTIONAL MATCH (f:BuildingFurniture)-[:ATTACHED_TO]->(bs:BoundarySurface)
  WHERE f.id IN [obj IN matched_objects | obj.id]
    AND bs.surface_type IN $floor_surface_types
  WITH collect(DISTINCT f.id) AS floor_ids, matched_objects
  RETURN
    size(floor_ids) AS floor_attached_count,
    reduce(total = 0.0, obj IN matched_objects |
      total + CASE
        WHEN obj.id IN floor_ids THEN
          (
            CASE
              WHEN obj.category IN ['sink', 'counter', 'cabinet', 'storage', 'fridge', 'kitchen'] THEN 1.0
              WHEN obj.category IN ['sofa', 'table', 'tv'] THEN 0.25
              ELSE 0.5
            END
          )
          * coalesce(
            head([obs IN $observed_objects
              WHERE toLower(coalesce(obs.category, '')) = obj.category |
              toFloat(coalesce(obs.confidence, 1.0)) * toFloat(coalesce(obs.visibility, 1.0))
            ]),
            1.0
          )
        ELSE 0.0
      END
    ) AS floor_attachment_score
}
CALL {
  WITH r, matched_objects
  MATCH (a:BuildingFurniture)-[:INSIDE]->(r)
  MATCH (b:BuildingFurniture)-[:INSIDE]->(r)
  WHERE a.id < b.id
    AND a.id IN [obj IN matched_objects | obj.id]
    AND b.id IN [obj IN matched_objects | obj.id]
  MATCH (a)-[rel:ADJACENT_TO|TOUCHES|INTERSECTS|ABOVE|BELOW]-(b)
  RETURN count(DISTINCT a.id + '|' + b.id) AS furniture_relation_pair_count
}
WITH r,
     furniture_names,
     matched_objects,
     door_count,
     floor_attached_count,
     floor_attachment_score,
     furniture_relation_pair_count,
     reduce(total = 0.0, obj IN matched_objects |
       total + coalesce(
         head([obs IN $observed_objects
           WHERE toLower(coalesce(obs.category, '')) = obj.category |
           toFloat(coalesce(obs.weight, $default_object_weight))
           * toFloat(coalesce(obs.confidence, 1.0))
           * toFloat(coalesce(obs.visibility, 1.0))
         ]),
         CASE
           WHEN obj.category IN ['sink', 'counter', 'cabinet', 'storage', 'fridge', 'kitchen'] THEN 4.0
           WHEN obj.category IN ['sofa', 'table', 'tv'] THEN 1.0
           ELSE 3.0
         END
       )
     )
     + CASE WHEN door_count >= $min_doors THEN 1.0 ELSE 0.0 END
     + floor_attachment_score
     + furniture_relation_pair_count * 1.0 AS total_score
RETURN
  r.id AS room_id,
  coalesce(r.gml_name, r.id) AS room_name,
  total_score,
  [obj IN matched_objects | obj.category] AS matched_furniture_keywords,
  matched_objects,
  furniture_names,
  door_count,
  floor_attached_count,
  floor_attachment_score,
  furniture_relation_pair_count,
  {
    object_keyword_score: reduce(total = 0.0, obj IN matched_objects |
       total + coalesce(
         head([obs IN $observed_objects
           WHERE toLower(coalesce(obs.category, '')) = obj.category |
           toFloat(coalesce(obs.weight, $default_object_weight))
           * toFloat(coalesce(obs.confidence, 1.0))
           * toFloat(coalesce(obs.visibility, 1.0))
         ]),
         CASE
           WHEN obj.category IN ['sink', 'counter', 'cabinet', 'storage', 'fridge', 'kitchen'] THEN 4.0
           WHEN obj.category IN ['sofa', 'table', 'tv'] THEN 1.0
           ELSE 3.0
         END
       )
    ),
    door_score: CASE WHEN door_count >= $min_doors THEN 1.0 ELSE 0.0 END,
    floor_attachment_score: floor_attachment_score,
    furniture_relation_score: furniture_relation_pair_count * 1.0
  } AS score_breakdown
ORDER BY total_score DESC, door_count DESC, floor_attached_count DESC, room_id
LIMIT $limit
"""


SCENARIOS: dict[str, dict[str, object]] = {
    "room_inventory": {
        "description": "Room별 가구/문/창문 기본 signature를 확인한다.",
        "view_graph_schema": {},
        "query": ROOM_INVENTORY_QUERY,
    },
    "object_keyword_candidates": {
        "description": "이미지에서 검출된 furniture keyword로 후보 Room을 점수화한다.",
        "view_graph_schema": {
            "objects": [
                {"alias": "sofa", "type": "BuildingFurniture", "category": "sofa"},
                {"alias": "table", "type": "BuildingFurniture", "category": "table"},
                {"alias": "tv", "type": "BuildingFurniture", "category": "tv"},
                {"alias": "fridge", "type": "BuildingFurniture", "category": "fridge"},
                {"alias": "door", "type": "Opening", "category": "Door", "min_count": 1},
            ]
        },
        "query": OBJECT_KEYWORD_QUERY,
    },
    "opening_host_surface": {
        "description": "Door/Window가 어떤 BoundarySurface에 HOSTED_BY 되는지 확인한다.",
        "view_graph_schema": {
            "objects": [{"alias": "opening", "type": "Opening", "category": "Door|Window"}],
            "relations": [["opening", "HOSTED_BY", "BoundarySurface"]],
        },
        "query": OPENING_HOST_QUERY,
    },
    "surface_attachment": {
        "description": "가구가 Floor/Wall surface와 맺는 ATTACHED_TO/TOUCHES/ADJACENT_TO 단서를 확인한다.",
        "view_graph_schema": {
            "objects": [{"alias": "furniture", "type": "BuildingFurniture"}],
            "relations": [
                ["furniture", "ATTACHED_TO", "FloorSurface"],
                ["furniture", "ATTACHED_TO", "WallSurface"],
            ],
        },
        "query": SURFACE_ATTACHMENT_QUERY,
    },
    "furniture_pair_relation": {
        "description": "sofa-table 같은 가구쌍 공간관계가 Room 후보 식별 단서가 되는지 확인한다.",
        "view_graph_schema": {
            "objects": [
                {"alias": "sofa", "type": "BuildingFurniture", "category": "sofa"},
                {"alias": "table", "type": "BuildingFurniture", "category": "table"},
            ],
            "relations": [["sofa", "ADJACENT_TO|TOUCHES|INTERSECTS|ABOVE|BELOW", "table"]],
        },
        "query": FURNITURE_PAIR_RELATION_QUERY,
    },
    "opening_boundary_room_score": {
        "description": "Window/Door opening + wall/floor boundary topology cues for furniture-sparse corridor or lab views.",
        "view_graph_schema": {
            "objects": [
                {"alias": "window", "type": "Opening", "category": "window"},
                {"alias": "door", "type": "Opening", "category": "door", "min_count": 1},
                {"alias": "wall", "type": "WallSurface", "category": "wall_surface"},
                {"alias": "floor", "type": "FloorSurface", "category": "floor_surface"},
                {"alias": "column", "type": "IntBuildingInstallation", "category": "column"},
            ],
            "relations": [
                ["window", "HOSTED_BY", "WallSurface"],
                ["WallSurface", "ADJACENT_SURFACE", "FloorSurface"],
                ["door", "CONNECTS", "Room"],
                ["Room", "ROOM_INSTALLATION", "column"],
            ],
        },
        "query": OPENING_BOUNDARY_ROOM_SCORE_QUERY,
    },
    "combined_room_score": {
        "description": "객체 keyword + Door 연결 + Floor attachment + 가구쌍 관계를 합산해 Room 후보를 랭킹한다.",
        "view_graph_schema": {
            "objects": [
                {"alias": "sofa", "type": "BuildingFurniture", "category": "sofa"},
                {"alias": "table", "type": "BuildingFurniture", "category": "table"},
                {"alias": "tv", "type": "BuildingFurniture", "category": "tv"},
                {"alias": "fridge", "type": "BuildingFurniture", "category": "fridge"},
                {"alias": "door", "type": "Opening", "category": "Door", "min_count": 1},
            ],
            "relations": [
                ["BuildingFurniture", "ATTACHED_TO", "FloorSurface"],
                ["BuildingFurniture", "ADJACENT_TO|TOUCHES|INTERSECTS|ABOVE|BELOW", "BuildingFurniture"],
            ],
        },
        "query": COMBINED_ROOM_SCORE_QUERY,
    },
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run room-localization Cypher scenario tests")
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Project config path containing Neo4j connection info",
    )
    parser.add_argument(
        "--output",
        default="data/output/room_localization_query_report.json",
        help="Room-localization scenario report JSON path",
    )
    parser.add_argument(
        "--scenario",
        choices=["all", *SCENARIOS.keys()],
        default="all",
        help="Scenario to run",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max rows per scenario")
    parser.add_argument(
        "--furniture-keywords",
        nargs="*",
        default=None,
        help="Furniture category/name keywords observed from an image view graph",
    )
    parser.add_argument(
        "--source-keywords",
        nargs="*",
        default=None,
        help="Source object keywords for furniture-pair scenario",
    )
    parser.add_argument(
        "--target-keywords",
        nargs="*",
        default=None,
        help="Target object keywords for furniture-pair scenario",
    )
    parser.add_argument(
        "--view-graph",
        default=None,
        help="Observed view graph JSON path. When provided, object scoring uses weight * confidence * visibility.",
    )
    return parser


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _default_observed_weight(category: str) -> float:
    if category in KITCHEN_FURNITURE_CATEGORIES:
        return 4.0
    if category in LOW_CONFIDENCE_FURNITURE_CATEGORIES:
        return 1.0
    return float(DEFAULT_PARAMS["furniture_keyword_weight"])


def _as_float(value: object, *, field: str, path: Path) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: observed object field '{field}' must be numeric, got {value!r}") from exc


def _load_observed_view_graph(
    path_value: str | None,
) -> tuple[list[dict[str, object]], list[object], dict[str, object], dict[str, object]]:
    if not path_value:
        return [], [], {}, {}

    path = Path(path_value)
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: observed view graph must be a JSON object")

    objects_raw = raw.get("objects", [])
    if not isinstance(objects_raw, list):
        raise ValueError(f"{path}: 'objects' must be a list")

    objects: list[dict[str, object]] = []
    for index, item in enumerate(objects_raw):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: objects[{index}] must be a JSON object")
        category = str(item.get("category", "")).strip().lower()
        if not category:
            continue

        observed: dict[str, object] = {
            "alias": str(item.get("alias") or category),
            "category": category,
            "weight": _as_float(item.get("weight", _default_observed_weight(category)), field="weight", path=path),
            "confidence": _as_float(item.get("confidence", 1.0), field="confidence", path=path),
            "visibility": _as_float(item.get("visibility", 1.0), field="visibility", path=path),
        }
        if item.get("type") is not None:
            observed["type"] = str(item["type"])
        for id_field in ("id", "gml_id", "target_id"):
            if item.get(id_field) is not None:
                observed[id_field] = str(item[id_field])
        if isinstance(item.get("target_ids"), list):
            observed["target_ids"] = [str(target_id) for target_id in item["target_ids"]]
        if isinstance(item.get("attributes"), dict):
            observed["attributes"] = item["attributes"]
        objects.append(observed)

    relations_raw = raw.get("relations", [])
    if not isinstance(relations_raw, list):
        raise ValueError(f"{path}: 'relations' must be a list")

    constraints_raw = raw.get("constraints", {})
    if not isinstance(constraints_raw, dict):
        raise ValueError(f"{path}: 'constraints' must be a JSON object")
    query_raw = raw.get("query", {})
    if not isinstance(query_raw, dict):
        raise ValueError(f"{path}: 'query' must be a JSON object")
    return objects, relations_raw, constraints_raw, query_raw


def _optional_non_negative_int(value: object, *, field: str, path: str) -> int | None:
    if value is None:
        return None
    try:
        converted = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: observed constraint field '{field}' must be an integer, got {value!r}") from exc
    if converted < 0:
        raise ValueError(f"{path}: observed constraint field '{field}' must be non-negative, got {value!r}")
    return converted


def _build_params(args: argparse.Namespace) -> dict[str, object]:
    params = dict(DEFAULT_PARAMS)
    observed_objects, observed_relations, observed_constraints, observed_query = _load_observed_view_graph(
        args.view_graph
    )
    if args.view_graph is not None:
        params["view_graph_path"] = str(args.view_graph)
        params["observed_objects"] = observed_objects
        params["observed_relations"] = observed_relations
        params["observed_constraints"] = observed_constraints
        params["observed_query"] = observed_query
        room_constraints = observed_constraints.get("room", {})
        if isinstance(room_constraints, dict):
            min_doors = _optional_non_negative_int(
                room_constraints.get("min_doors"), field="constraints.room.min_doors", path=str(args.view_graph)
            )
            min_windows = _optional_non_negative_int(
                room_constraints.get("min_windows"), field="constraints.room.min_windows", path=str(args.view_graph)
            )
            candidate_limit = _optional_non_negative_int(
                room_constraints.get("candidate_limit"),
                field="constraints.room.candidate_limit",
                path=str(args.view_graph),
            )
            if min_doors is not None:
                params["min_doors"] = min_doors
            if min_windows is not None:
                params["min_windows"] = min_windows
            if candidate_limit is not None:
                params["limit"] = max(1, candidate_limit)
        observed_furniture_keywords = sorted(
            {
                str(item["category"])
                for item in observed_objects
                if str(item["category"]) not in NON_FURNITURE_VIEW_CATEGORIES
            }
        )
        observed_installation_keywords = sorted(
            {
                str(item["category"])
                for item in observed_objects
                if str(item["category"]) in INSTALLATION_VIEW_CATEGORIES
            }
        )
        if observed_furniture_keywords:
            params["furniture_keywords"] = observed_furniture_keywords
        if observed_installation_keywords:
            params["installation_keywords"] = sorted(
                set(str(item) for item in params.get("installation_keywords", []))
                | set(observed_installation_keywords)
            )
        observed_installation_target_ids: set[str] = set()
        for item in observed_objects:
            if str(item["category"]) not in INSTALLATION_VIEW_CATEGORIES:
                continue
            for id_field in ("id", "gml_id", "target_id"):
                if item.get(id_field) is not None:
                    observed_installation_target_ids.add(str(item[id_field]))
            if isinstance(item.get("target_ids"), list):
                observed_installation_target_ids.update(str(target_id) for target_id in item["target_ids"])
            attributes = item.get("attributes")
            if isinstance(attributes, dict):
                for id_field in ("id", "gml_id", "target_id"):
                    if attributes.get(id_field) is not None:
                        observed_installation_target_ids.add(str(attributes[id_field]))
                if isinstance(attributes.get("target_ids"), list):
                    observed_installation_target_ids.update(
                        str(target_id) for target_id in attributes["target_ids"]
                    )
        if observed_installation_target_ids:
            params["installation_target_ids"] = sorted(
                set(str(item) for item in params.get("installation_target_ids", []))
                | observed_installation_target_ids
            )
    if args.furniture_keywords is not None:
        params["furniture_keywords"] = list(args.furniture_keywords)
    if args.source_keywords is not None:
        params["source_keywords"] = list(args.source_keywords)
    if args.target_keywords is not None:
        params["target_keywords"] = list(args.target_keywords)
    if args.limit is not None:
        params["limit"] = max(1, int(args.limit))
    else:
        params["limit"] = max(1, int(params.get("limit", 10)))
    return params


def _selected_scenarios(name: str) -> list[tuple[str, dict[str, object]]]:
    if name == "all":
        return list(SCENARIOS.items())
    return [(name, SCENARIOS[name])]


def main() -> int:
    args = build_parser().parse_args()
    params = _build_params(args)
    config = load_project_config(args.config)
    neo4j = config.neo4j
    client = Neo4jClient(neo4j.uri, neo4j.username, neo4j.password, database=neo4j.database)

    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, object]] = []
    try:
        with client.session() as session:
            for scenario_id, scenario in _selected_scenarios(args.scenario):
                query = str(scenario["query"])
                t0 = perf_counter()
                records = session.run(query, **params).data()
                elapsed_ms = (perf_counter() - t0) * 1000.0
                rows = [_json_safe(record) for record in records]
                top_room = rows[0] if rows else None
                results.append(
                    {
                        "id": scenario_id,
                        "description": scenario["description"],
                        "view_graph_schema": scenario["view_graph_schema"],
                        "query": query.strip(),
                        "params": params,
                        "row_count": len(rows),
                        "elapsed_ms": round(elapsed_ms, 3),
                        "top_room": top_room,
                        "rows": rows,
                    }
                )
    finally:
        client.close()

    report = {
        "summary": {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "config_path": str(args.config),
            "output_path": str(args.output),
            "neo4j_uri": neo4j.uri,
            "neo4j_database": neo4j.database,
            "scenario": args.scenario,
            "scenario_total": len(results),
            "limit": int(params["limit"]),
            "view_graph_path": params.get("view_graph_path"),
            "observed_object_count": len(params.get("observed_objects", [])),
            "observed_relation_count": len(params.get("observed_relations", [])),
        },
        "scenarios": results,
    }

    output = Path(args.output)
    ensure_dir(output.parent)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Room-localization query report written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
