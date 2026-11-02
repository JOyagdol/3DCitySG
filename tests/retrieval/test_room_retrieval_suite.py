"""Room-retrieval suite utility tests."""

from __future__ import annotations

from citygml_sg.retrieval.evaluation import (
    apply_case_variant,
    evaluate_case_rows,
    normalize_recall_k_values,
    summarize_evaluations,
)


def test_apply_case_variant_filters_objects_relations_and_keywords() -> None:
    params = {
        "observed_objects": [
            {"alias": "sofa_1", "category": "sofa"},
            {"alias": "tv_1", "category": "tv"},
            {"alias": "wall_1", "category": "wall_surface"},
        ],
        "observed_relations": [
            ["tv_1", "ABOVE", "sofa_1"],
            ["tv_1", "ADJACENT_TO", "wall_1"],
            ["sofa_1", "ATTACHED_TO", "FloorSurface"],
        ],
        "furniture_keywords": ["sofa", "tv"],
        "installation_keywords": [],
        "installation_target_ids": [],
    }
    case = {
        "variant": {
            "keep_categories": ["tv", "wall_surface"],
        }
    }

    result = apply_case_variant(params, case)

    assert [item["category"] for item in result["observed_objects"]] == ["tv", "wall_surface"]
    assert result["observed_relations"] == [["tv_1", "ADJACENT_TO", "wall_1"]]
    assert result["furniture_keywords"] == ["tv"]


def test_summarize_evaluations_computes_topk_rank_and_mrr() -> None:
    cases = [
        evaluate_case_rows(
            {"case_id": "a", "scenario_id": "combined_room_score", "target_room": "E102", "group": "furnished"},
            [{"room_name": "E102", "total_score": 5.0}],
            top_k=3,
            retrieval_time_ms=10.0,
        ),
        evaluate_case_rows(
            {"case_id": "b", "scenario_id": "combined_room_score", "target_room": "E103", "group": "furnished"},
            [{"room_name": "E102"}, {"room_name": "E103"}],
            top_k=3,
            retrieval_time_ms=20.0,
        ),
        evaluate_case_rows(
            {"case_id": "c", "scenario_id": "opening_boundary_room_score", "target_room": "E204", "group": "sparse"},
            [{"room_name": "E101"}],
            top_k=3,
            retrieval_time_ms=30.0,
        ),
    ]

    summary = summarize_evaluations(cases, top_k=3)

    assert normalize_recall_k_values([1, 5], top_k=3) == (1, 3, 5)
    assert summary["overall"]["case_count"] == 3
    assert summary["overall"]["top1_room_accuracy_pct"] == 33.333
    assert summary["overall"]["top3_room_inclusion_pct"] == 66.667
    assert summary["overall"]["recall_at_1_pct"] == 33.333
    assert summary["overall"]["recall_at_3_pct"] == 66.667
    assert summary["overall"]["recall_at_5_pct"] == 66.667
    assert summary["overall"]["mean_target_room_rank"] == 1.667
    assert summary["overall"]["mrr"] == 0.5
    assert summary["overall"]["retrieval_time_ms_mean"] == 20.0
    assert summary["by_group"]["furnished"]["case_count"] == 2
    assert summary["by_group"]["furnished"]["recall_at_3_pct"] == 100.0
