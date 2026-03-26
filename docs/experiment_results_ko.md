# v1 실험 결과 기록

이 문서는 v1 기준 실측 결과를 기록하는 최종 문서다.

## 1. 실험 메타

1. 실험 일시: 2026-03-26
2. 실행자: OKLab
3. Git commit: `84e37e2`
4. 데이터셋: `data/input/(210812)E-TYPE_201dong-IFC4.gml`
5. Neo4j 버전/DB: Local Neo4j (version 미기록) / `neo4j`
6. 설정 파일: `configs/default.yaml`

## 2. 실행 명령 기록

```powershell
# import + neo4j
python scripts/run_import.py --input "<input.gml>" --output "<output.json>" --to-neo4j --config configs/default.yaml

# benchmark
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3

# profiling
python scripts/profile_import_runs.py --input "<input.gml>" --runs 3 --config configs/default.yaml
```

## 3. import 결과 요약

| 항목 | 값 |
|---|---|
| node_count | 1,076,195 |
| edge_count | 1,240,071 |
| scorecard.overall_score | 97.97 |
| scorecard.spatial_coverage.score | 57.14 (8/14) |
| scorecard.spatial_precision_sanity.score | 100.00 (inferred=8, metadata_valid=8, schema_valid=8, pair_conflicts=0) |
| import total runtime | 306.559s (`--to-neo4j` 실행 기준) |

## 4. 질의 벤치마크 결과

출처: `data/output/benchmark_report.json`

| Query ID | Query Name | Result Count | Avg(ms) | Min(ms) | Max(ms) | Std(ms) | 비고 |
|---|---|---:|---:|---:|---:|---:|---|
| Q1 | furniture_furniture_intersects_pairs | 0 | 10.629 | 8.878 | 11.645 | 1.243 | 현재 데이터셋에서 해당 쌍 미검출 |
| Q2 | furniture_opening_touches | 0 | 5.744 | 4.750 | 6.800 | 0.838 | 현재 데이터셋에서 해당 쌍 미검출 |
| Q3 | furniture_boundary_adjacent | 0 | 5.441 | 4.113 | 6.869 | 1.127 | 현재 데이터셋에서 해당 쌍 미검출 |
| Q4 | opening_room_connects | 0 | 7.424 | 6.305 | 8.317 | 0.837 | `CONNECTS` 관계 타입 미생성 경고(Neo4j notification) |
| Q5 | room_internal_furniture_touching_opening | 0 | 5.775 | 5.237 | 6.130 | 0.387 | `CONNECTS` 미생성으로 조인 경로 부재 |

## 5. import 프로파일링 결과

출처: `data/output/import_profile_report.json`

### 5.1 전체 요약

| 항목 | Avg | Min | Max | Std |
|---|---:|---:|---:|---:|
| wall_time_seconds | 153.028553 | 149.791812 | 156.003975 | 2.542828 |
| node_count | 1076195.0 | 1076195.0 | 1076195.0 | 0.0 |
| edge_count | 1240071.0 | 1240071.0 | 1240071.0 | 0.0 |

### 5.2 stage별 시간

| Stage | Avg(s) | Min(s) | Max(s) | Std(s) |
|---|---:|---:|---:|---:|
| parse_xml | 5.753844 | 5.142485 | 6.840876 | 0.770641 |
| collect_semantics | 1.135243 | 1.069884 | 1.208718 | 0.056969 |
| build_nodes | 0.007367 | 0.006687 | 0.008230 | 0.000643 |
| build_semantic_edges | 0.455520 | 0.418494 | 0.497008 | 0.032208 |
| build_geometry | 23.289802 | 22.494518 | 24.832995 | 1.091374 |
| export_neo4j | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| export_json | 53.351159 | 51.160102 | 54.894664 | 1.591903 |
| total | 96.247233 | 92.040884 | 99.054131 | 3.029329 |

## 6. 분석 메모

1. 병목 단계:
   - `--to-neo4j` 실행에서는 `export_neo4j`(약 207s)와 `export_json`(약 58s)이 지배적.
   - profiling(`--to-neo4j` 비활성)에서는 `export_json`(약 53s)과 `build_geometry`(약 23s)가 주요 병목.
2. 튜닝 전/후 비교:
   - 동일 설정 3회 반복 시 wall time std 약 2.54s로 변동성은 제한적.
   - Neo4j export 포함/미포함 차이가 매우 큼(대략 +200s 수준).
3. 정확성 영향 여부(관계 수/scorecard 변동):
   - 3회 반복에서 node/edge/overall score(97.97) 동일.
   - Spatial coverage는 57.14(8/14)로 유지, precision-like sanity는 100.00 유지.
4. 다음 액션:
   - `CONNECTS` 관계 생성 로직/조건을 구현 또는 벤치마크 질의를 현재 스키마와 정합되게 조정.
   - 후보 쌍이 0인 `furniture_boundary_surface`, `furniture_opening` 케이스 데이터셋 확장 후 재측정.
