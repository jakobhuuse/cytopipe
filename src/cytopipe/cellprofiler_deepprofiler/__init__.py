"""
``cytopipe cellprofiler-deepprofiler`` — CellProfiler measurement output → DeepProfiler inputs.
"""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .index import build_index, read_image_table, write_index
from .locations import convert_locations_tree
from .platemap import (
    PLATEMAP_COLS,
    PLATEMAP_PLATE_COL,
    PLATEMAP_WELL_COL,
    join_platemap,
    load_platemap,
    unmatched_wells,
)

__all__ = ["bridge", "BridgeResult"]
_IMAGE_TABLE = "Image.csv"


@dataclass
class BridgeResult:
    plate: str
    n_location_files: int
    n_sites: int
    unmatched_wells: list[str] = field(default_factory=list)


def _resolve_measurement(source: Path) -> Path:
    """Accept either a CellProfiler ``measurement/`` dir or a plate dir containing one."""
    if (source / _IMAGE_TABLE).is_file():
        return source
    elif (source / "measurement" / _IMAGE_TABLE).is_file():
        return source / "measurement"
    raise FileNotFoundError(
        f"{source} does not look like a CellProfiler measurement dir "
        f"(no {_IMAGE_TABLE} file here or under 'measurement/')."
    )


def _resolve_image_table(measurement: Path) -> Path:
    """Resolve the image table from measurement path"""
    table = measurement / _IMAGE_TABLE
    if not table.is_file():
        raise FileNotFoundError(
            f"No CellProfiler Image table at {table}. The pipeline's .cppipe must export the "
            f"Image table as {_IMAGE_TABLE} in the measurement dir."
        )
    return table


def _resolve_plate(image_table: pd.DataFrame, measurement: Path) -> str:
    """
    The plate id is the Image table's Metadata_Plate.
    Fall back to the plate dir name if not found.
    """
    if "Metadata_Plate" in image_table:
        plates = image_table["Metadata_Plate"].astype(str).str.strip().unique()
        if len(plates) == 1:
            return plates[0]
        raise ValueError(
            f"Image table spans multiple plates {sorted(plates)}."
            f"Cytopipe takes only one plate at a time."
        )
    return measurement.resolve().parent.name


def bridge(
    source: Path,
    dest: Path,
    platemap: Path,
    *,
    platemap_plate_col: str | None = PLATEMAP_PLATE_COL,
    platemap_well_col: str = PLATEMAP_WELL_COL,
    platemap_cols: tuple[str, ...] | None = PLATEMAP_COLS,
) -> BridgeResult:
    """
    Convert a CellProfiler ``measurement/`` dir to DeepProfiler ``locations/`` + ``index.csv``.
    """
    source, dest = Path(source), Path(dest)
    measurement = _resolve_measurement(source)
    image_table = read_image_table(_resolve_image_table(measurement))
    plate = _resolve_plate(image_table, measurement)

    n_files = convert_locations_tree(measurement, dest, plate)
    index = build_index(image_table, plate)

    pm = load_platemap(platemap)
    missing = unmatched_wells(index, pm, platemap_plate_col, platemap_well_col)
    index = join_platemap(index, pm, platemap_plate_col, platemap_well_col, platemap_cols)

    write_index(index, dest)
    return BridgeResult(
        plate=plate,
        n_location_files=n_files,
        n_sites=len(index),
        unmatched_wells=missing,
    )
