"""Locate pycytominer profile outputs and shape them for the report figures.

The pipeline publishes profiles under ``results/<experiment>/<engine>/`` (see
``nextflow/workflows/*.nf``). Metadata columns are ``Metadata_*`` and everything else is a
feature — the pycytominer ``--features infer`` contract — so the same code serves both the
DeepProfiler (``efficientnet_*``) and CellProfiler (``Cells_/Cytoplasm_/Nuclei_*``) engines.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

METADATA_PREFIX = "Metadata_"
PLATE_COL = "Metadata_Plate"
WELL_COL = "Metadata_Well"
COMPOUND_COL = "Metadata_Compound"
BATCH_COL = "Metadata_Batch"
CONTROL_COMPOUND = "DMSO"

ENGINES = ("deepprofiler", "cellprofiler")
# CytoTable may prefix the well column differently between engines; try these in order.
_WELL_COL_CANDIDATES = (WELL_COL, "Image_Metadata_Well")
# Smallest standard microplate whose grid contains the observed wells.
_STANDARD_PLATES = ((8, 12), (16, 24), (32, 48))
_WELL_RE = re.compile(r"^\s*([A-Za-z]+)\s*0*(\d+)\s*$")


@dataclass(frozen=True)
class ProfileSet:
    """Resolved profile files for one engine under a results tree."""

    engine: str
    root: Path
    normalized: list[Path]
    raw: list[Path]
    consensus: Path | None
    feature_select: Path | None

    def cohort_source(self) -> list[Path]:
        """Well-level cohort input for the embedding/reproducibility figures.

        Prefer CellProfiler's feature-selected cohort file; otherwise the per-plate
        normalized profiles (DeepProfiler publishes no feature_select step).
        """
        if self.feature_select is not None:
            return [self.feature_select]
        return self.normalized


def _looks_like_engine_dir(directory: Path) -> bool:
    return directory.is_dir() and (
        (directory / "consensus.parquet").exists() or (directory / "normalized").is_dir()
    )


def _find_engine_dirs(results_dir: Path, engine: str) -> list[Path]:
    names = ENGINES if engine == "auto" else (engine,)
    candidates = [results_dir, *(p for p in results_dir.rglob("*") if p.is_dir())]
    found = {d for d in candidates if d.name in names and _looks_like_engine_dir(d)}
    return sorted(found)


def discover_profiles(results_dir: Path, engine: str = "auto") -> ProfileSet:
    """Resolve the ``<engine>`` profile directory under ``results_dir``.

    Accepts a path pointing at the engine dir itself, at an experiment dir, or at a whole
    ``results/`` tree (the ``<experiment>/`` layer is discovered, not hardcoded).
    """
    results_dir = Path(results_dir)
    if not results_dir.exists():
        raise FileNotFoundError(f"results path does not exist: {results_dir}")

    dirs = _find_engine_dirs(results_dir, engine)
    if not dirs:
        wanted = "/".join(ENGINES) if engine == "auto" else engine
        raise FileNotFoundError(f"no {wanted} profile directory found under {results_dir}")
    if len(dirs) > 1:
        listing = ", ".join(str(d) for d in dirs)
        raise ValueError(
            f"multiple profile directories found; point at one or pass --engine: {listing}"
        )

    root = dirs[0]
    normalized_dir, raw_dir = root / "normalized", root / "raw"
    consensus = root / "consensus.parquet"
    feature_select = root / "selected" / "feature_select.parquet"
    return ProfileSet(
        engine=root.name,
        root=root,
        normalized=sorted(normalized_dir.glob("*.parquet")) if normalized_dir.is_dir() else [],
        raw=sorted(raw_dir.glob("*.parquet")) if raw_dir.is_dir() else [],
        consensus=consensus if consensus.exists() else None,
        feature_select=feature_select if feature_select.exists() else None,
    )


def plate_id_from_path(path: Path) -> str:
    """``26157.normalized.parquet`` / ``26157.parquet`` -> ``26157``."""
    return path.stem.split(".")[0]


def load_profiles(paths: list[Path]) -> pd.DataFrame:
    """Read and row-concatenate one or more profile parquet files."""
    if not paths:
        raise FileNotFoundError("no profile parquet files to load")
    return pd.concat((pd.read_parquet(p) for p in paths), ignore_index=True)


def split_metadata_features(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Split columns into metadata (``Metadata_*``) and numeric feature columns."""
    metadata = [c for c in df.columns if c.startswith(METADATA_PREFIX)]
    features = [
        c
        for c in df.columns
        if not c.startswith(METADATA_PREFIX) and pd.api.types.is_numeric_dtype(df[c])
    ]
    return metadata, features


def clean_features(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Feature matrix robust to CellProfiler's Inf/NaN and mixed scales.

    Inf -> NaN, drop all-NaN and zero-variance columns, median-impute, then any residual NaN
    (fully-empty columns) -> 0. Harmless on already-clean DeepProfiler embeddings.
    """
    matrix = df[features].apply(pd.to_numeric, errors="coerce")
    matrix = matrix.replace([np.inf, -np.inf], np.nan)
    matrix = matrix.dropna(axis=1, how="all")
    matrix = matrix.loc[:, matrix.nunique(dropna=True) > 1]
    matrix = matrix.fillna(matrix.median(numeric_only=True)).fillna(0.0)
    return matrix


def _row_to_index(letters: str) -> int:
    """Plate row letters -> 0-based index (``A`` -> 0, ``H`` -> 7, ``AA`` -> 26)."""
    index = 0
    for char in letters.upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def parse_wells(wells: pd.Series) -> pd.DataFrame:
    """Parse ``A02``/``G12`` well IDs into 0-based ``row``/``col`` grid coordinates."""
    parts = wells.astype(str).str.extract(_WELL_RE)
    row = parts[0].map(lambda s: _row_to_index(s) if isinstance(s, str) else np.nan)
    col = pd.to_numeric(parts[1], errors="coerce") - 1
    return pd.DataFrame({"row": row, "col": col})


def infer_grid_shape(max_row: int, max_col: int) -> tuple[int, int]:
    """Smallest standard plate (96/384/1536) containing the observed wells, else exact fit."""
    for rows, cols in _STANDARD_PLATES:
        if max_row < rows and max_col < cols:
            return rows, cols
    return max_row + 1, max_col + 1


def _parquet_columns(path: Path) -> list[str]:
    with duckdb.connect() as con:
        peek = con.execute("SELECT * FROM read_parquet(?) LIMIT 0", [str(path)])
        return [column[0] for column in peek.description]


def _detect_well_column(path: Path) -> str:
    columns = _parquet_columns(path)
    for candidate in _WELL_COL_CANDIDATES:
        if candidate in columns:
            return candidate
    raise KeyError(f"no well column ({' / '.join(_WELL_COL_CANDIDATES)}) in {path.name}")


def well_cell_counts(raw_path: Path) -> pd.DataFrame:
    """Cells per well from a single-cell parquet, streamed via DuckDB (files can be GBs)."""
    well_column = _detect_well_column(raw_path)
    with duckdb.connect() as con:
        return con.execute(
            f'SELECT "{well_column}" AS well, count(*) AS value '
            "FROM read_parquet(?) GROUP BY 1",
            [str(raw_path)],
        ).df()


def plate_well_values(profiles: ProfileSet) -> tuple[list[tuple[str, pd.DataFrame]], str]:
    """Per-well QC value for each plate: cell count from ``raw/``, else mean |feature|.

    Returns ``([(plate_id, DataFrame[well, value]), ...], value_label)``.
    """
    if profiles.raw:
        plates = [(plate_id_from_path(p), well_cell_counts(p)) for p in profiles.raw]
        return plates, "cell count"

    plates = []
    for path in profiles.normalized:
        df = pd.read_parquet(path)
        _, features = split_metadata_features(df)
        wells = pd.DataFrame(
            {"well": df[WELL_COL].astype(str), "value": df[features].abs().mean(axis=1)}
        )
        plates.append((plate_id_from_path(path), wells))
    return plates, "mean |feature|"
