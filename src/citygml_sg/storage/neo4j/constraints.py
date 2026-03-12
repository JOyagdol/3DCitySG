"""Neo4j schema constraints and indexes."""

CONSTRAINTS = [
    "CREATE CONSTRAINT city_object_id IF NOT EXISTS FOR (n:CityObject) REQUIRE n.id IS UNIQUE",
]
