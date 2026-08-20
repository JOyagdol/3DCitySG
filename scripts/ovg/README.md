# OVG Scripts

이 폴더는 향후 image/perception output을 Observed View Graph JSON으로 정규화하는 CLI를 둘 위치이다.

현재 상태:

1. active script 없음.
2. OVG validation logic은 `src/citygml_sg/ovg/validation/observed_view_graph.py`에 있다.
3. 현재 retrieval 실행은 `scripts/retrieval/room_localization_queries.py --view-graph <json>`을 사용한다.

추가 예정:

1. image model output -> `observed_view_graph.json` 변환 script.
2. OVG schema validation 전용 script.
3. OVG example generation/check script.
