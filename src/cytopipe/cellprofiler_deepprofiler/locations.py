from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

# CellProfiler's per-object location columns, and DeepProfiler's expected names.
SRC_X, SRC_Y = "Location_Center_X", "Location_Center_Y"
DST_X, DST_Y = "Nuclei_Location_Center_X", "Nuclei_Location_Center_Y"

_READ_ONLY_LOCATION_COLS = pacsv.ConvertOptions(include_columns=[SRC_X, SRC_Y])

_WRITE_OPTS = pacsv.WriteOptions(quoting_header="none")


def clean_nuclei_locations(table: pa.Table, as_int: bool = True) -> pa.Table:
    """Keep the two center columns, rename to DeepProfiler names, optionally round to int."""
    x, y = table.column(SRC_X), table.column(SRC_Y)
    if as_int:
        x = pc.cast(pc.round(x), pa.int64())
        y = pc.cast(pc.round(y), pa.int64())
    return pa.table({DST_X: x, DST_Y: y})


def convert_locations_tree(measurement_dir: Path, dest_dir: Path, plate: str) -> int:
    """Convert ``measurement/locations/*-Nuclei.csv`` to DeepProfiler input under
    ``dest/locations/{plate}/``; return the number of files written."""
    src_dir = Path(measurement_dir) / "locations"
    out_dir = Path(dest_dir) / "locations" / plate
    out_dir.mkdir(parents=True, exist_ok=True)

    sources = sorted(src_dir.glob("*-Nuclei.csv"))
    for src in sources:
        table = pacsv.read_csv(src, convert_options=_READ_ONLY_LOCATION_COLS)
        pacsv.write_csv(clean_nuclei_locations(table), out_dir / src.name, _WRITE_OPTS)
    return len(sources)
