# World Graph Domain

이 폴더는 CityGML에서 생성된 semantic-spatial world graph와 retrieval용 anchor/signature 확장을 관리한다.

범위:

1. CityGML parsing과 semantic object extraction.
2. Geometry normalization.
3. Semantic-spatial scene graph construction.
4. Spatial relation inference.
5. Neo4j export.
6. RoomSignature, RoomAnchor, expected-view feature generation.

현재 source-of-truth는 기존 안정 경로를 유지한다:

1. `src/citygml_sg/app/pipeline.py`
2. `src/citygml_sg/world_graph/citygml_to_graph/geometry_subgraph.py`
3. `src/citygml_sg/world_graph/citygml_to_graph/appearance_subgraph.py`
4. `src/citygml_sg/relations/spatial_inference.py`
5. `src/citygml_sg/graph/graph_schema.py`
6. `scripts/run_import.py`
7. `scripts/refresh_latest_reports.py`
8. `scripts/benchmark_queries.py`

Current reusable modules:

1. `src/citygml_sg/world_graph/signatures/room_signature.py`
   - Room별 object/opening/relation/topology count를 담는 `RoomSignature` dataclass.
   - 현재는 interface이며, Neo4j precompute pipeline에는 아직 연결하지 않았다.
2. `src/citygml_sg/world_graph/anchor/room_anchor.py`
   - `RoomSignature`를 retrieval용 stable anchor record로 감싼 `RoomAnchor` dataclass.
   - 향후 AnchorGraph 저장/캐시의 기본 단위이다.
3. `src/citygml_sg/world_graph/citygml_to_graph/geometry_subgraph.py`
   - LoD geometry, concrete geometry component, Polygon, LinearRing, Position 노드와 관련 geometry edge를 생성한다.
   - `pipeline.py`를 import하지 않고 parent-map, ancestor, fallback-id, edge-validation helper를 callback으로 받는다.
4. `src/citygml_sg/world_graph/citygml_to_graph/appearance_subgraph.py`
   - Appearance, SurfaceData, `HAS_APPEARANCE`, `HAS_SURFACE_DATA`, `APPLIES_TO`를 생성한다.
   - global appearance fallback owner 정책과 target reference normalization을 이 모듈이 소유한다.

정리 정책:

1. `app/pipeline.py`의 public import orchestration은 실험 결과가 흔들리지 않도록 유지한다.
2. 새 anchor/signature 코드는 `src/citygml_sg/world_graph/` 아래에 추가한다.
3. 기존 import 명령은 root script를 통해 안정적으로 유지한다.
4. 테스트와 결과가 유지되는 isolated helper부터 단계적으로 이동한다.

다음 구현 대상:

1. Neo4j Room 후보 feature를 즉석 계산하지 않고 `RoomSignature`로 사전 계산하는 query/export 단계 추가.
2. `RoomAnchor` JSON export 또는 Neo4j cache node 정책 결정.
3. Retrieval query가 raw Room graph 대신 RoomSignature/RoomAnchor를 우선 조회하도록 전환.
4. E-type, SmartCityLab의 query latency를 precompute 전/후로 비교한다.
