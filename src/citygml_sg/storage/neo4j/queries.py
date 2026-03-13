"""Reusable Cypher query fragments."""

UPSERT_NODE = """
MERGE (n:CityObject {id: $id})
SET n += $properties
"""

UPSERT_NODE_WITH_LABEL_TEMPLATE = """
MERGE (n:CityObject {{id: $id}})
SET n += $properties
SET n:{label}
"""

UPSERT_NODE_WITH_LABEL_BATCH_TEMPLATE = """
UNWIND $rows AS row
MERGE (n:CityObject {{id: row.id}})
SET n += row.properties
SET n:{label}
"""

UPSERT_EDGE_TEMPLATE = """
MATCH (s:CityObject {{id: $source_id}})
MATCH (t:CityObject {{id: $target_id}})
MERGE (s)-[r:{relation}]->(t)
SET r += $properties
"""

UPSERT_EDGE_BATCH_TEMPLATE = """
UNWIND $rows AS row
MATCH (s:CityObject {{id: row.source_id}})
MATCH (t:CityObject {{id: row.target_id}})
MERGE (s)-[r:{relation}]->(t)
SET r += row.properties
"""
