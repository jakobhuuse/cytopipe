"""Annotation join (plate map → index.csv).

The plate map is a small, messy CSV (BOM, alignment whitespace, unicode). Robustness matters
more than speed here, so we read it with pandas and aggressively strip whitespace. The columns
that annotate a treatment (``pert_name``, ``Split``, …) cannot be derived from CellProfiler
output, so they only appear in ``index.csv`` when a plate map is supplied.
"""

from pathlib import Path

import pandas as pd

# Defaults for the project plate map: join keys against the index's Metadata_Plate/Well, and the
# annotation columns carried into index.csv (DeepProfiler treatment + replicate). Override only
# as a special case if a different plate map is used.
PLATEMAP_PLATE_COL = "Metadata_PlateID"
PLATEMAP_WELL_COL = "Metadata_DestinationWell"
PLATEMAP_COLS = ["Metadata_Compound", "Metadata_Batch"]


def load_platemap(path: Path) -> pd.DataFrame:
    """Read a plate-map CSV as all-string, stripping BOM, header, and cell whitespace."""
    df = pd.read_csv(path, skipinitialspace=True, dtype=str, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    return df.apply(lambda col: col.str.strip())


def _merge_keys(plate_col: str | None, well_col: str | None) -> tuple[list[str], list[str]]:
    left, right = [], []
    if plate_col:
        left.append("Metadata_Plate")
        right.append(plate_col)
    left.append("Metadata_Well")
    right.append(well_col)
    return left, right


def unmatched_wells(
    index: pd.DataFrame,
    platemap: pd.DataFrame,
    plate_col: str | None,
    well_col: str | None,
) -> list[str]:
    """Return the index join-keys (as strings) that have no row in the plate map."""
    left, right = _merge_keys(plate_col, well_col)
    have = set(map(tuple, platemap[right].astype(str).itertuples(index=False, name=None)))
    missing = []
    for keys in index[left].astype(str).itertuples(index=False, name=None):
        if keys not in have:
            missing.append("/".join(keys))
    return sorted(set(missing))


def join_platemap(
    index: pd.DataFrame,
    platemap: pd.DataFrame,
    plate_col: str | None,
    well_col: str | None,
    cols: list[str] | None = None,
) -> pd.DataFrame:
    """Pure left-join of plate-map columns onto the index on the plate/well key(s).

    ``cols`` restricts which plate-map columns are carried into the index (the join keys are
    always included). Defaults to all columns — but plate maps are wide and messy, so callers
    typically pass an explicit subset (e.g. a treatment and a replicate column).
    """
    left, right = _merge_keys(plate_col, well_col)
    if cols is not None:
        missing = [c for c in [*right, *cols] if c not in platemap.columns]
        if missing:
            raise KeyError(f"Plate map is missing requested column(s): {', '.join(missing)}")
        platemap = platemap[[*right, *cols]]

    # Coerce join keys to string on both sides — the index may carry a numeric Metadata_Plate
    # (from CellProfiler's Image table) while the plate map is all-string.
    index = index.copy()
    platemap = platemap.copy()
    for col in left:
        index[col] = index[col].astype(str)
    for col in right:
        platemap[col] = platemap[col].astype(str)

    merged = index.merge(
        platemap,
        how="left",
        left_on=left,
        right_on=right,
        suffixes=("", "_platemap"),
    )
    # Drop redundant right-side key columns that duplicate the index keys.
    drop = [c for c in right if c not in left and c in merged.columns]
    return merged.drop(columns=drop)
