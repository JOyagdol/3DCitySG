# 3DCitySG 개발 진행 요약

기준일: 2026-03-26

## 1. 현재 기준선

1. 연구 초점: CityGML 기반 의미-공간 Scene Graph
2. 실험 기준 버전: CityGML 2.0
3. v1 핵심 객체:
   - Building
   - BuildingPart
   - Room
   - BoundarySurface
   - Opening(Door/Window)
   - BuildingFurniture

## 2. 완료된 작업

## 2.1 파싱/그래프 구성

1. 핵심 객체군 노드화 및 계층 관계 생성
2. Geometry 하위 구조(Polygon, LinearRing, Position) 연결
3. Appearance/SurfaceData fallback 소유자 연결

## 2.2 공간관계 v1 구현

1. 관계 집합: `INSIDE`, `CONNECTS`, `ADJACENT_TO`, `TOUCHES`, `INTERSECTS`
2. 우선순위/배타: `INTERSECTS > TOUCHES > ADJACENT_TO`
3. 대상 쌍:
   - Furniture <-> BoundarySurface
   - Furniture <-> Door|Window
   - Furniture <-> Furniture
4. 계산 방식: Geometry 좌표 기반 AABB 판정
5. 공간 edge 메타데이터:
   - `method`, `distance`
   - `epsilon_touch`, `epsilon_adjacent`, `epsilon_intersection`
   - `confidence`, `computed_at`

## 2.3 설정/평가/테스트 고도화

1. epsilon 파라미터를 `configs/default.yaml`의 `spatial.*`로 외부화
2. scorecard에 공간 전용 지표 추가:
   - `spatial_coverage`
   - `spatial_precision_sanity`
   - `spatial_pair_stats`
3. 회귀 테스트 강화:
   - positive
   - precedence/배타
   - negative(비접촉/비인접/비교차)

## 2.4 문서화/실행 도구

1. 질의 벤치마크 가이드 문서 추가
2. 기능 구현/검증 가이드 문서 추가
3. 대용량 성능 프로파일링 가이드 문서 추가
4. `scripts/benchmark_queries.py`를 실제 벤치마크 실행기로 구현
5. `scripts/profile_import_runs.py` 추가(반복 import 성능 리포트 생성)

## 3. 부분완료

1. 대용량 성능 프로파일링
   - 실행 스크립트/가이드는 준비 완료
   - 실제 대용량 데이터셋 기준 결과 리포트 축적은 진행 필요

2. 문서 최종 동기화
   - 핵심 문서 대부분 동기화됨
   - 구현 마무리 시 최종 점검 1회 필요

## 4. 미완료

1. 질의 벤치마크 결과 축적
   - 벤치마크 실행기는 구현 완료
   - 데이터셋별 결과 비교 리포트(정확성/성능) 누적 필요

2. 튜닝 전후 성능 비교표 작성
   - `batch_size`, epsilon 조합별 정량 비교표 작성 필요

3. v2 공간관계 확장
   - 방향 관계(좌/우/상/하/전/후)
   - 거리 구간 관계(near/far)
   - 접근성/경로 기반 관계

## 5. 다음 우선순위

1. 실데이터 기준 벤치마크 1차 결과 리포트 작성
2. import profiling 결과(평균/표준편차) 1차 리포트 작성
3. 문서 최종 동기화(README + docs 전체) 마감

## 6. 실행 명령어

프로젝트 루트에서 실행:

```powershell
cd "C:\Users\OKLab\Desktop\AIDT Lab\City Scene Understanding\3DCitySG"
conda activate 3DCitySG
```

import:

```powershell
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json --config configs/default.yaml
```

import + Neo4j:

```powershell
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json --to-neo4j --config configs/default.yaml
```

질의 벤치마크:

```powershell
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
```

성능 프로파일링:

```powershell
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --config configs/default.yaml
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --to-neo4j --config configs/default.yaml
```

회귀 테스트:

```powershell
python -m pytest tests/test_spatial_priority.py -q
python -m pytest tests/test_spatial_relation_pairs.py -q
python -m pytest tests/test_pipeline_regression.py -q
```
