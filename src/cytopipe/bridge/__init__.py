from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .index import METADATA_PLATE, build_index, read_image_table, write_index
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
_IMAGE_TABLE_DIR = "image_csv"


def _image_table_path(measurement: Path) -> Path | None:
    """The per-chunk ``image_csv/`` dir, a single ``Image.csv``, or None if neither is present."""
    if (measurement / _IMAGE_TABLE_DIR).is_dir():
        return measurement / _IMAGE_TABLE_DIR
    if (measurement / _IMAGE_TABLE).is_file():
        return measurement / _IMAGE_TABLE
    return None


@dataclass
class BridgeResult:
    plate: str
    n_location_files: int
    n_sites: int
    unmatched_wells: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """One-line description of what the bridge produced."""
        return (
            f"plate {self.plate}: {self.n_location_files} location files, "
            f"{self.n_sites} index rows"
        )

    def warning(self) -> str | None:
        """Message if any index keys had no plate-map match, else None."""
        if not self.unmatched_wells:
            return None
        return (
            f"{len(self.unmatched_wells)} index key(s) had no plate-map match: "
            f"{', '.join(self.unmatched_wells)}"
        )


def _resolve_measurement(source: Path) -> Path:
    """Accept either a CellProfiler ``measurement/`` dir or a plate dir containing one."""
    if _image_table_path(source) is not None:
        return source
    elif _image_table_path(source / "measurement") is not None:
        return source / "measurement"
    raise FileNotFoundError(
        f"{source} does not look like a CellProfiler measurement dir "
        f"(no {_IMAGE_TABLE} or {_IMAGE_TABLE_DIR}/ here or under 'measurement/')."
    )


def _resolve_plate(image_table: pd.DataFrame, measurement: Path) -> str:
    """Plate id from the Image table's Metadata_Plate; falls back to the plate dir name."""
    if METADATA_PLATE in image_table:
        plates = image_table[METADATA_PLATE].astype(str).str.strip().unique()
        if len(plates) == 1:
            return plates[0]
        raise ValueError(
            f"Image table spans multiple plates {sorted(plates)}. "
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
    """CellProfiler ``measurement/`` dir → DeepProfiler ``locations/`` + ``index.csv``."""
    source, dest = Path(source), Path(dest)
    measurement = _resolve_measurement(source)
    image_table = read_image_table(_image_table_path(measurement))
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
