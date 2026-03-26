from __future__ import annotations

import json
from pathlib import Path

from citygml_sg.app.pipeline import run_import_pipeline


MINIMAL_GML_WITH_SPATIAL_PAIRS = """<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel
    xmlns:core="http://www.opengis.net/citygml/2.0"
    xmlns:gml="http://www.opengis.net/gml"
    xmlns:bldg="http://www.opengis.net/citygml/building/2.0">
  <core:cityObjectMember>
    <bldg:Building gml:id="b1">
      <bldg:interiorRoom>
        <bldg:Room gml:id="r1">
          <bldg:boundedBy>
            <bldg:WallSurface gml:id="ws1">
              <gml:Polygon gml:id="p_ws1">
                <gml:exterior>
                  <gml:LinearRing>
                    <gml:posList>0 0 0 5 0 0 5 0 3 0 0 3 0 0 0</gml:posList>
                  </gml:LinearRing>
                </gml:exterior>
              </gml:Polygon>
              <bldg:opening>
                <bldg:Door gml:id="o1">
                  <gml:Polygon gml:id="p_o1">
                    <gml:exterior>
                      <gml:LinearRing>
                        <gml:posList>1 0 0 2 0 0 2 0 2 1 0 2 1 0 0</gml:posList>
                      </gml:LinearRing>
                    </gml:exterior>
                  </gml:Polygon>
                </bldg:Door>
              </bldg:opening>
              <bldg:opening>
                <bldg:Window gml:id="o2">
                  <gml:Polygon gml:id="p_o2">
                    <gml:exterior>
                      <gml:LinearRing>
                        <gml:posList>3.2 0 0 4.2 0 0 4.2 0 1 3.2 0 1 3.2 0 0</gml:posList>
                      </gml:LinearRing>
                    </gml:exterior>
                  </gml:Polygon>
                </bldg:Window>
              </bldg:opening>
            </bldg:WallSurface>
          </bldg:boundedBy>
          <bldg:interiorFurniture>
            <bldg:BuildingFurniture gml:id="f1">
              <gml:Polygon gml:id="p_f1">
                <gml:exterior>
                  <gml:LinearRing>
                    <gml:posList>2 0 0 3 0 0 3 0.6 1 2 0.6 1 2 0 0</gml:posList>
                  </gml:LinearRing>
                </gml:exterior>
              </gml:Polygon>
            </bldg:BuildingFurniture>
          </bldg:interiorFurniture>
          <bldg:interiorFurniture>
            <bldg:BuildingFurniture gml:id="f2">
              <gml:Polygon gml:id="p_f2">
                <gml:exterior>
                  <gml:LinearRing>
                    <gml:posList>3.2 0 0 4.2 0 0 4.2 0.6 1 3.2 0.6 1 3.2 0 0</gml:posList>
                  </gml:LinearRing>
                </gml:exterior>
              </gml:Polygon>
            </bldg:BuildingFurniture>
          </bldg:interiorFurniture>
          <bldg:interiorFurniture>
            <bldg:BuildingFurniture gml:id="f3">
              <gml:Polygon gml:id="p_f3">
                <gml:exterior>
                  <gml:LinearRing>
                    <gml:posList>3 0 0 4 0 0 4 0.6 1 3 0.6 1 3 0 0</gml:posList>
                  </gml:LinearRing>
                </gml:exterior>
              </gml:Polygon>
            </bldg:BuildingFurniture>
          </bldg:interiorFurniture>
        </bldg:Room>
      </bldg:interiorRoom>
    </bldg:Building>
  </core:cityObjectMember>
</core:CityModel>
"""

MINIMAL_GML_WITH_NEGATIVE_SPATIAL = """<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel
    xmlns:core="http://www.opengis.net/citygml/2.0"
    xmlns:gml="http://www.opengis.net/gml"
    xmlns:bldg="http://www.opengis.net/citygml/building/2.0">
  <core:cityObjectMember>
    <bldg:Building gml:id="b_neg">
      <bldg:interiorRoom>
        <bldg:Room gml:id="r_neg">
          <bldg:boundedBy>
            <bldg:WallSurface gml:id="ws_neg">
              <gml:Polygon gml:id="p_ws_neg">
                <gml:exterior>
                  <gml:LinearRing>
                    <gml:posList>0 0 0 10 0 0 10 0 3 0 0 3 0 0 0</gml:posList>
                  </gml:LinearRing>
                </gml:exterior>
              </gml:Polygon>
              <bldg:opening>
                <bldg:Door gml:id="o_neg_door">
                  <gml:Polygon gml:id="p_o_neg_door">
                    <gml:exterior>
                      <gml:LinearRing>
                        <gml:posList>1 0 0 2 0 0 2 0 2 1 0 2 1 0 0</gml:posList>
                      </gml:LinearRing>
                    </gml:exterior>
                  </gml:Polygon>
                </bldg:Door>
              </bldg:opening>
              <bldg:opening>
                <bldg:Window gml:id="o_neg_window">
                  <gml:Polygon gml:id="p_o_neg_window">
                    <gml:exterior>
                      <gml:LinearRing>
                        <gml:posList>2.5 0 1 3.5 0 1 3.5 0 2 2.5 0 2 2.5 0 1</gml:posList>
                      </gml:LinearRing>
                    </gml:exterior>
                  </gml:Polygon>
                </bldg:Window>
              </bldg:opening>
            </bldg:WallSurface>
          </bldg:boundedBy>
          <bldg:interiorFurniture>
            <bldg:BuildingFurniture gml:id="f_near">
              <gml:Polygon gml:id="p_f_near">
                <gml:exterior>
                  <gml:LinearRing>
                    <gml:posList>1 1 0 2 1 0 2 1.6 1 1 1.6 1 1 1 0</gml:posList>
                  </gml:LinearRing>
                </gml:exterior>
              </gml:Polygon>
            </bldg:BuildingFurniture>
          </bldg:interiorFurniture>
          <bldg:interiorFurniture>
            <bldg:BuildingFurniture gml:id="f_far">
              <gml:Polygon gml:id="p_f_far">
                <gml:exterior>
                  <gml:LinearRing>
                    <gml:posList>8 1 0 9 1 0 9 1.6 1 8 1.6 1 8 1 0</gml:posList>
                  </gml:LinearRing>
                </gml:exterior>
              </gml:Polygon>
            </bldg:BuildingFurniture>
          </bldg:interiorFurniture>
        </bldg:Room>
      </bldg:interiorRoom>
    </bldg:Building>
  </core:cityObjectMember>
</core:CityModel>
"""


def _run_pipeline(xml_text: str, tmp_path: Path) -> dict:
    input_path = tmp_path / "input.gml"
    output_path = tmp_path / "output.json"
    input_path.write_text(xml_text, encoding="utf-8")

    rc = run_import_pipeline(str(input_path), str(output_path))
    assert rc == 0
    assert output_path.exists()
    return json.loads(output_path.read_text(encoding="utf-8"))


def _assert_no_inferred_spatial(edge_set: set[tuple[str, str, str]], source_id: str, target_id: str) -> None:
    for relation in ("ADJACENT_TO", "TOUCHES", "INTERSECTS"):
        assert (source_id, relation, target_id) not in edge_set


def test_adds_furniture_to_door_and_window_spatial_relation(tmp_path: Path) -> None:
    payload = _run_pipeline(MINIMAL_GML_WITH_SPATIAL_PAIRS, tmp_path)
    edge_set = {(edge["source_id"], edge["relation"], edge["target_id"]) for edge in payload["edges"]}

    assert ("f1", "TOUCHES", "o1") in edge_set
    assert ("o1", "TOUCHES", "f1") in edge_set
    assert ("f2", "TOUCHES", "o2") in edge_set
    assert ("o2", "TOUCHES", "f2") in edge_set


def test_adds_furniture_to_furniture_spatial_relation(tmp_path: Path) -> None:
    payload = _run_pipeline(MINIMAL_GML_WITH_SPATIAL_PAIRS, tmp_path)
    edge_set = {(edge["source_id"], edge["relation"], edge["target_id"]) for edge in payload["edges"]}

    assert ("f1", "ADJACENT_TO", "f2") in edge_set
    assert ("f2", "ADJACENT_TO", "f1") in edge_set


def test_adds_furniture_to_furniture_touches_relation(tmp_path: Path) -> None:
    payload = _run_pipeline(MINIMAL_GML_WITH_SPATIAL_PAIRS, tmp_path)
    edge_set = {(edge["source_id"], edge["relation"], edge["target_id"]) for edge in payload["edges"]}

    assert ("f1", "TOUCHES", "f3") in edge_set
    assert ("f3", "TOUCHES", "f1") in edge_set


def test_adds_furniture_to_boundary_surface_bidirectional_relation(tmp_path: Path) -> None:
    payload = _run_pipeline(MINIMAL_GML_WITH_SPATIAL_PAIRS, tmp_path)
    edge_set = {(edge["source_id"], edge["relation"], edge["target_id"]) for edge in payload["edges"]}

    assert ("f1", "TOUCHES", "ws1") in edge_set
    assert ("ws1", "TOUCHES", "f1") in edge_set


def test_does_not_add_spatial_relation_for_far_furniture_and_openings(tmp_path: Path) -> None:
    payload = _run_pipeline(MINIMAL_GML_WITH_NEGATIVE_SPATIAL, tmp_path)
    edge_set = {(edge["source_id"], edge["relation"], edge["target_id"]) for edge in payload["edges"]}

    _assert_no_inferred_spatial(edge_set, "f_far", "o_neg_door")
    _assert_no_inferred_spatial(edge_set, "o_neg_door", "f_far")
    _assert_no_inferred_spatial(edge_set, "f_far", "o_neg_window")
    _assert_no_inferred_spatial(edge_set, "o_neg_window", "f_far")


def test_does_not_add_spatial_relation_for_far_furniture_pair(tmp_path: Path) -> None:
    payload = _run_pipeline(MINIMAL_GML_WITH_NEGATIVE_SPATIAL, tmp_path)
    edge_set = {(edge["source_id"], edge["relation"], edge["target_id"]) for edge in payload["edges"]}

    _assert_no_inferred_spatial(edge_set, "f_near", "f_far")
    _assert_no_inferred_spatial(edge_set, "f_far", "f_near")
