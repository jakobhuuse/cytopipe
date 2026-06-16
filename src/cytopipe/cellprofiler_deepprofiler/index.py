from pathlib import Path

import pandas as pd

# Fixed by the Cell Painting CNN model (DeepProfiler handbook §6.2. NOT configurable.
# NB! Might be changed for a future release of DeepProfiler
CHANNEL_ORDER = ["DNA", "RNA", "ER", "AGP", "Mito"]

METADATA_PLATE = "Metadata_Plate"
METADATA_WELL = "Metadata_Well"
METADATA_SITE = "Metadata_Site"


def read_image_table(path: Path) -> pd.DataFrame:
    """Read the CP Image table CSV"""
    df = pd.read_csv(path, skipinitialspace=True)
    df.columns = df.columns.str.strip()
    return df


def build_index(image_table: pd.DataFrame, plate: str) -> pd.DataFrame:
    """
    Builds and returns metadata dataframe created from image table.
    """
    out = pd.DataFrame()
    out[METADATA_PLATE] = image_table[METADATA_PLATE] if METADATA_PLATE in image_table else plate
    out[METADATA_WELL] = image_table[METADATA_WELL].astype(str).str.strip()
    out[METADATA_SITE] = image_table[METADATA_SITE]

    for channel in CHANNEL_ORDER:
        col = f"FileName_Orig{channel}"
        if col not in image_table.columns:
            raise KeyError(
                f"Image table is missing required column {col!r}. "
                f"Ensure CellProfiler's ExportToSpreadsheet emits the Image table with "
                f"FileName_Orig{{{','.join(CHANNEL_ORDER)}}} columns."
            )

        # Replace the file extension ".tif" for ".tiff"
        stem = image_table[col].astype(str).str.strip().str.rsplit(".", n=1).str[0]
        out[channel] = plate + "/" + stem + ".tiff"

    # Deterministic ordering
    site = pd.to_numeric(out[METADATA_SITE], errors="coerce")
    return (
        out.assign(_site=site)
        .sort_values([METADATA_WELL, "_site"], kind="stable")
        .drop(columns="_site")
        .reset_index(drop=True)
    )


def write_index(index: pd.DataFrame, dest_dir: Path) -> Path:
    """
    Write ``dest/metadata/index.csv``.
    Returns the path written.
    """
    out = Path(dest_dir) / "metadata" / "index.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    index.to_csv(out, index=False)
    return out
