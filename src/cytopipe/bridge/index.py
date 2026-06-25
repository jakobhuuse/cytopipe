from pathlib import Path

import pandas as pd

# Channel order is fixed by the Cell Painting CNN model, not configurable.
CHANNEL_ORDER = ["DNA", "RNA", "ER", "AGP", "Mito"]

METADATA_PLATE = "Metadata_Plate"
METADATA_WELL = "Metadata_Well"
METADATA_SITE = "Metadata_Site"


def read_image_table(path: Path) -> pd.DataFrame:
    """Read a CP Image table CSV, or concatenate every ``*.csv`` in a directory."""
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
        METADATA_PLATE: image_table[METADATA_PLATE] if METADATA_PLATE in image_table else plate,
        METADATA_WELL: image_table[METADATA_WELL].astype(str).str.strip(),
        METADATA_SITE: image_table[METADATA_SITE],
    }
    for channel in CHANNEL_ORDER:
        # CellProfiler records ".tif" originals; DeepProfiler reads the ".tiff" it saves.
        stem = image_table[f"FileName_Orig{channel}"].astype(str).str.strip().str.rsplit(".", n=1)
        cols[channel] = plate + "/" + stem.str[0] + ".tiff"

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
    """Write the index to ``dest/metadata/index.csv`` and return the path."""
    out = Path(dest_dir) / "metadata" / "index.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    index.to_csv(out, index=False)
    return out
