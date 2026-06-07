from __future__ import annotations

from citygml_sg.domain.geometry import Point3D
from citygml_sg.extractors.bbox_extractor import extract_bbox
from citygml_sg.relations.spatial_inference import infer_spatial_relation


def _to_bbox(points: list[Point3D]):
    bbox = extract_bbox(points)
    assert bbox is not None
    return bbox


def test_two_stage_refinement_filters_aabb_intersection_false_positive() -> None:
    first_points = [
        Point3D(0.0, 0.0, 0.0),
        Point3D(2.0, 0.0, 0.0),
        Point3D(0.0, 2.0, 0.0),
        Point3D(0.0, 0.0, 1.0),
        Point3D(2.0, 0.0, 1.0),
        Point3D(0.0, 2.0, 1.0),
    ]
    second_points = [
        Point3D(1.5, 1.5, 0.0),
        Point3D(3.5, 1.5, 0.0),
        Point3D(1.5, 3.5, 0.0),
        Point3D(1.5, 1.5, 1.0),
        Point3D(3.5, 1.5, 1.0),
        Point3D(1.5, 3.5, 1.0),
    ]
    first_bbox = _to_bbox(first_points)
    second_bbox = _to_bbox(second_points)

    raw_relation, _ = infer_spatial_relation(
        first_bbox,
        second_bbox,
        touch_epsilon=0.05,
        adjacent_epsilon=0.50,
        intersection_epsilon=1e-6,
    )
    assert raw_relation is not None
    assert raw_relation.value == "INTERSECTS"

    refined_relation, refined_props = infer_spatial_relation(
        first_bbox,
        second_bbox,
        touch_epsilon=0.05,
        adjacent_epsilon=0.50,
        intersection_epsilon=1e-6,
        first_points=first_points,
        second_points=second_points,
        use_two_stage_refinement=True,
    )
    assert refined_relation is not None
    assert refined_relation.value != "INTERSECTS"
    assert refined_props.get("stage2_refinement") == "obb_polygon_v2"
    assert refined_props.get("stage2_polygon_overlap") is False


def test_two_stage_refinement_keeps_true_intersection() -> None:
    first_points = [
        Point3D(0.0, 0.0, 0.0),
        Point3D(2.0, 0.0, 0.0),
        Point3D(2.0, 2.0, 0.0),
        Point3D(0.0, 2.0, 0.0),
        Point3D(0.0, 0.0, 1.0),
        Point3D(2.0, 0.0, 1.0),
        Point3D(2.0, 2.0, 1.0),
        Point3D(0.0, 2.0, 1.0),
    ]
    second_points = [
        Point3D(1.0, 1.0, 0.0),
        Point3D(3.0, 1.0, 0.0),
        Point3D(3.0, 3.0, 0.0),
        Point3D(1.0, 3.0, 0.0),
        Point3D(1.0, 1.0, 1.0),
        Point3D(3.0, 1.0, 1.0),
        Point3D(3.0, 3.0, 1.0),
        Point3D(1.0, 3.0, 1.0),
    ]
    first_bbox = _to_bbox(first_points)
    second_bbox = _to_bbox(second_points)

    relation, props = infer_spatial_relation(
        first_bbox,
        second_bbox,
        touch_epsilon=0.05,
        adjacent_epsilon=0.50,
        intersection_epsilon=1e-6,
        first_points=first_points,
        second_points=second_points,
        use_two_stage_refinement=True,
    )

    assert relation is not None
    assert relation.value == "INTERSECTS"
    assert props.get("stage2_refinement") == "obb_polygon_v2"
    assert props.get("stage2_obb_overlap") is True
    assert props.get("stage2_polygon_overlap") is True
