# World Graph Scripts

이 폴더는 향후 WorldGraph/AnchorGraph 전용 CLI를 둘 위치이다.

현재 stable public commands는 root `scripts/`에 유지한다.

1. `scripts/run_import.py`
2. `scripts/refresh_latest_reports.py`
3. `scripts/benchmark_queries.py`
4. `scripts/profile_import_runs.py`
5. `scripts/check_large_scale_baseline.py`

현재 상태:

1. active world_graph 전용 script 없음.
2. `RoomSignature`와 `RoomAnchor` interface는 `src/citygml_sg/world_graph/`에 있다.
3. Neo4j RoomSignature precompute/export는 아직 구현 전이다.

추가 예정:

1. RoomSignature precompute script.
2. RoomAnchor JSON export script.
3. precompute 전/후 retrieval latency 비교 script.
