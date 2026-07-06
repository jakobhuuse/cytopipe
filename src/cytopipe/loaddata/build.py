from pathlib import Path

import pandas as pd

from cytopipe.columns import METADATA_PLATE, METADATA_SITE, METADATA_WELL
from cytopipe.io import write_csv

from .scan import CHANNEL_BY_NUMBER


def build_loaddata(
    images: pd.DataFrame,
    plate: str,
    *,
    images_token: str,
    with_illum: bool = False,
    illum_token: str = "__ILLUM__",
) -> pd.DataFrame:
    """Pivot scanned image rows into a CellProfiler LoadData table (one row per image set).

    Emits ``Image_FileName_Orig{X}`` / ``Image_PathName_Orig{X}`` per channel (paths set to the
    ``images_token`` placeholder, sed-substituted to the staged dir at run time). When
    ``with_illum`` is set, also emits ``Image_FileName_Illum{X}`` / ``Image_PathName_Illum{X}``
    for the analysis pipeline's CorrectIlluminationApply. Errors if any image set lacks a channel.
    """
    expected = set(CHANNEL_BY_NUMBER)
    records = []
    for (well, site), group in images.groupby(["Well", "Site"], sort=True):
        present = dict(zip(group["ChannelNumber"], group["FileName"], strict=False))
        missing = expected - set(present)
        if missing:
            channels = ", ".join(f"w{n}" for n in sorted(missing))
            raise ValueError(f"{plate} {well} s{site}: image set is missing channel(s) {channels}.")

        row = {METADATA_PLATE: plate, METADATA_WELL: well, METADATA_SITE: site}
        for number, name in CHANNEL_BY_NUMBER.items():
            row[f"Image_FileName_Orig{name}"] = present[number]
            row[f"Image_PathName_Orig{name}"] = images_token
        if with_illum:
            for name in CHANNEL_BY_NUMBER.values():
                row[f"Image_FileName_Illum{name}"] = f"Illum{name}.npy"
                row[f"Image_PathName_Illum{name}"] = illum_token
        records.append(row)

    return pd.DataFrame.from_records(records)


def write_loaddata(table: pd.DataFrame, out: Path) -> Path:
    """Write the LoadData table to ``out`` (creating parent dirs) and return the path."""
    return write_csv(table, out)
