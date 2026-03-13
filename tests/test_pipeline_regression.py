from __future__ import annotations

import json
from pathlib import Path

from citygml_sg.app.pipeline import run_import_pipeline


MINIMAL_GML_WITH_GLOBAL_APPEARANCE = """<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel
    xmlns:core="http://www.opengis.net/citygml/2.0"
    xmlns:gml="http://www.opengis.net/gml"
    xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
    xmlns:app="http://www.opengis.net/citygml/appearance/2.0">
  <core:cityObjectMember>
    <bldg:Building gml:id="b1">
      <gml:name>Main Building</gml:name>
      <bldg:consistsOfBuildingPart>
        <bldg:BuildingPart gml:id="bp1"/>
      </bldg:consistsOfBuildingPart>
      <bldg:interiorRoom>
        <bldg:Room gml:id="r1"/>
      </bldg:interiorRoom>
      <bldg:boundedBy>
        <bldg:WallSurface gml:id="ws1">
          <bldg:opening>
            <bldg:Door gml:id="d1"/>
          </bldg:opening>
        </bldg:WallSurface>
      </bldg:boundedBy>
    </bldg:Building>
  </core:cityObjectMember>
  <app:appearanceMember>
    <app:Appearance gml:id="app1">
      <app:surfaceDataMember>
        <app:X3DMaterial gml:id="mat1">
          <app:target>#ws1</app:target>
        </app:X3DMaterial>
      </app:surfaceDataMember>
    </app:Appearance>
  </app:appearanceMember>
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


def test_global_appearance_fallback_creates_has_appearance(tmp_path: Path) -> None:
    payload = _run_pipeline(MINIMAL_GML_WITH_GLOBAL_APPEARANCE, tmp_path)
    summary = payload["summary"]

    assert summary["node_type_counts"]["Appearance"] == 1
    assert summary["relation_counts"]["HAS_APPEARANCE"] >= 1
    assert "appearance_coverage" in summary
    assert summary["appearance_coverage"]["linked_appearance_count"] == 1
    assert summary["appearance_coverage"]["unresolved_appearance_count"] == 0

    appearance_nodes = [node for node in payload["nodes"] if node["type"] == "Appearance"]
    assert len(appearance_nodes) == 1
    assert str(appearance_nodes[0]["properties"].get("owner_resolution", "")).startswith("fallback:")


def test_specialized_relations_do_not_duplicate_contains(tmp_path: Path) -> None:
    payload = _run_pipeline(MINIMAL_GML_WITH_GLOBAL_APPEARANCE, tmp_path)

    edge_set = {(edge["source_id"], edge["relation"], edge["target_id"]) for edge in payload["edges"]}

    assert ("b1", "CONSISTS_OF_BUILDING_PART", "bp1") in edge_set
    assert ("b1", "INTERIOR_ROOM", "r1") in edge_set

    # When a specialized CityGML relation exists, CONTAINS must not be duplicated.
    assert ("b1", "CONTAINS", "bp1") not in edge_set
    assert ("b1", "CONTAINS", "r1") not in edge_set


def test_summary_keeps_scorecard_and_appearance_coverage(tmp_path: Path) -> None:
    payload = _run_pipeline(MINIMAL_GML_WITH_GLOBAL_APPEARANCE, tmp_path)
    summary = payload["summary"]

    assert "scorecard" in summary
    assert summary["scorecard"]["criteria_comment"] == "overall=0.40*node + 0.30*relation + 0.30*property"
    assert "appearance_coverage" in summary
    assert summary["appearance_coverage"]["appearance_node_count"] == 1
