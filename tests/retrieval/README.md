# Retrieval Tests

이 폴더는 room retrieval 관련 테스트를 두는 위치이다.

대상:

1. query generator scenario registry tests.
2. OVG-to-parameter builder tests.
3. graph/signature matching score tests.
4. metric aggregation tests.
5. JSON reporting tests.

현재 주요 구현 경로:

1. `src/citygml_sg/retrieval/query_generator/room_localization.py`
2. `src/citygml_sg/retrieval/scoring/view_params.py`
3. `src/citygml_sg/retrieval/graph_matching/signature_similarity.py`
4. `src/citygml_sg/retrieval/reporting/json_safe.py`
5. `scripts/retrieval/*.py`
