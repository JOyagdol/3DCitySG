# 질의 벤치마크 가이드 (v1)

기준: CityGML 2.0 / 공간관계 v1 (`INSIDE`, `CONNECTS`, `ADJACENT_TO`, `TOUCHES`, `INTERSECTS`)

## 1. 목적

1. 그래프가 실제 공간 질의에 대해 해석 가능한지 검증
2. 파이프라인 변경 후 결과 회귀를 조기에 감지
3. 질의 정확성/일관성/성능을 재현 가능하게 기록
4. 논문/보고서용 정량 결과를 축적

## 2. 벤치마크 질의 세트 (권장)

## 2.1 충돌 질의

1. `INTERSECTS`인 가구-가구 쌍 조회
2. `INTERSECTS`인 가구-문/창문 쌍 조회

## 2.2 접촉 질의

1. `TOUCHES`인 가구-경계면 조회
2. `TOUCHES`인 가구-문/창문 조회

## 2.3 인접 질의

1. `ADJACENT_TO`인 가구-가구 조회
2. `ADJACENT_TO`인 가구-경계면 조회

## 2.4 연결 질의

1. 특정 room과 `CONNECTS`된 opening 목록
2. opening 종류별(door/window) 연결 분포

## 2.5 복합 질의

1. 특정 room 내부(`INSIDE`)이면서 문/창문과 접촉(`TOUCHES`)인 가구
2. 특정 room 내부 가구 중 인접(`ADJACENT_TO`) 관계가 많은 객체 상위 N개

## 3. 실행 및 측정 원칙

1. 동일 데이터셋, 동일 DB 상태에서 반복 측정
2. 질의당 최소 3회 이상 실행 후 평균/최솟값 기록
3. warm-up 1회 실행 후 본 측정 시작
4. 결과 건수와 실행 시간(ms)을 함께 기록
5. 예외/빈 결과도 실패가 아니라 상태로 기록

실행 명령:

```bash
python scripts/benchmark_queries.py --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
```

또는

```bash
python -m citygml_sg.app.cli benchmark --config configs/default.yaml --output data/output/benchmark_report.json --warmup 1 --repeat 3
```

## 4. 결과 기록 템플릿

아래 표 형태로 실험 로그를 남긴다.

| Query ID | 목적 | Cypher 요약 | Result Count | Avg Time (ms) | P95 (ms) | 비고 |
|---|---|---|---:|---:|---:|---|
| Q1 | 충돌(가구-가구) | `MATCH ... INTERSECTS ...` | 0 | 0.0 | 0.0 | |
| Q2 | 접촉(가구-문/창문) | `MATCH ... TOUCHES ...` | 0 | 0.0 | 0.0 | |

기본 산출 파일:

- `data/output/benchmark_report.json`

JSON에는 `summary`와 `queries`가 포함되며, query별로 `result_count`, `avg_ms`, `min_ms`, `max_ms`, `std_ms`를 기록한다.

## 5. 해석 기준

1. 정확성 측면
   - 도메인 기대치와 정성 비교
   - 비정상 급증/급감 시 파싱/관계 생성 로직 점검
2. 일관성 측면
   - 동일 데이터셋 재실행 시 결과 편차 최소화
3. 성능 측면
   - 질의별 시간 추세 비교
   - 인덱스/라벨 전략 변경 전후 비교

## 6. 산출물

1. 실행 로그 원본 (CLI 출력 또는 CSV)
2. 질의 결과 요약표
3. 핵심 질의 샘플 결과 ID
4. 튜닝 전후 비교 메모
