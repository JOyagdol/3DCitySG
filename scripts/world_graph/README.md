# World Graph Scripts

이 폴더는 향후 WorldGraph/AnchorGraph 전용 CLI를 둘 위치이다.

현재 stable public commands는 root `scripts/`에 유지한다.

1. `scripts/run_import.py`
2. `scripts/refresh_latest_reports.py`
3. `scripts/benchmark_queries.py`
4. `scripts/profile_import_runs.py`
5. `scripts/check_large_scale_baseline.py`

현재 상태:

1. `build_etype_room_dashboard_data.py`
   - E-TYPE graph JSON에서 Room polygon face, Furniture XY convex hull outline, Building bbox data를 추출해 로컬 dashboard data를 생성한다.
   - 실행 후 `web/etype_room_dashboard/`를 localhost로 serve해서 3D view에서 room name/GML ID를 확인한다.
2. `RoomSignature`와 `RoomAnchor` interface는 `src/citygml_sg/world_graph/`에 있다.
3. Neo4j RoomSignature precompute/export는 아직 구현 전이다.

E-TYPE room dashboard:

```powershell
python scripts/world_graph/build_etype_room_dashboard_data.py --input data/output/e_type_import.json --output web/etype_room_dashboard/etype_room_dashboard_data.json
```

```powershell
python -m http.server 8765 --directory web/etype_room_dashboard
```

추가 예정:

1. RoomSignature precompute script.
2. RoomAnchor JSON export script.
3. precompute 전/후 retrieval latency 비교 script.
