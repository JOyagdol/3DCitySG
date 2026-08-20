# OVG Domain

OVG는 image/perception output을 retrieval에 사용할 수 있는 `observed_view_graph.json` 형식으로 정규화하는 영역이다.

## Scope

1. Observed View Graph JSON schema 관리.
2. OVG example JSON 관리.
3. OVG JSON validation.
4. future image model adapter 위치 제공.
5. Retrieval 전에 object/relation/constraint/query 필드를 안정적으로 정규화.

## Source-of-Truth

1. `docs/schemas/observed_view_graph.schema.json`
2. `docs/examples/observed_view_graph_*.json`
3. `src/citygml_sg/ovg/validation/observed_view_graph.py`

## Current Code

1. UTF-8 BOM 포함 JSON을 `utf-8-sig`로 읽는다.
2. `objects`, `relations`, `constraints`, `query` 필드를 검증한다.
3. object `weight`, `confidence`, `visibility`를 numeric 값으로 정규화한다.
4. `id`, `gml_id`, `target_id`, `target_ids`, `attributes`를 retrieval query parameter로 전달할 수 있게 보존한다.

## Policy

1. image-recognition logic은 world graph construction code와 섞지 않는다.
2. OVG schema/example 변경 시 retrieval 문서와 query scenario 문서도 함께 갱신한다.
3. 실제 image-to-graph adapter는 `src/citygml_sg/ovg/adapters/`에 둔다.
4. active CLI가 생기면 `scripts/ovg/`에 둔다.
