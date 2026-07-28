"""Drop excluded image sets from an already-built LoadData table."""

import pandas as pd

from cytopipe.columns import METADATA_PLATE, METADATA_SITE, METADATA_WELL


def filter_loaddata(table: pd.DataFrame, excluded: pd.DataFrame) -> pd.DataFrame:
    """Drop rows of ``table`` matching a (Plate, Well, Site) triple in ``excluded``.

    ``excluded`` carries the same three Metadata_* columns as a QC exclusion list. An empty
    ``excluded`` is a no-op passthrough.
    """
    if excluded.empty:
        return table.reset_index(drop=True)

    keys = [METADATA_PLATE, METADATA_WELL, METADATA_SITE]
    merged = table.merge(excluded[keys].drop_duplicates(), on=keys, how="left", indicator=True)
    kept = merged[merged["_merge"] == "left_only"].drop(columns="_merge")
    return kept.reset_index(drop=True)
