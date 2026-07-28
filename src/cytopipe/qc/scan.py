"""Aggregate per-image QC metrics and overlay thumbnails from a CellProfiler QC output tree."""

from pathlib import Path

import pandas as pd

from cytopipe.columns import METADATA_PLATE, METADATA_SITE, METADATA_WELL

POWERLOGLOGSLOPE_PREFIX = "ImageQuality_PowerLogLogSlope_Orig"


def _overlay_path(qc_dir: Path, plate: str, well: str, site: int) -> Path | None:
    """Resolve the Overlays/<plate>_<well>_<site>_overlay.png thumbnail for one image set.

    Globs recursively rather than assuming a fixed nesting depth, since ``qc_dir`` may hold a
    single plate's chunks directly or several plates' chunks each under their own subdirectory
    (e.g. when combining a whole run's images into one gallery).
    """
    matches = sorted(qc_dir.glob(f"**/Overlays/{plate}_{well}_{site}_overlay.png"))
    return matches[0] if matches else None


def scan_qc_metrics(qc_dir: Path) -> pd.DataFrame:
    """Concatenate every ``QCb3/<Plate>_<Well>/Image.csv`` found anywhere under ``qc_dir``.

    Keeps ``Metadata_Plate``/``Well``/``Site`` and every ``PowerLogLogSlope`` column, and adds
    an ``overlay_path`` column resolving each row's matching review thumbnail (``None`` if not
    found). Both ``1_QC.cppipe`` and ``nuclei.cppipe`` write this same layout. The search is
    recursive, so ``qc_dir`` may be one plate's chunk outputs or a whole run's worth across
    several plates, each in their own subdirectory. Rows are told apart by their own
    ``Metadata_Plate``/``Well``/``Site`` values, not by directory structure.
    """
    qc_dir = Path(qc_dir)
    paths = sorted(qc_dir.glob("**/QCb3/*/Image.csv"))
    if not paths:
        raise FileNotFoundError(f"no QCb3/*/Image.csv files found under {qc_dir}")

    frames = []
    for path in paths:
        frame = pd.read_csv(path)
        keep = [METADATA_PLATE, METADATA_WELL, METADATA_SITE] + [
            column for column in frame.columns if column.startswith(POWERLOGLOGSLOPE_PREFIX)
        ]
        frames.append(frame[keep])
    metrics = pd.concat(frames, ignore_index=True)

    metrics["overlay_path"] = [
        _overlay_path(qc_dir, row[METADATA_PLATE], row[METADATA_WELL], int(row[METADATA_SITE]))
        for _, row in metrics.iterrows()
    ]
    return metrics


def channel_columns(metrics: pd.DataFrame) -> dict[str, str]:
    """Map channel name (e.g. ``"DNA"``) to its ``PowerLogLogSlope`` column name in ``metrics``."""
    return {
        column[len(POWERLOGLOGSLOPE_PREFIX) :]: column
        for column in metrics.columns
        if column.startswith(POWERLOGLOGSLOPE_PREFIX)
    }
