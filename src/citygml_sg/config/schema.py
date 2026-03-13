"""Configuration schemas."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Neo4jConfig:
    uri: str
    username: str
    password: str
    database: str = "neo4j"
    batch_size: int = 5000


@dataclass(slots=True)
class PipelineConfig:
    input_path: str = "data/input"
    output_path: str = "data/output"
    enable_relations: bool = True


@dataclass(slots=True)
class ProjectConfig:
    name: str = "citygml-scene-graph"
    citygml_version: str = "2.0"
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    neo4j: Neo4jConfig = field(
        default_factory=lambda: Neo4jConfig(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="neo4j",
            database="neo4j",
        )
    )
