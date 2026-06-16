from pathlib import Path

import pandas as pd

from .index import METADATA_PLATE, METADATA_WELL

# Defaults for the project plate map.
# Join keys against the index's Metadata_Plate/Well, and add annotation columns.
# Override only as a special case if a different plate map is used.
PLATEMAP_PLATE_COL = "Metadata_PlateID"
PLATEMAP_WELL_COL = "Metadata_DestinationWell"
PLATEMAP_COLS = ("Metadata_Compound", "Metadata_Batch")


def load_platemap(path: Path) -> pd.DataFrame:
    """Read a plate-map CSV as all-string, stripping BOM, header, and cell whitespace."""
    df = pd.read_csv(path, skipinitialspace=True, dtype=str, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    return df.apply(lambda col: col.str.strip())


def _merge_keys(plate_col: str | None, well_col: str) -> tuple[list[str], list[str]]:
    """
    Create aligned (index-side, platemap-side) join keys.
    Plate optional, well always included.
    """
    left, right = [], []
    if plate_col:
        left.append(METADATA_PLATE)
        right.append(plate_col)
    left.append(METADATA_WELL)
    right.append(well_col)
    return left, right


def unmatched_wells(
    index: pd.DataFrame,
    platemap: pd.DataFrame,
    plate_col: str | None,
    well_col: str,
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
    well_col: str,
    cols: tuple[str, ...] | None,
) -> pd.DataFrame:
    """
    Left-join of plate-map columns onto the index on the plate/well key(s).

    ``cols`` restricts which plate-map columns are carried into the index (the join keys are
    always included).
    """
    left, right = _merge_keys(plate_col, well_col)
    if cols is not None:
        missing = [c for c in [*right, *cols] if c not in platemap.columns]
        if missing:
            raise KeyError(f"Plate map is missing requested column(s): {', '.join(missing)}")
        platemap = platemap[[*right, *cols]]

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
