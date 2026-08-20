# World Graph Tests

이 폴더는 CityGML-to-world-graph와 RoomSignature/AnchorGraph 관련 테스트를 두는 위치이다.

대상:

1. world graph helper tests.
2. RoomSignature serialization tests.
3. RoomAnchor serialization tests.
4. future precompute/export tests.

기존 import pipeline regression tests는 아직 root `tests/`에 유지한다. 안정적인 helper 분리가 끝난 뒤 domain별로 이동한다.
