"""Locate and identify the CellProfiler measurement source for a bridge run."""

from pathlib import Path

import pandas as pd

from cytopipe.columns import METADATA_PLATE

_IMAGE_TABLE = "Image.csv"
_IMAGE_TABLE_DIR = "image_csv"


def image_table_path(measurement: Path) -> Path | None:
    """The per-chunk image table directory, or a single image table file"""
    if (measurement / _IMAGE_TABLE_DIR).is_dir():
        return measurement / _IMAGE_TABLE_DIR
    if (measurement / _IMAGE_TABLE).is_file():
        return measurement / _IMAGE_TABLE
    return None


def resolve_measurement(source: Path) -> Path:
    """Accept either a CellProfiler ``measurement/`` dir or a plate dir containing one."""
    if image_table_path(source) is not None:
        return source
    if image_table_path(source / "measurement") is not None:
        return source / "measurement"
    raise FileNotFoundError(
        f"{source} does not look like a CellProfiler measurement dir "
        f"(no {_IMAGE_TABLE} or {_IMAGE_TABLE_DIR}/ here or under 'measurement/')."
    )


def resolve_plate(image_table: pd.DataFrame, measurement: Path) -> str:
    """Plate id from the Image table's Metadata_Plate. Falls back to the plate dir name."""
    if METADATA_PLATE in image_table:
        plates = image_table[METADATA_PLATE].astype(str).str.strip().unique()
        if len(plates) == 1:
            return plates[0]
        raise ValueError(
            f"Image table spans multiple plates {sorted(plates)}. "
            f"Cytopipe takes only one plate at a time."
        )
    return measurement.resolve().parent.name
