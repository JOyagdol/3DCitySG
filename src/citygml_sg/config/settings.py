"""Config loading utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from citygml_sg.config import DEFAULT_CITYGML_VERSION, normalize_citygml_version
from citygml_sg.config.schema import Neo4jConfig, PipelineConfig, ProjectConfig


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def load_project_config(path: str | Path) -> ProjectConfig:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    project_raw = _as_dict(raw.get("project"))
    pipeline_raw = _as_dict(raw.get("pipeline"))
    neo4j_raw = _as_dict(raw.get("neo4j"))

    citygml_version = normalize_citygml_version(str(project_raw.get("citygml_version", DEFAULT_CITYGML_VERSION)))

    return ProjectConfig(
        name=str(project_raw.get("name", "citygml-scene-graph")),
        citygml_version=citygml_version,
        pipeline=PipelineConfig(
            input_path=str(pipeline_raw.get("input_path", "data/input")),
            output_path=str(pipeline_raw.get("output_path", "data/output")),
            enable_relations=bool(pipeline_raw.get("enable_relations", True)),
        ),
        neo4j=Neo4jConfig(
            uri=str(neo4j_raw.get("uri", "bolt://localhost:7687")),
            username=str(neo4j_raw.get("username", "neo4j")),
            password=str(neo4j_raw.get("password", "neo4j")),
            database=str(neo4j_raw.get("database", "neo4j")),
            batch_size=int(neo4j_raw.get("batch_size", 5000)),
        ),
    )
