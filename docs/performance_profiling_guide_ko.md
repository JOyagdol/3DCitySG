# 대용량 성능 프로파일링 가이드 (v1)

기준: import 파이프라인 성능 측정 / CityGML 2.0 baseline

## 1. 목적

1. 단계별 병목을 정량적으로 파악
2. 튜닝 전후 성능 비교 결과를 재현 가능하게 기록
3. 연구 결과물(논문/보고서)에 근거 데이터 제공

## 2. 실행 도구

스크립트:

- `scripts/profile_import_runs.py`

주요 기능:

1. import를 N회 반복 실행
2. run별 wall time과 `summary.stage_durations` 수집
3. 평균/최솟값/최댓값/표준편차 집계
4. 집계 보고서를 JSON으로 저장

## 3. 실행 예시

Neo4j 비활성(순수 파이프라인):

```bash
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --config configs/default.yaml
```

Neo4j 포함(적재까지 성능 측정):

```bash
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --to-neo4j --config configs/default.yaml
```

출력 경로 기본값:

1. run별 결과: `data/output/profiling/import_run_<n>.json`
2. 집계 리포트: `data/output/import_profile_report.json`

## 4. 수집 지표

## 4.1 run 단위

1. `return_code`
2. `wall_time_seconds`
3. `node_count`, `edge_count`
4. `stage_durations`
   - `parse_xml`
   - `collect_semantics`
   - `build_nodes`
   - `build_semantic_edges`
   - `build_geometry`
   - `export_neo4j`
   - `export_json`
   - `total`

## 4.2 집계

각 지표별:

1. `avg`
2. `min`
3. `max`
4. `std`

## 5. 튜닝 실험 권장 시나리오

1. `neo4j.batch_size`: 2000 / 5000 / 10000 비교
2. `spatial.*` epsilon 세트 변경 전후 비교
3. 동일 입력 파일로 최소 3회 반복 후 평균/표준편차 기록

## 6. 결과 해석 가이드

1. `build_geometry`가 길면:
   - geometry node/edge 생성량, bbox 계산량 점검
2. `export_neo4j`가 길면:
   - batch_size 조정, DB 리소스(메모리/디스크) 점검
3. `std`가 크면:
   - 실행 환경 변동이 큰 상태이므로 반복 횟수 확장 필요

## 7. 산출물 체크리스트

1. 튜닝 전 baseline 리포트
2. 튜닝 후 리포트
3. 개선율(%) 요약 표
4. 정확성 영향(관계 수/scorecard 변동) 점검 결과
