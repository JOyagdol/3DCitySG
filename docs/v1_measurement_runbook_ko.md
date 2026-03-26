# v1 실측 결과 생성 가이드

이 문서는 v1 상태에서 벤치마크/프로파일링 실측 결과를 재현 가능하게 생성하기 위한 실행 절차를 정의한다.

## 1. 목적

1. 질의 벤치마크 결과(`benchmark_report.json`) 생성
2. import 성능 프로파일링 결과(`import_profile_report.json`) 생성
3. 결과 기록 문서(`docs/experiment_results_ko.md`)에 반영할 입력값 확보

## 2. 사전 조건

1. 프로젝트 루트 경로:
   - `C:\Users\OKLab\Desktop\AIDT Lab\City Scene Understanding\3DCitySG`
2. Conda 환경:
   - `3DCitySG`
3. Neo4j:
   - 로컬 실행 중
   - `configs/default.yaml`의 접속 정보와 일치

## 3. 실행 명령

```powershell
cd "C:\Users\OKLab\Desktop\AIDT Lab\City Scene Understanding\3DCitySG"
conda activate 3DCitySG
```

### 3.1 import + Neo4j 적재 (기준 1회)

```powershell
python scripts/run_import.py --input "data/input/fzk_haus_lod2_v2.gml" --output data/output/my_import.json --to-neo4j --config configs/default.yaml
```

### 3.2 질의 벤치마크 결과 생성

```powershell
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
```

### 3.3 import 성능 프로파일링 결과 생성

```powershell
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --config configs/default.yaml
```

Neo4j 포함 성능 측정이 필요하면:

```powershell
python scripts/profile_import_runs.py --input "data/input/fzk_haus_lod2_v2.gml" --runs 3 --to-neo4j --config configs/default.yaml
```

## 4. 생성 산출물

1. import 결과:
   - `data/output/my_import.json`
2. 질의 벤치마크:
   - `data/output/benchmark_report.json`
3. 프로파일링:
   - run별 파일: `data/output/profiling/import_run_<n>.json`
   - 집계 리포트: `data/output/import_profile_report.json`

## 5. 완료 체크리스트

1. import 로그에 `Import complete` 확인
2. `benchmark_report.json`에 `summary.query_failed = 0` 확인
3. `import_profile_report.json`에 `summary.runs_failed = 0` 확인
4. 생성된 수치를 `docs/experiment_results_ko.md`에 기록

## 6. 고정 실행 예시 (2026-03-26, E-TYPE_201dong)

아래는 실제 실행한 기준선(baseline) 기록이다. 이후 재실행 시 이 값과 비교한다.

### 6.1 실행 명령

```powershell
python -m pytest -q
python -m pytest tests/test_spatial_relation_pairs.py -q
python scripts/run_import.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --output data/output/E-TYPE_201dong.json --to-neo4j --config configs/default.yaml
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
python scripts/profile_import_runs.py --input "data/input/(210812)E-TYPE_201dong-IFC4.gml" --runs 3 --config configs/default.yaml
```

### 6.2 핵심 결과 스냅샷

1. 테스트:
   - `python -m pytest -q` -> `13 passed`
   - `python -m pytest tests/test_spatial_relation_pairs.py -q` -> `6 passed`
2. Import (`--to-neo4j`):
   - nodes=`1,076,195`, edges=`1,240,071`
   - scorecard overall=`97.97`
   - spatial coverage=`57.14 (8/14)`
   - spatial precision-like sanity=`100.00`
   - total runtime=`306.559s`
3. Benchmark (`benchmark_report.json`):
   - Q1 avg=`10.629ms`, Q2 avg=`5.744ms`, Q3 avg=`5.441ms`, Q4 avg=`7.424ms`, Q5 avg=`5.775ms`
   - result_count는 Q1~Q5 모두 `0`
   - `CONNECTS` 관계 타입 미존재 경고 발생(Q4, Q5 관련)
4. Profiling (`import_profile_report.json`, `--to-neo4j` 미사용):
   - wall time avg=`153.028553s` (min=`149.791812s`, max=`156.003975s`, std=`2.542828s`)
   - stage avg: `parse_xml=5.753844s`, `collect_semantics=1.135243s`,
     `build_nodes=0.007367s`, `build_semantic_edges=0.455520s`,
     `build_geometry=23.289802s`, `export_json=53.351159s`, `total=96.247233s`
