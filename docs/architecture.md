# Architecture

- `parsers`: load raw CityGML/CityJSON content.
- `extractors`: derive bbox/centroid/semantic features.
- `modules`: object-type specific parsing and mapping.
- `relations`: spatial and indoor relation extraction.
- `graph`: in-memory graph schema and builders.
- `storage`: persistence adapters (Neo4j/JSON/Parquet).
