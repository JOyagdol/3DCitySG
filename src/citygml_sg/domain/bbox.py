"""Bounding box utilities."""

from __future__ import annotations

from dataclasses import dataclass

from citygml_sg.domain.geometry import Point3D


@dataclass(slots=True)
class BBox:
    min_point: Point3D
    max_point: Point3D

    def contains(self, other: "BBox") -> bool:
        return (
            self.min_point.x <= other.min_point.x <= other.max_point.x <= self.max_point.x
            and self.min_point.y <= other.min_point.y <= other.max_point.y <= self.max_point.y
            and self.min_point.z <= other.min_point.z <= other.max_point.z <= self.max_point.z
        )

    def touches(self, other: "BBox") -> bool:
        x_overlap = self.max_point.x >= other.min_point.x and other.max_point.x >= self.min_point.x
        y_overlap = self.max_point.y >= other.min_point.y and other.max_point.y >= self.min_point.y
        z_overlap = self.max_point.z >= other.min_point.z and other.max_point.z >= self.min_point.z
        return x_overlap and y_overlap and z_overlap
