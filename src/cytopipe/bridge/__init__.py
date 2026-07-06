"""Module for bridging CellProfiler output to DeepProfiler input."""

from dataclasses import dataclass, field
from pathlib import Path

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
from .source import image_table_path, resolve_measurement, resolve_plate

__all__ = ["bridge", "BridgeResult"]


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


def bridge(
    source: Path,
    dest: Path,
    platemap: Path,
    *,
    platemap_plate_col: str | None = PLATEMAP_PLATE_COL,
    platemap_well_col: str = PLATEMAP_WELL_COL,
    platemap_cols: tuple[str, ...] | None = PLATEMAP_COLS,
) -> BridgeResult:
    source, dest = Path(source), Path(dest)
    measurement = resolve_measurement(source)
    image_table = read_image_table(image_table_path(measurement))
    plate = resolve_plate(image_table, measurement)

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
