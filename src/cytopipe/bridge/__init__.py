"""``cytopipe bridge`` — CellProfiler measurement output → DeepProfiler inputs.

Stateless, deterministic, idempotent: a pure function of ``source`` and the plate map.
:func:`run_bridge` is a thin orchestrator — every transform lives in its own module
(:mod:`.locations`, :mod:`.index`, :mod:`.platemap`).
"""

from __future__ import annotations

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

__all__ = ["run_bridge", "BridgeResult"]


@dataclass
class BridgeResult:
    plate: str
    n_location_files: int
    n_sites: int
    unmatched_wells: list[str] = field(default_factory=list)


def _resolve_measurement(source: Path) -> Path:
    """Accept either a CellProfiler ``measurement/`` dir or a plate dir containing one."""
    if (source / "locations").is_dir():
        return source
    if (source / "measurement" / "locations").is_dir():
        return source / "measurement"
    raise FileNotFoundError(
        f"{source} does not look like a CellProfiler measurement dir "
        f"(no 'locations/' here or under 'measurement/')."
    )


_IMAGE_TABLE = "image.csv"


def _resolve_image_table(measurement: Path) -> Path:
    table = measurement / _IMAGE_TABLE
    if not table.is_file():
        raise FileNotFoundError(
            f"No CellProfiler Image table at {table}. The pipeline's .cppipe must export the "
            f"Image table as {_IMAGE_TABLE} in the measurement dir."
        )
    return table


def _infer_plate(image_table: pd.DataFrame, measurement: Path) -> str:
    """The plate id is the Image table's Metadata_Plate; fall back to the plate dir name."""
    if "Metadata_Plate" in image_table:
        plates = image_table["Metadata_Plate"].astype(str).str.strip().unique()
        if len(plates) == 1:
            return plates[0]
    return measurement.resolve().parent.name


def run_bridge(source: Path, dest: Path, platemap: Path) -> BridgeResult:
    """Convert a CellProfiler ``measurement/`` dir to DeepProfiler ``locations/`` + ``index.csv``.

    Everything else is derived from the standard pipeline output layout (``image.csv``,
    ``locations/``); the plate map supplies the treatment/replicate annotations DeepProfiler
    requires, so it is mandatory.
    """
    source, dest = Path(source), Path(dest)
    measurement = _resolve_measurement(source)
    image_table = read_image_table(_resolve_image_table(measurement))
    plate = _infer_plate(image_table, measurement)

    n_files = convert_locations_tree(measurement, dest, plate)
    index = build_index(image_table, plate)

    pm = load_platemap(platemap)
    missing = unmatched_wells(index, pm, PLATEMAP_PLATE_COL, PLATEMAP_WELL_COL)
    index = join_platemap(index, pm, PLATEMAP_PLATE_COL, PLATEMAP_WELL_COL, PLATEMAP_COLS)

    write_index(index, dest)
    return BridgeResult(
        plate=plate,
        n_location_files=n_files,
        n_sites=len(index),
        unmatched_wells=missing,
    )
