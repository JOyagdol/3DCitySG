# Retrieval Scripts

이 폴더는 room retrieval 실험과 측정에 사용하는 canonical CLI script를 관리한다.

Canonical scripts:

1. `room_localization_queries.py`
   - Neo4j world graph에 room-localization scenario query를 실행한다.
   - JSON report를 `data/output/*query_report.json`로 저장한다.
2. `profile_room_localization_stages.py`
   - retrieval query의 coarse stage와 component probe 시간을 측정한다.
   - RoomSignature/AnchorGraph 사전 계산이 필요한 병목을 확인하는 용도이다.
3. `evaluate_room_retrieval_metrics.py`
   - 여러 retrieval report를 읽어 Top-1, Top-3, MRR, 평균 ranking time을 집계한다.
4. `sync_room_retrieval_docs.py`
   - raw JSON report에서 `docs/retrieval/raw_json_sync_review_ko.md`를 재생성한다.

운영 규칙:

1. 새 명령어 문서는 `scripts/retrieval/...` 경로를 기준으로 작성한다.
2. retrieval 명령은 이 폴더만 사용한다.
3. Python/Conda 명령은 사용자가 직접 실행한다.
4. 새 scenario를 추가하면 raw report, evaluation case, 문서 sync 대상도 함께 갱신한다.
