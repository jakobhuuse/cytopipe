from pathlib import Path

import pandas as pd

from cytopipe.columns import METADATA_PLATE, METADATA_SITE, METADATA_WELL
from cytopipe.io import write_csv

from .scan import CHANNEL_BY_NUMBER


def build_loaddata(
    images: pd.DataFrame,
    plate: str,
    *,
    images_subdir: str = "images",
    with_illum: bool = False,
    illum_subdir: str = "illum",
) -> pd.DataFrame:
    """Pivot scanned image rows into a CellProfiler LoadData table, one row per image set.

    PathNames hold ``images_subdir``/``illum_subdir``, resolved at run time by ``cellprofiler -i``.
    Raises if an image set is missing a channel.
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
            row[f"Image_PathName_Orig{name}"] = images_subdir
        if with_illum:
            for name in CHANNEL_BY_NUMBER.values():
                row[f"Image_FileName_Illum{name}"] = f"Illum{name}.npy"
                row[f"Image_PathName_Illum{name}"] = illum_subdir
        records.append(row)

    return pd.DataFrame.from_records(records)


def write_loaddata(table: pd.DataFrame, out: Path) -> Path:
    """Write the LoadData table to ``out`` (creating parent dirs) and return the path."""
    return write_csv(table, out)


def image_filenames(table: pd.DataFrame) -> list[str]:
    """Sorted, unique raw image filenames a LoadData table references (Orig channels only)."""
    cols = [c for c in table.columns if c.startswith("Image_FileName_Orig")]
    return sorted({name for col in cols for name in table[col]})


def write_chunks(table: pd.DataFrame, chunk_dir: Path, chunk_size: int) -> int:
    """Split ``table`` into ``chunk_size``-row chunks under ``chunk_dir`` and return the count.

    Each chunk gets a ``chunk{i}.load_data.csv`` and a ``chunk{i}.images.txt`` manifest of the
    tifs it references, so a scheduler can stage just those images.
    """
    chunk_dir = Path(chunk_dir)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    n_chunks = -(-len(table) // chunk_size)  # ceil division
    for i in range(n_chunks):
        chunk = table.iloc[i * chunk_size : (i + 1) * chunk_size]
        write_csv(chunk, chunk_dir / f"chunk{i + 1}.load_data.csv")
        manifest = "".join(f"{name}\n" for name in image_filenames(chunk))
        (chunk_dir / f"chunk{i + 1}.images.txt").write_text(manifest)
    return n_chunks
