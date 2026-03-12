"""CityGML XML reader."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET


def read_citygml(path: str | Path) -> ET.Element:
    tree = ET.parse(Path(path))
    return tree.getroot()
