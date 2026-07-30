"""Aggregate per-image QC metrics and overlay thumbnails from a CellProfiler QC output tree."""

import os
from pathlib import Path

import pandas as pd

from cytopipe.columns import METADATA_PLATE, METADATA_SITE, METADATA_WELL

BLUR_PREFIX = "ImageQuality_PowerLogLogSlope_Orig"
FOCUS_SCORE_PREFIX = "ImageQuality_FocusScore_Orig"
PERCENT_MAXIMAL_PREFIX = "ImageQuality_PercentMaximal_Orig"
CELL_COUNT_COLUMN = "Count_Nuclei"

# Every per-channel metric the review gallery can plot. All three come from the same
# MeasureImageQuality module (1_QC.cppipe), computed for every channel already, alongside
# CELL_COUNT_COLUMN from the Nuclei IdentifyPrimaryObjects module (a single value, not
# per-channel).
PER_CHANNEL_PREFIXES = (BLUR_PREFIX, FOCUS_SCORE_PREFIX, PERCENT_MAXIMAL_PREFIX)


def _find_dirs(root: Path, name: str) -> list[Path]:
    """Directories named ``name`` anywhere under ``root``, however deep.

    Walks with ``followlinks=True`` rather than using ``Path.glob("**/...")``, since Nextflow
    stages each chunk's output directory into the review process as a symlink, and pathlib's
    ``**`` silently refuses to descend into symlinked directories.
    """
    return [
        Path(dirpath)
        for dirpath, _dirnames, _filenames in os.walk(root, followlinks=True)
        if Path(dirpath).name == name
    ]


def _overlay_index(qc_dir: Path) -> dict[str, Path]:
    """Map ``<plate>_<well>_<site>_overlay.png`` filename to its path, across every chunk."""
    return {
        png.name: png
        for overlays_dir in _find_dirs(qc_dir, "Overlays")
        for png in overlays_dir.glob("*.png")
    }


def scan_qc_metrics(qc_dir: Path) -> pd.DataFrame:
    """Concatenate every ``QCb3/<Plate>_<Well>/Image.csv`` found anywhere under ``qc_dir``.

    Keeps ``Metadata_Plate``/``Well``/``Site``, ``CELL_COUNT_COLUMN``, and every column under
    each ``PER_CHANNEL_PREFIXES`` prefix, and adds an ``overlay_path`` column resolving each
    row's matching review thumbnail (``None`` if not found). The search recurses through
    symlinks, so ``qc_dir`` may be one plate's chunk outputs or a whole run's worth across
    several plates, each in their own subdirectory (or symlinked chunk directory, as Nextflow
    stages them). Rows are told apart by their own ``Metadata_Plate``/``Well``/``Site`` values,
    not by directory structure.
    """
    qc_dir = Path(qc_dir)
    paths = sorted(
        image_csv
        for qcb3_dir in _find_dirs(qc_dir, "QCb3")
        for image_csv in qcb3_dir.glob("*/Image.csv")
    )
    if not paths:
        raise FileNotFoundError(f"no QCb3/*/Image.csv files found under {qc_dir}")

    frames = []
    for path in paths:
        frame = pd.read_csv(path)
        per_channel_columns = [
            column
            for prefix in PER_CHANNEL_PREFIXES
            for column in frame.columns
            if column.startswith(prefix)
        ]
        keep = [
            METADATA_PLATE,
            METADATA_WELL,
            METADATA_SITE,
            CELL_COUNT_COLUMN,
        ] + per_channel_columns
        frames.append(frame[keep])
    metrics = pd.concat(frames, ignore_index=True)

    overlay_index = _overlay_index(qc_dir)
    metrics["overlay_path"] = [
        overlay_index.get(f"{row[METADATA_PLATE]}_{row[METADATA_WELL]}_{int(row[METADATA_SITE])}_overlay.png")
        for _, row in metrics.iterrows()
    ]
    return metrics


def channel_columns(metrics: pd.DataFrame, prefix: str) -> dict[str, str]:
    """Map channel name (e.g. ``"DNA"``) to its full column name for the given metric prefix."""
    return {
        column[len(prefix) :]: column for column in metrics.columns if column.startswith(prefix)
    }
