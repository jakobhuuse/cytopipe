"""CellProfiler Image table → DeepProfiler ``metadata/index.csv``.

The channel→file mapping is supplied by CellProfiler as ``FileName_Orig<CHANNEL>`` columns in
its exported Image table; cytopipe reads them *by name*. It never parses ``.cppipe`` files and
never reasons about the ``_wN`` acquisition order (which varies by dataset).
"""

from pathlib import Path

import pandas as pd

# Fixed by the Cell Painting CNN model (DeepProfiler handbook §6.2) — NOT configurable.
CHANNEL_ORDER = ["DNA", "RNA", "ER", "AGP", "Mito"]
META_COLS = ["Metadata_Plate", "Metadata_Well", "Metadata_Site"]

# CellProfiler saves the illum-corrected images as TIFF under the original basename, so the
# index references the .tiff outputs even though FileName_Orig records the .tif inputs.
SAVED_IMAGE_EXT = ".tiff"


def read_image_table(path: Path) -> pd.DataFrame:
    """Read the CP Image table CSV"""
    df = pd.read_csv(path, skipinitialspace=True)
    df.columns = df.columns.str.strip()
    return df


def build_index(image_table: pd.DataFrame, plate: str) -> pd.DataFrame:
    """Pure transform: Image table → index rows in the fixed channel order.

    Each ``<CHANNEL>`` column holds ``{plate}/{basename of FileName_Orig<CHANNEL>}.tiff`` — the
    illum-corrected image CellProfiler saved (TIFF) under the original input's basename, laid out
    one directory per plate (matching DeepProfiler's expected ``{plate}/{file}`` image layout).
    Raises a clear error if an expected ``FileName_Orig*`` column is missing, so a misconfigured
    export fails loudly rather than producing a silently mislabeled index.
    """
    out = pd.DataFrame()
    out["Metadata_Plate"] = (
        image_table["Metadata_Plate"] if "Metadata_Plate" in image_table else plate
    )
    out["Metadata_Well"] = image_table["Metadata_Well"].astype(str).str.strip()
    out["Metadata_Site"] = image_table["Metadata_Site"]

    for channel in CHANNEL_ORDER:
        col = f"FileName_Orig{channel}"
        if col not in image_table.columns:
            raise KeyError(
                f"Image table is missing required column {col!r}. "
                f"Ensure CellProfiler's ExportToSpreadsheet emits the Image table with "
                f"FileName_Orig{{{','.join(CHANNEL_ORDER)}}} columns."
            )
        stem = image_table[col].astype(str).str.strip().str.rsplit(".", n=1).str[0]
        out[channel] = plate + "/" + stem + SAVED_IMAGE_EXT

    # Deterministic order (numeric site), done once on the small index table.
    site = pd.to_numeric(out["Metadata_Site"], errors="coerce")
    return (
        out.assign(_site=site)
        .sort_values(["Metadata_Well", "_site"], kind="stable")
        .drop(columns="_site")
        .reset_index(drop=True)
    )


def write_index(index: pd.DataFrame, dest_dir: Path) -> Path:
    """Write ``dest/metadata/index.csv``. Returns the path written."""
    out = Path(dest_dir) / "metadata" / "index.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    index.to_csv(out, index=False)
    return out
