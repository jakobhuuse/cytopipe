from pathlib import Path

import pandas as pd

from cytopipe.columns import METADATA_BATCH, METADATA_COMPOUND, METADATA_PLATE, METADATA_WELL

# Project plate-map defaults: columns to join on (plate/well) and annotations to carry over.
PLATEMAP_PLATE_COL = "Metadata_PlateID"
PLATEMAP_WELL_COL = "Metadata_DestinationWell"
PLATEMAP_COLS = (METADATA_COMPOUND, METADATA_BATCH)


def load_platemap(path: Path) -> pd.DataFrame:
    """Read a plate-map CSV as all-string, stripping BOM, header, and cell whitespace."""
    df = pd.read_csv(path, skipinitialspace=True, dtype=str, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    return df.apply(lambda col: col.str.strip())


def _merge_keys(plate_col: str | None, well_col: str) -> tuple[list[str], list[str]]:
    """Aligned (index-side, platemap-side) join keys. Plate optional, well always included."""
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
    have = set(platemap[right].astype(str).itertuples(index=False, name=None))
    keys = index[left].astype(str).itertuples(index=False, name=None)
    return sorted({"/".join(k) for k in keys if k not in have})


def duplicate_keys(platemap: pd.DataFrame, plate_col: str | None, well_col: str) -> list[str]:
    """Return plate/well keys (as strings) that appear more than once in the plate map."""
    _, right = _merge_keys(plate_col, well_col)
    keys = platemap[right].astype(str)
    dupe_mask = keys.duplicated(keep=False)
    if not dupe_mask.any():
        return []
    return sorted({"/".join(row) for row in keys[dupe_mask].itertuples(index=False, name=None)})


def join_platemap(
    index: pd.DataFrame,
    platemap: pd.DataFrame,
    plate_col: str | None,
    well_col: str,
    cols: tuple[str, ...] | None,
) -> pd.DataFrame:
    """Left-join plate-map onto the index by plate/well key(s) (join keys always kept).

    Raises if the plate map has more than one row for the same plate/well key: a left-join
    would silently fan out every matching index row (e.g. every imaging site in that well)
    once per duplicate, which is never wanted and usually means the plate map itself has a
    data-entry error.
    """
    left, right = _merge_keys(plate_col, well_col)
    dupes = duplicate_keys(platemap, plate_col, well_col)
    if dupes:
        raise ValueError(
            f"Plate map has more than one row for key(s): {', '.join(dupes)}. "
            "A left-join would silently duplicate every matching index row per extra "
            "match; fix the plate map so each plate/well key appears once."
        )
    if cols is not None:
        missing = [c for c in [*right, *cols] if c not in platemap.columns]
        if missing:
            raise KeyError(f"Plate map is missing requested column(s): {', '.join(missing)}")
        platemap = platemap[[*right, *cols]]

    # astype with a column→dtype map returns a fresh frame, so callers are left untouched.
    index = index.astype({col: str for col in left})
    platemap = platemap.astype({col: str for col in right})

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
