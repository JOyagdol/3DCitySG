# 기능 구현/검증 가이드 (v1)

기준 버전: CityGML 2.0 baseline  
목적: 벤치마크 문서와 동일한 수준으로, 핵심 기능의 목적/내용/결과/검증 기준을 고정한다.

## 1. 공간 임계값 설정 파라미터 (`spatial.*`)

## 1.1 목적

1. 실험 데이터셋별로 공간관계 민감도(`TOUCHES/ADJACENT_TO/INTERSECTS`)를 조정
2. 코드 변경 없이 설정 파일만 바꿔 재현 가능한 실험 수행

## 1.2 내용

설정 위치: `configs/default.yaml`

```yaml
spatial:
  touch_epsilon: 0.05
  adjacent_epsilon: 0.50
  intersection_epsilon: 0.000001
```

파라미터 의미:

1. `touch_epsilon`: 비교차 상태에서 접촉으로 보는 최대 거리
2. `adjacent_epsilon`: 접촉보다 멀지만 인접으로 보는 최대 거리
3. `intersection_epsilon`: 축 겹침이 이 값보다 커야 `INTERSECTS` 판정

## 1.3 결과

1. import 로그에 실제 로드된 임계값이 출력됨
2. 동일 데이터셋에서 임계값 변경에 따른 관계 분포 변화를 실험 가능

## 1.4 검증 체크

1. 임계값 변경 후 `relation_counts`의 공간관계 분포가 기대대로 변하는지 확인
2. 극단값 테스트:
   - `touch_epsilon`을 매우 작게 했을 때 `TOUCHES` 급감 여부
   - `adjacent_epsilon`을 키웠을 때 `ADJACENT_TO` 증가 여부

---

## 2. 공간 scorecard 진단 지표

## 2.1 목적

1. 전체 `overall` 점수와 별개로 공간관계 품질을 분리 진단
2. 관계 수치만 많은 경우와 품질이 좋은 경우를 구분

## 2.2 내용

`summary.scorecard`에 아래 항목을 포함한다.

1. `spatial_coverage`
   - 후보 pair 대비 실제 추론 edge 비율
2. `spatial_precision_sanity`
   - no-GT sanity 지표
   - metadata 유효성, schema 유효성, precedence 일관성 평균
3. `spatial_pair_stats`
   - pair family별 candidate/inferred/relation 분포

상세 정의는 `docs/evaluation_scorecard.md`를 소스 오브 트루스로 사용한다.

## 2.3 결과

1. scorecard JSON에 공간 진단 필드가 항상 존재
2. 터미널 conversion report에도 요약 출력

## 2.4 검증 체크

1. scorecard 필드 존재 여부 테스트
2. `pair_conflict_count`가 0에 근접하는지 확인
3. 데이터셋 변경 시 pair family 분포가 도메인 직관과 맞는지 확인

---

## 3. 회귀 테스트 (negative 포함)

## 3.1 목적

1. 공간관계 과생성(false positive) 방지
2. 우선순위/배타 규칙 깨짐을 조기 감지

## 3.2 내용

현재 회귀 범위:

1. positive: 문/창문, 경계면, 가구-가구 관계 생성
2. precedence: `INTERSECTS > TOUCHES > ADJACENT_TO`
3. negative:
   - 비접촉
   - 비인접
   - 비교차

## 3.3 결과

1. 관계 누락뿐 아니라 과생성도 검출 가능
2. 임계값/로직 변경 시 회귀 영향 범위를 빠르게 식별 가능

## 3.4 검증 체크

1. `pytest tests/test_spatial_priority.py -q`
2. `pytest tests/test_spatial_relation_pairs.py -q`
3. `pytest tests/test_pipeline_regression.py -q`

---

## 4. 대용량 성능 프로파일링

## 4.1 목적

1. import 파이프라인 병목(파싱/그래프 빌드/Neo4j 적재)을 정량 확인
2. 튜닝 전후를 수치로 비교해 개선 효과를 검증

## 4.2 내용

측정 항목:

1. 단계별 시간(`parse_xml`, `collect_semantics`, `build_nodes`, `build_semantic_edges`, `build_geometry`, `export_neo4j`, `export_json`)
2. 총 시간
3. 적재량(노드/엣지 수)
4. Neo4j 배치 크기(`batch_size`)별 처리량

권장 실험:

1. 동일 입력 파일 기준 `batch_size`를 2k/5k/10k로 비교
2. spatial epsilon 세트별 edge 수와 시간 비교
3. 최소 3회 반복 후 평균/표준편차 기록

## 4.3 결과

1. 튜닝 전후 비교표 작성
2. 병목 단계와 개선 방향을 명시

## 4.4 검증 체크

1. 동일 조건 반복 시 편차 허용 범위 내 유지
2. 튜닝으로 시간 개선 시 결과 정확성(관계 수/scorecard) 유지 확인

---

## 5. 문서 동기화 원칙

기능/정책이 바뀌면 같은 작업 단위에서 아래 문서를 같이 갱신한다.

1. `README.md`
2. `docs/evaluation_scorecard.md`
3. `docs/relation_definitions.md`
4. `docs/graph_schema.md`
5. `docs/regression_testing.md`
6. `docs/development_summary_ko.md`

---

## 6. 실행 명령 모음

아래 명령은 프로젝트 루트(`3DCitySG`)에서 실행한다.

환경 준비:

```powershell
conda activate 3DCitySG
```

import 실행:

```powershell
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json --config configs/default.yaml
```

Neo4j 적재 포함:

```powershell
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json --to-neo4j --config configs/default.yaml
```

공간관계 회귀 테스트:

```powershell
python -m pytest tests/test_spatial_priority.py -q
python -m pytest tests/test_spatial_relation_pairs.py -q
python -m pytest tests/test_pipeline_regression.py -q
```

전체 테스트:

```powershell
python -m pytest -q
```
