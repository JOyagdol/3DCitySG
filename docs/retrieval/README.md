# Retrieval Domain

이 폴더는 Neo4j world graph 기반 room retrieval 영역을 관리한다.

범위:

1. OVG-to-Cypher query generation.
2. Rule-based query templates.
3. Graph/signature matching.
4. Room candidate scoring and ranking.
5. Retrieval timing and metric evaluation.
6. Evidence report generation.

Canonical scripts:

1. `scripts/retrieval/room_localization_queries.py`
2. `scripts/retrieval/profile_room_localization_stages.py`
3. `scripts/retrieval/evaluate_room_retrieval_metrics.py`

Current reusable modules:

1. `src/citygml_sg/ovg/validation/observed_view_graph.py`
   - `--view-graph` 입력 JSON을 검증하고 query parameter로 변환한다.
   - UTF-8 BOM 입력도 허용한다.
2. `src/citygml_sg/retrieval/query_generator/room_localization.py`
   - room localization Cypher query template과 `SCENARIOS` registry를 관리한다.
   - CLI script와 stage profiler가 이 registry를 공유한다.
3. `src/citygml_sg/retrieval/scoring/view_params.py`
   - room retrieval 기본 parameter와 observed view graph 기반 parameter 조립 로직을 관리한다.
4. `src/citygml_sg/retrieval/reporting/json_safe.py`
   - Neo4j record/result를 JSON report로 쓰기 전에 안전한 dict/list/scalar 형태로 변환한다.
5. `src/citygml_sg/retrieval/graph_matching/signature_similarity.py`
   - OVG feature count와 `RoomSignature` 사이의 normalized overlap score를 계산한다.
   - 현재는 helper 수준이며, query runner에는 아직 연결하지 않았다.

Current script role:

1. `scripts/retrieval/room_localization_queries.py`
   - CLI argument parsing, Neo4j execution, JSON report writing만 담당한다.
2. `scripts/retrieval/profile_room_localization_stages.py`
   - `SCENARIOS` registry를 재사용하고, stage/component timing probe를 수행한다.
3. `scripts/retrieval/sync_room_retrieval_docs.py`
   - raw JSON report에서 `docs/retrieval/raw_json_sync_review_ko.md`를 재생성한다.
4. Retrieval commands use `scripts/retrieval/...` only.

결과 수치 기준:

1. 최신 retrieval 수치의 source-of-truth는 raw JSON report이다.
2. raw JSON 기준 재동기화 검토 문서는 `docs/retrieval/raw_json_sync_review_ko.md`이다.
3. 새 명령어 문서는 `scripts/retrieval/...` 기준으로 작성한다.

완료된 구조 정리:

1. OVG 입력 검증 모듈 분리.
2. Retrieval JSON-safe reporting 모듈 분리.
3. Retrieval parameter builder 분리.
4. Room localization Cypher query/scenario registry 분리.
5. Raw JSON 기반 retrieval 결과 문서 sync script 추가.
6. RoomSignature/RoomAnchor interface와 signature similarity helper 추가.

다음 구현 대상:

1. RoomSignature/AnchorGraph 사전 계산 query/export를 구현한다.
2. Retrieval query runner가 raw Room graph와 precomputed RoomSignature 중 선택할 수 있게 전환한다.
3. CLI script는 실행 orchestration만 담당하도록 유지한다.
