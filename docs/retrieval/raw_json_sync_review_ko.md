# Raw JSON 기반 Retrieval 결과 재동기화 검토

기준일: 2026-06-09 raw output 기준

이 문서는 과거 실험 수치 테이블을 raw JSON 결과 파일 기준으로 다시 맞추기 위한 검토 문서이다. 논문/발표 자료에 들어갈 최신 수치는 아래 raw JSON 값을 우선 사용한다.

## 1. Source-of-Truth Raw Files

| 구분 | Raw JSON | 상태 |
|---|---|---|
| E-type kitchen view | `data/output/e_type_kitchen_view_graph_query_report.json` | 최신 OVG 입력 기반 결과 |
| E-type living / TV-sofa view | `data/output/e_type_living_tv_sofa_query_report.json` | 최신 OVG 입력 기반 결과 |
| E-type sparse opening / window view | `data/output/e_type_empty_window_room_query_report.json` | 희소 단서 시나리오 결과 |
| SmartCityLab corridor / column view | `data/output/smartcity_lab_corridor_window_query_report.json` | 희소 공간 + installation 단서 결과 |
| E-type retrieval metrics | `data/output/e_type_room_retrieval_metrics.json` | kitchen/living 2개 case 집계 |

## 2. Raw JSON 기준 최신 후보 결과

| Scenario | Target Room | Rank 1 | Rank 2 | Rank 3 | Target Rank | Retrieval Time |
|---|---|---|---|---|---:|---:|
| E-type kitchen view | E103 | E103 `10.25` | E102 `6.95625` | E201 `1.0` | 1 | 2086.194 ms |
| E-type living / TV-sofa view | E102 | E102 `4.289375` | E201 `1.0` | E204 `1.0` | 1 | 2086.852 ms |
| E-type sparse opening / window view | E204 | E104 `3.6375` | E201 `2.3575` | E204 `2.1075` | 3 | 4033.677 ms |
| SmartCityLab corridor / column view | Room 20 | Room 20 `3.1` | Room 1 `3.1` | Room 4 `3.1` | tie group 1 | raw query time not stored |

해석:

1. Kitchen view와 living / TV-sofa view는 target room이 1위이다.
2. Sparse opening / window view는 문 단서 없이 보면 E204가 3위이다. 따라서 top-1 성공으로 쓰면 안 되고 top-3 inclusion으로 해석해야 한다.
3. SmartCityLab corridor view는 Room 20이 첫 행이지만 Room 1, Room 4, Room 18도 같은 `3.1` 점수이다. 논문 표에서는 “동점 1위 그룹” 또는 “ranking ambiguity”로 표기해야 한다.
4. 기존 문서의 `11.0`, `9.5` 계열 값은 이전 heuristic 결과이며 최신 raw JSON 기준값과 다르다.

## 3. Scenario별 주요 Evidence

| Scenario | 주요 evidence |
|---|---|
| E-type kitchen view | fridge, storage 객체 매칭, door count, floor attachment |
| E-type living / TV-sofa view | sofa, table, TV 객체 매칭, furniture pair relation, floor attachment |
| E-type sparse opening / window view | window count, door count, wall/floor surface count, wall-floor topology |
| SmartCityLab corridor / column view | wall/floor topology, door count, target installation hint |

Kitchen top-1 세부:

| Rank | Room | Score | Matched Objects | Score Breakdown |
|---:|---|---:|---|---|
| 1 | E103 | 10.25 | fridge, storage | object `7.4`, door `1.0`, floor attachment `1.85`, relation `0.0` |
| 2 | E102 | 6.95625 | sofa, table, fridge | object evidence + relation/floor evidence 혼합 |

Living top-1 세부:

| Rank | Room | Score | Matched Objects | Score Breakdown |
|---:|---|---:|---|---|
| 1 | E102 | 4.289375 | sofa, table, TV | object `2.0025`, door `1.0`, furniture relation `1.0`, floor attachment `0.286875` |

Sparse opening/window 세부:

| Rank | Room | Score | Window | Door | Wall-Floor Topology |
|---:|---|---:|---:|---:|---:|
| 1 | E104 | 3.6375 | 1 | 4 | 2 |
| 2 | E201 | 2.3575 | 0 | 6 | 2 |
| 3 | E204 | 2.1075 | 0 | 6 | 1 |

SmartCityLab corridor 세부:

| Rank | Room | Score | Door | Window | Wall-Floor Topology | Target Installation |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Room 20 | 3.1 | 28 | 0 | 18 | 1 |
| 2 | Room 1 | 3.1 | 7 | 0 | 4 | 1 |
| 3 | Room 4 | 3.1 | 6 | 0 | 5 | 1 |
| 4 | Room 18 | 3.1 | 5 | 0 | 4 | 1 |
| 5 | Room 19 | 2.85 | 5 | 0 | 3 | 1 |

## 4. 집계 Metric 기준

`data/output/e_type_room_retrieval_metrics.json`는 현재 E-type kitchen/living 2개 case만 포함한다.

| Metric | Value |
|---|---:|
| Case count | 2 |
| Top-1 Room Accuracy | 100.0% |
| Top-3 Room Inclusion | 100.0% |
| Mean Target Room Rank | 1.0 |
| MRR | 1.0 |
| Mean Retrieval Time | 2086.523 ms |
| Total Retrieval Time | 4173.046 ms |
| Mean Total Elapsed Time | 2094.207 ms |

주의:

1. Sparse opening/window E204 case는 이 metrics JSON에 포함되어 있지 않다.
2. SmartCityLab corridor case도 이 metrics JSON에 포함되어 있지 않다.
3. 전체 논문용 평균을 내기 전에 evaluation case JSON에 sparse/smartcity case를 명시적으로 추가해야 한다.

## 5. 재동기화 필요 문서

아래 문서에는 과거 heuristic 수치 또는 raw JSON과 다른 값이 섞여 있을 수 있다.

| 문서 | 처리 방침 |
|---|---|
| `docs/room_localization_query_results_ko.md` | raw JSON 기준 표로 재생성 필요 |
| `docs/e_type_201dong_dataset_profile_ko.md` | dataset profile은 유지하되 retrieval 결과 표는 raw JSON 기준으로 재생성 필요 |
| `docs/room_localization_query_scenarios.md` | scenario 정의는 유지, 결과값은 최신 raw JSON 값으로 교체 필요 |
| `docs/experiment_results.md` / `docs/experiment_results_ko.md` | 대표 결과 표가 있으면 raw JSON 값으로 동기화 필요 |
| `docs/dataset_result_comparison.md` / `docs/dataset_result_comparison_ko.md` | dataset별 최신 결과만 남기고 이력값은 history 문서로 분리 필요 |

## 6. 운영 방식

1. `scripts/retrieval/sync_room_retrieval_docs.py`로 이 문서를 raw JSON에서 재생성한다.
2. 입력은 `data/output/*query_report.json`와 `data/output/*metrics.json`를 기준으로 한다.
3. 기본 출력은 `docs/retrieval/raw_json_sync_review_ko.md`이다.
4. 과거 수치 전체 테이블은 history/raw archive로 분리하고, 논문용 문서는 최신 raw JSON 기준 표만 유지한다.
5. 새 scenario를 추가하면 sync script의 report 목록 또는 evaluation case JSON도 함께 갱신한다.
