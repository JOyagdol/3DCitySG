# 3DCitySG 개발 진행 요약 (한글)

기준 시점: 현재 워크스페이스 최신 코드 상태

## 1. 작업 목표

CityGML 2.0 기반 건물 데이터를 의미-공간 장면 그래프로 변환하고,  
그래프를 JSON/Neo4j로 내보내는 연구용 파이프라인을 안정화하는 것이 목표였다.

## 2. 지금까지 완료한 주요 작업

## 2.1 객체/스키마 반영

다음 객체군을 파이프라인에서 노드로 처리하도록 정리했다.

1. CityObjectMember, CityObjectGroup
2. Building, BuildingPart, Room
3. BuildingInstallation, IntBuildingInstallation
4. BoundarySurface(+ 하위 surface tag), Opening(Door/Window)
5. BuildingFurniture, Address
6. Appearance, SurfaceData
7. Geometry/ImplicitGeometry/Solid/MultiSurface/MultiCurve/Polygon/LinearRing/Position

## 2.2 속성 파싱 강화

다음 속성군을 노드 속성으로 반영하도록 확장했다.

1. `gml:name` (`gml_name`, `gml_name_all`)
2. 공통 메타데이터(`description`, `creationDate`, `relativeToTerrain`)
3. Building 계열 코드/수치 속성(`class`, `function`, `usage`, `roofType`, `measuredHeight`, `storeys*`)
4. `gen:*Attribute` 계열(flattened `attr_*`)

## 2.3 관계 생성 정책 정리

핵심 관계 생성 규칙을 정리/보강했다.

1. 계층 관계: `CONTAINS`, `CONSISTS_OF_BUILDING_PART`, `INTERIOR_ROOM`, `ROOM_INSTALLATION`, `INTERIOR_FURNITURE` 등
2. 경계/개구부 관계: `BOUNDED_BY`, `HAS_OPENING`
3. 주소/외부 관계: `HAS_ADDRESS`
4. Appearance 서브그래프: `HAS_APPEARANCE`, `HAS_SURFACE_DATA`, `APPLIES_TO`
5. LoD/기하 구조 관계: `HAS_LOD_GEOMETRY`, `HAS_GEOMETRY_COMPONENT`, `HAS_GEOMETRY_MEMBER`, `HAS_GEOMETRY`, `HAS_RING`, `HAS_POS`

중복 방지 정책:

1. 특화 관계가 존재하는 경우 동일 parent-child에 `CONTAINS`를 중복 생성하지 않도록 정리
2. 그래프 빌더에서 `(source, relation, target)` 중복 엣지 방지

## 2.4 Appearance owner fallback 보강

`Appearance`가 semantic ancestor 없이 루트 `appearanceMember`에 위치한 경우에도  
`HAS_APPEARANCE`가 생성되도록 fallback owner 로직을 추가했다.

추가로 검증 지표를 보강했다.

1. `summary.appearance_coverage` 출력
2. `owner_resolution`(ancestor/fallback/unresolved) 집계
3. 터미널 리포트에 Appearance Coverage 섹션 추가

## 2.5 Neo4j 적재/운영성 개선

1. 배치 적재(`UNWIND`) 기반 writer 구조 반영
2. 노드/엣지 적재 진행률(퍼센트 바) 출력
3. stage timeline/report 출력 고도화
4. 제약조건/라벨 정책 정리(`CityObject` + 타입 라벨)

## 2.6 평가/리포트 체계 정리

1. Scorecard 기준 반영: `overall = 0.40*node + 0.30*relation + 0.30*property`
2. 공정한 분모 정책(지원 범위 기준 expected 계산) 정리
3. Building-centric 리포트 확장(객체 분포/속성/기하 밀도/stage 상태)
4. `docs/evaluation_scorecard.md` 유지

## 2.7 문서/컨벤션 정리

1. README를 연구 중심 설명 + 실행 가이드 중심으로 정리
2. CityGML 2.0 baseline 명시 및 3.0 확장 여지(config/constants) 정리
3. `INTERSECTS`는 개념상 spatial relation으로 유지하되 현재는 planned(미구현)으로 명시
4. 미구현 스텁 모듈은 `Planned module stub` 상태로 정리하고 문서화(`docs/module_stubs.md`)
5. 회귀 테스트 가이드 문서 추가(`docs/regression_testing.md`)

## 3. 테스트/검증 상태

회귀 테스트 추가 후 실행 결과:

1. `python -m pytest -q`
2. 결과: `3 passed`

회귀 테스트가 검증하는 핵심:

1. global appearance fallback 시 `HAS_APPEARANCE` 생성
2. 특화 관계 존재 시 `CONTAINS` 중복 방지
3. summary 계약(`scorecard`, `appearance_coverage`) 유지

## 4. 현재 남은 핵심 개발 작업

우선순위에서 의도적으로 미룬 항목:

1. 공간관계 추출 로직 구현 (`ADJACENT_TO`, `TOUCHES`, `INTERSECTS`)

그 외는 주로 운영/품질 단계:

1. 대용량 실데이터 반복 검증
2. 커밋 단위 정리 및 릴리즈 노트화

## 5. 관련 문서

1. `README.md`
2. `docs/evaluation_scorecard.md`
3. `docs/regression_testing.md`
4. `docs/module_stubs.md`
5. `docs/graph_schema.md`
6. `docs/relation_definitions.md`
