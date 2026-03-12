"""Geometry primitives used across parsing and extraction."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Point3D:
    x: float
    y: float
    z: float


@dataclass(slots=True)
class PolygonMesh:
    vertices: list[Point3D] = field(default_factory=list)
    faces: list[tuple[int, ...]] = field(default_factory=list)
