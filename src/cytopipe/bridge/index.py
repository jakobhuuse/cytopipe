from pathlib import Path

import pandas as pd

from cytopipe.columns import METADATA_PLATE, METADATA_SITE, METADATA_WELL
from cytopipe.io import write_csv

# Channel order is fixed by the Cell Painting CNN model, not configurable.
CHANNEL_ORDER = ["DNA", "RNA", "ER", "AGP", "Mito"]


def read_image_table(path: Path) -> pd.DataFrame:
    """Read a CP Image table CSV, or concatenate every csv in a directory."""
    path = Path(path)
    sources = sorted(path.glob("*.csv")) if path.is_dir() else [path]
    if not sources:
        raise FileNotFoundError(f"No Image table CSV found under {path}.")
    df = pd.concat([pd.read_csv(src, skipinitialspace=True) for src in sources], ignore_index=True)
    df.columns = df.columns.str.strip()
    return df


def build_index(image_table: pd.DataFrame, plate: str) -> pd.DataFrame:
    """Build the DeepProfiler index (metadata + per-channel image paths) from the Image table."""
    missing = [c for c in CHANNEL_ORDER if f"FileName_Orig{c}" not in image_table.columns]
    if missing:
        raise KeyError(
            f"Image table is missing required column(s) "
            f"{', '.join(f'FileName_Orig{c}' for c in missing)}. Ensure CellProfiler's "
            f"ExportToSpreadsheet emits FileName_Orig{{{','.join(CHANNEL_ORDER)}}} columns."
        )

    cols = {
        METADATA_PLATE: plate,
        METADATA_WELL: image_table[METADATA_WELL].astype(str).str.strip(),
        METADATA_SITE: image_table[METADATA_SITE],
    }
    for channel in CHANNEL_ORDER:
        # CellProfiler records ".tif" originals, DeepProfiler reads the ".tiff" it saves.
        original = image_table[f"FileName_Orig{channel}"].astype(str).str.strip()
        cols[channel] = plate + "/" + original.str.rsplit(".", n=1).str[0] + ".tiff"

    return (
        pd.DataFrame(cols)
        .sort_values(
            [METADATA_WELL, METADATA_SITE],
            key=lambda c: pd.to_numeric(c, errors="coerce") if c.name == METADATA_SITE else c,
            kind="stable",
        )
        .reset_index(drop=True)
    )


def write_index(index: pd.DataFrame, dest_dir: Path) -> Path:
    """Write the index and return the path."""
    return write_csv(index, Path(dest_dir) / "metadata" / "index.csv")
