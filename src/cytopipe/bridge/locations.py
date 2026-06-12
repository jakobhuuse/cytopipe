"""CellProfiler nuclei-location CSVs → DeepProfiler ``locations/`` tree.

This is the hot path: hundreds of CSVs per plate, thousands of rows each. We read only the two
columns we need with pyarrow (columnar, fast) and process one file at a time so memory stays
O(one file) regardless of how big the dataset is.
"""

from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

# CellProfiler's per-object location columns → DeepProfiler's expected names.
SRC_X, SRC_Y = "Location_Center_X", "Location_Center_Y"
DST_X, DST_Y = "Nuclei_Location_Center_X", "Nuclei_Location_Center_Y"

_READ_ONLY_LOCATION_COLS = pacsv.ConvertOptions(include_columns=[SRC_X, SRC_Y])

_WRITE_OPTS = pacsv.WriteOptions(quoting_header="none")


def clean_nuclei_locations(table: pa.Table, round_: bool = True) -> pa.Table:
    """Pure transform: keep the two center columns, rename them, optionally round to int.

    Takes/returns an Arrow table (no IO) so it is trivially unit-testable.
    """
    x, y = table.column(SRC_X), table.column(SRC_Y)
    if round_:
        x = pc.cast(pc.round(x), pa.int64())
        y = pc.cast(pc.round(y), pa.int64())
    return pa.table({DST_X: x, DST_Y: y})


def convert_locations_tree(measurement_dir: Path, dest_dir: Path, plate: str) -> int:
    """Walk ``measurement/locations/*-Nuclei.csv`` → ``dest/locations/{plate}/`` one file at a time.

    Owns IO + traversal only; the per-file transform lives in :func:`clean_nuclei_locations`.
    Returns the number of files written. Preserves each source filename (and thus CP's well
    casing) so locations, index.csv, and image paths stay internally consistent.
    """
    src_dir = Path(measurement_dir) / "locations"
    out_dir = Path(dest_dir) / "locations" / plate
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for src in sorted(src_dir.glob("*-Nuclei.csv")):
        table = pacsv.read_csv(src, convert_options=_READ_ONLY_LOCATION_COLS)
        pacsv.write_csv(clean_nuclei_locations(table), out_dir / src.name, _WRITE_OPTS)
        count += 1
    return count
