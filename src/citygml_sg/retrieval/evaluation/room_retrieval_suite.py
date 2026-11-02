"""Room-retrieval suite utilities."""

from __future__ import annotations

from copy import deepcopy
from statistics import mean
from typing import Any

from citygml_sg.retrieval.scoring.view_params import (
    INSTALLATION_VIEW_CATEGORIES,
    NON_FURNITURE_VIEW_CATEGORIES,
)

DEFAULT_RECALL_K_VALUES: tuple[int, ...] = (1, 3, 5)


def _normalize(value: object) -> str:
    return str(value or "").strip().casefold()


def _object_category(item: dict[str, Any]) -> str:
    return _normalize(item.get("category"))


def _object_alias(item: dict[str, Any]) -> str:
    return str(item.get("alias") or item.get("id") or item.get("target_id") or "")


def _as_str_set(values: object) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {_normalize(value) for value in values}


def _filter_relations(relations: list[Any], kept_aliases: set[str]) -> list[Any]:
    if not kept_aliases:
        return []
    filtered: list[Any] = []
    for relation in relations:
        if not isinstance(relation, list) or len(relation) < 3:
            filtered.append(relation)
            continue
        source = str(relation[0])
        target = str(relation[2])
        source_known = source in kept_aliases
        target_known = target in kept_aliases
        target_is_type = target[:1].isupper() or target.endswith("Surface") or target == "Room"
        if source_known and (target_known or target_is_type):
            filtered.append(relation)
    return filtered


def _recompute_keyword_params(params: dict[str, Any], observed_objects: list[dict[str, Any]]) -> None:
    furniture_keywords = sorted(
        {
            str(item["category"])
            for item in observed_objects
            if _object_category(item) not in NON_FURNITURE_VIEW_CATEGORIES
        }
    )
    params["furniture_keywords"] = furniture_keywords

    installation_keywords = sorted(
        {
            str(item["category"])
            for item in observed_objects
            if _object_category(item) in INSTALLATION_VIEW_CATEGORIES
        }
    )
    if installation_keywords:
        params["installation_keywords"] = sorted(
            set(str(item) for item in params.get("installation_keywords", [])) | set(installation_keywords)
        )

    installation_target_ids: set[str] = set()
    for item in observed_objects:
        if _object_category(item) not in INSTALLATION_VIEW_CATEGORIES:
            continue
        for id_field in ("id", "gml_id", "target_id"):
            if item.get(id_field) is not None:
                installation_target_ids.add(str(item[id_field]))
        if isinstance(item.get("target_ids"), list):
            installation_target_ids.update(str(target_id) for target_id in item["target_ids"])
        attributes = item.get("attributes")
        if isinstance(attributes, dict):
            for id_field in ("id", "gml_id", "target_id"):
                if attributes.get(id_field) is not None:
                    installation_target_ids.add(str(attributes[id_field]))
            if isinstance(attributes.get("target_ids"), list):
                installation_target_ids.update(str(target_id) for target_id in attributes["target_ids"])
    params["installation_target_ids"] = sorted(installation_target_ids)


def apply_case_variant(params: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    """Apply object/relation ablation options from a suite case."""
    result = deepcopy(params)
    variant = case.get("variant", {})
    if not isinstance(variant, dict):
        variant = {}

    observed_objects = [
        item for item in result.get("observed_objects", []) if isinstance(item, dict)
    ]
    keep_categories = _as_str_set(variant.get("keep_categories"))
    drop_categories = _as_str_set(variant.get("drop_categories"))
    if keep_categories:
        observed_objects = [item for item in observed_objects if _object_category(item) in keep_categories]
    if drop_categories:
        observed_objects = [item for item in observed_objects if _object_category(item) not in drop_categories]

    max_objects = variant.get("max_objects")
    if isinstance(max_objects, int) and max_objects >= 0:
        observed_objects = observed_objects[:max_objects]

    observed_relations = list(result.get("observed_relations", []))
    if variant.get("include_relations", True) is False:
        observed_relations = []
    else:
        kept_aliases = {_object_alias(item) for item in observed_objects if _object_alias(item)}
        observed_relations = _filter_relations(observed_relations, kept_aliases)
        max_relations = variant.get("max_relations")
        if isinstance(max_relations, int) and max_relations >= 0:
            observed_relations = observed_relations[:max_relations]

    result["observed_objects"] = observed_objects
    result["observed_relations"] = observed_relations
    _recompute_keyword_params(result, observed_objects)

    param_overrides = case.get("param_overrides", {})
    if isinstance(param_overrides, dict):
        result.update(param_overrides)
    return result


def find_target_rank(rows: list[dict[str, Any]], target_room: str) -> int | None:
    target = _normalize(target_room)
    for index, row in enumerate(rows, start=1):
        if _normalize(row.get("room_name")) == target or _normalize(row.get("room_id")) == target:
            return index
    return None


def normalize_recall_k_values(values: list[int] | tuple[int, ...] | None, *, top_k: int) -> tuple[int, ...]:
    """Return sorted positive Recall@K values, always including 1 and top_k."""
    recall_values = set(DEFAULT_RECALL_K_VALUES if values is None else values)
    recall_values.update({1, int(top_k)})
    return tuple(sorted(value for value in recall_values if int(value) >= 1))


def _recall_hits(rank: int | None, recall_k_values: tuple[int, ...]) -> dict[int, bool]:
    return {k: rank is not None and rank <= k for k in recall_k_values}


def evaluate_case_rows(
    case: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    top_k: int,
    retrieval_time_ms: float | None,
    recall_k_values: tuple[int, ...] | list[int] | None = None,
) -> dict[str, Any]:
    target_room = str(case["target_room"])
    rank = find_target_rank(rows, target_room)
    row_count = len(rows)
    penalized_rank = rank if rank is not None else row_count + 1
    reciprocal_rank = 0.0 if rank is None else 1.0 / rank
    top_room = rows[0] if rows else {}
    normalized_recall_k_values = normalize_recall_k_values(recall_k_values, top_k=top_k)
    recall_hits = _recall_hits(rank, normalized_recall_k_values)

    result = {
        "case_id": str(case["case_id"]),
        "group": str(case.get("group", "")),
        "viewpoint": str(case.get("viewpoint", "")),
        "scenario_id": str(case["scenario_id"]),
        "view_graph": str(case.get("view_graph", "")),
        "target_room": target_room,
        "target_rank": rank,
        "target_rank_for_mean": penalized_rank,
        "target_found": rank is not None,
        "top1_correct": rank == 1,
        f"top{top_k}_included": rank is not None and rank <= top_k,
        "recall_at": {str(k): recall_hits[k] for k in normalized_recall_k_values},
        "reciprocal_rank": round(reciprocal_rank, 6),
        "retrieval_time_ms": None if retrieval_time_ms is None else round(float(retrieval_time_ms), 3),
        "row_count": row_count,
        "observed_object_count": int(case.get("observed_object_count", 0)),
        "observed_relation_count": int(case.get("observed_relation_count", 0)),
        "top_room": {
            "room_id": top_room.get("room_id") if isinstance(top_room, dict) else None,
            "room_name": top_room.get("room_name") if isinstance(top_room, dict) else None,
            "total_score": top_room.get("total_score") or top_room.get("score") if isinstance(top_room, dict) else None,
        },
        "rows": rows,
    }
    for k, hit in recall_hits.items():
        result[f"recall_at_{k}"] = hit
    return result


def _average(values: list[Any]) -> float | None:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric:
        return None
    return round(mean(numeric), 3)


def _percentile(values: list[Any], percentile: float) -> float | None:
    numeric = sorted(float(value) for value in values if isinstance(value, (int, float)))
    if not numeric:
        return None
    index = min(len(numeric) - 1, max(0, int(round((len(numeric) - 1) * percentile))))
    return round(numeric[index], 3)


def _item_recall_hit(item: dict[str, Any], k: int) -> bool:
    recall_at = item.get("recall_at")
    if isinstance(recall_at, dict) and str(k) in recall_at:
        return bool(recall_at[str(k)])
    return bool(item.get(f"recall_at_{k}", False))


def _summary_for_items(
    items: list[dict[str, Any]],
    *,
    top_k: int,
    recall_k_values: tuple[int, ...],
) -> dict[str, Any]:
    if not items:
        empty_summary = {
            "case_count": 0,
            "top1_room_accuracy": None,
            f"top{top_k}_room_inclusion": None,
            "mean_target_room_rank": None,
            "mrr": None,
            "retrieval_time_ms_mean": None,
            "retrieval_time_ms_p95": None,
        }
        for k in recall_k_values:
            empty_summary[f"recall_at_{k}"] = None
            empty_summary[f"recall_at_{k}_pct"] = None
        return empty_summary
    case_count = len(items)
    recall_counts = {
        k: sum(1 for item in items if _item_recall_hit(item, k))
        for k in recall_k_values
    }
    top1_count = recall_counts.get(1, sum(1 for item in items if item["top1_correct"]))
    topk_count = recall_counts.get(top_k, sum(1 for item in items if item.get(f"top{top_k}_included")))
    summary = {
        "case_count": case_count,
        "top1_room_accuracy": round(top1_count / case_count, 6),
        "top1_room_accuracy_pct": round((top1_count / case_count) * 100.0, 3),
        f"top{top_k}_room_inclusion": round(topk_count / case_count, 6),
        f"top{top_k}_room_inclusion_pct": round((topk_count / case_count) * 100.0, 3),
        "mean_target_room_rank": round(mean(float(item["target_rank_for_mean"]) for item in items), 3),
        "mrr": round(mean(float(item["reciprocal_rank"]) for item in items), 6),
        "retrieval_time_ms_mean": _average([item["retrieval_time_ms"] for item in items]),
        "retrieval_time_ms_p95": _percentile([item["retrieval_time_ms"] for item in items], 0.95),
        "retrieval_time_ms_max": max(
            [float(item["retrieval_time_ms"]) for item in items if isinstance(item["retrieval_time_ms"], (int, float))],
            default=None,
        ),
    }
    for k, count in recall_counts.items():
        summary[f"recall_at_{k}"] = round(count / case_count, 6)
        summary[f"recall_at_{k}_pct"] = round((count / case_count) * 100.0, 3)
    return summary


def summarize_evaluations(
    evaluated_cases: list[dict[str, Any]],
    *,
    top_k: int,
    recall_k_values: tuple[int, ...] | list[int] | None = None,
) -> dict[str, Any]:
    normalized_recall_k_values = normalize_recall_k_values(recall_k_values, top_k=top_k)
    by_group: dict[str, list[dict[str, Any]]] = {}
    for item in evaluated_cases:
        group = str(item.get("group") or "ungrouped")
        by_group.setdefault(group, []).append(item)
    return {
        "recall_k": list(normalized_recall_k_values),
        "overall": _summary_for_items(
            evaluated_cases,
            top_k=top_k,
            recall_k_values=normalized_recall_k_values,
        ),
        "by_group": {
            group: _summary_for_items(
                items,
                top_k=top_k,
                recall_k_values=normalized_recall_k_values,
            )
            for group, items in sorted(by_group.items())
        },
    }
