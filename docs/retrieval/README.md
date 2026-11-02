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
4. `scripts/retrieval/run_room_retrieval_suite.py`

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
6. `src/citygml_sg/retrieval/evaluation/room_retrieval_suite.py`
   - 여러 OVG case의 입력 변형, target-rank 평가, Recall@K/Top-K/MRR/time 집계를 관리한다. 입력 변형의 실제 점수 반영 여부는 아래 한계를 확인한다.

Current script role:

1. `scripts/retrieval/room_localization_queries.py`
   - CLI argument parsing, Neo4j execution, JSON report writing만 담당한다.
2. `scripts/retrieval/profile_room_localization_stages.py`
   - `SCENARIOS` registry를 재사용하고, stage/component timing probe를 수행한다.
3. `scripts/retrieval/sync_room_retrieval_docs.py`
   - raw JSON report에서 로컬 검토 문서 `docs/retrieval/raw_json_sync_review_ko.md`를 재생성한다. 이 생성 문서는 Git에 포함하지 않는다.
4. `scripts/retrieval/run_room_retrieval_suite.py`
   - suite JSON을 읽어 Neo4j room retrieval query를 반복 실행하고 Recall@1/3/5, Top-1/Top-3, MRR/time을 집계한다.
   - 최소 단서, multi-view 변형, 가구 없는 희소 공간, 가구 있는 공간을 같은 평가 구조로 비교한다.
5. Retrieval commands use `scripts/retrieval/...` only.

결과 수치 기준:

1. 최신 retrieval 수치의 source-of-truth는 raw JSON report이다.
2. raw JSON 기준 재동기화 검토 문서 `docs/retrieval/raw_json_sync_review_ko.md`는 선택적으로 생성하는 로컬 문서이며 새 checkout에는 포함되지 않는다.
3. 새 명령어 문서는 `scripts/retrieval/...` 기준으로 작성한다.

완료된 구조 정리:

1. OVG 입력 검증 모듈 분리.
2. Retrieval JSON-safe reporting 모듈 분리.
3. Retrieval parameter builder 분리.
4. Room localization Cypher query/scenario registry 분리.
5. Raw JSON 기반 retrieval 결과 문서 sync script 추가.
6. RoomSignature/RoomAnchor interface와 signature similarity helper 추가.
7. E-type 30-case room retrieval seed suite와 suite runner 추가.

## Current evaluation limitations

현재 30-case suite는 후속 구현을 위한 임시 평가 도구이다. 다음 문제를 해결하고 실제 실행을 검증하기 전에는 유효한 ablation benchmark 또는 확정된 matching 방법의 결과로 해석하지 않는다.

1. `include_relations=false`는 `observed_relations`를 비우지만 현재 점수 query는 이 parameter를 사용하지 않는다. 따라서 `sparse_no_relations`는 관계 제거의 효과를 검증하지 못한다.
2. `combined_room_score`의 door bonus는 `1.0`으로 고정되어 있어 `furnished_kitchen_no_door`의 `door_weight=0`이 문 점수를 제거하지 않는다.
3. `max_objects`는 필터 후 입력 순서대로 자른다. 현재 `sparse_door_window`는 window 두 개를, `minimal_sparse_wall_floor`는 wall 두 개를 선택하므로 case 이름의 door/floor가 실제 입력에 포함되지 않는다.
4. 반환된 rows에서 target을 찾지 못하면 rank 집계에는 `row_count + 1`, reciprocal rank에는 `0`을 사용한다. `LIMIT`으로 잘린 결과에서는 이를 전체 후보군의 실제 rank로 해석할 수 없다.

GitHub 정리 과정에서는 기존 구현을 보존했다. 새로운 matching/score 정의와 Neo4j 실행 결과를 검증한 것은 아니다. 후속 작업에서는 실제 seed 입력과 score breakdown, 전체 ranking을 함께 확인해야 한다.

다음 구현 대상:

1. RoomSignature/AnchorGraph 사전 계산 query/export를 구현한다.
2. Retrieval query runner가 raw Room graph와 precomputed RoomSignature 중 선택할 수 있게 전환한다.
3. CLI script는 실행 orchestration만 담당하도록 유지한다.
