"""Simple service container for dependency wiring."""

from __future__ import annotations

from dataclasses import dataclass

from citygml_sg.config.schema import ProjectConfig


@dataclass(slots=True)
class ServiceContainer:
    config: ProjectConfig
