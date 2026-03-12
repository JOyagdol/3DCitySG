"""Touch relation rules."""

from __future__ import annotations

from citygml_sg.domain.bbox import BBox


def touches(first: BBox | None, second: BBox | None) -> bool:
    if first is None or second is None:
        return False
    return first.touches(second)
