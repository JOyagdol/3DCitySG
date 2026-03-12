"""Reusable Cypher query fragments."""

UPSERT_NODE = """
MERGE (n:CityObject {id: $id})
SET n += $properties
"""

UPSERT_EDGE_TEMPLATE = """
MATCH (s:CityObject {id: $source_id})
MATCH (t:CityObject {id: $target_id})
MERGE (s)-[r:{relation}]->(t)
SET r += $properties
"""
