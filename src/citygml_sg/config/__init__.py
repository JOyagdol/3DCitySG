"""Project-level configuration constants."""

from __future__ import annotations

CITYGML_VERSION_2_0 = "2.0"
CITYGML_VERSION_3_0 = "3.0"

# Keep this tuple ordered by stable support priority.
SUPPORTED_CITYGML_VERSIONS: tuple[str, ...] = (
    CITYGML_VERSION_2_0,
    CITYGML_VERSION_3_0,
)
DEFAULT_CITYGML_VERSION = CITYGML_VERSION_2_0


def normalize_citygml_version(version: str | None) -> str:
    """Normalize configured CityGML version to a supported value."""

    normalized = (version or "").strip()
    if normalized in SUPPORTED_CITYGML_VERSIONS:
        return normalized
    return DEFAULT_CITYGML_VERSION
