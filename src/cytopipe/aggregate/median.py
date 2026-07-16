"""Memory-bounded well-level aggregation via DuckDB streaming median.

Equivalence with pycytominer's median is deliberate:

- Values are cast to DOUBLE before aggregating, matching pycytominer's
  ``astype(float)`` (float64), so medians agree to full precision.
- NaN is mapped to NULL per feature so DuckDB skips it, matching pandas
  ``median(skipna=True)``. DuckDB otherwise treats NaN as an ordinary value that
  sorts above everything, which would shift the median wherever CellProfiler
  emitted NaN.
- Groups are ordered by strata, matching pandas ``groupby(sort=True)``.
- NULL strata form their own group, matching ``groupby(dropna=False)``.
"""

import tempfile
from pathlib import Path

import duckdb

from cytopipe.io import parquet_columns

DEFAULT_THREADS = 2

# pycytominer's infer_cp_features selects columns carrying a CellProfiler
# compartment prefix. We match that exact rule for features="infer".
_CP_FEATURE_PREFIXES = ("Cells", "Nuclei", "Cytoplasm")


def _quote(identifier: str) -> str:
    """Double-quote a SQL identifier, escaping embedded quotes."""
    return '"' + identifier.replace('"', '""') + '"'


def _infer_features(columns: list[str]) -> list[str]:
    """Feature columns by CellProfiler compartment prefix (matches pycytominer 'infer')."""
    features = [column for column in columns if column.startswith(_CP_FEATURE_PREFIXES)]
    if not features:
        raise ValueError(
            "no CellProfiler feature columns (Cells/Nuclei/Cytoplasm prefix) found to infer; "
            "pass an explicit feature list for non-CellProfiler data"
        )
    return features


def aggregate_median(
    source_path: Path,
    dest_path: Path,
    *,
    strata: list[str],
    features: list[str] | None = None,
    threads: int = DEFAULT_THREADS,
    memory_limit: str | None = None,
    temp_directory: str | None = None,
) -> None:
    """Aggregate single-cell parquet to per-group medians, written to ``dest_path``."""
    if not strata:
        raise ValueError("strata must list at least one grouping column")

    peek_config = {"threads": threads}
    with duckdb.connect(config=peek_config) as peek_con:
        columns = parquet_columns(peek_con, source_path)

    if features is None:
        features = _infer_features(columns)
    elif not features:
        raise ValueError("features must be a non-empty list, or None to infer")

    missing = [column for column in [*strata, *features] if column not in columns]
    if missing:
        raise ValueError(f"columns not present in {source_path.name}: {missing}")

    strata_sql = ", ".join(_quote(column) for column in strata)
    # median over DOUBLE, mapping NaN -> NULL so it is skipped like pandas median(skipna=True).
    median_sql = ", ".join(
        f"median(CASE WHEN isnan(CAST({_quote(feature)} AS DOUBLE)) THEN NULL "
        f"ELSE CAST({_quote(feature)} AS DOUBLE) END) AS {_quote(feature)}"
        for feature in features
    )
    select_sql = (
        f"SELECT {strata_sql}, {median_sql} "
        "FROM read_parquet(?) "
        f"GROUP BY {strata_sql} ORDER BY {strata_sql}"
    )

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_sql = str(dest_path).replace("'", "''")

    spill_dir = temp_directory or tempfile.gettempdir()
    Path(spill_dir).mkdir(parents=True, exist_ok=True)
    config: dict[str, object] = {
        "threads": threads,
        "temp_directory": spill_dir,
        # We stream to parquet and never need input order, so let DuckDB reorder freely.
        "preserve_insertion_order": False,
    }
    if memory_limit:
        config["memory_limit"] = memory_limit

    with duckdb.connect(config=config) as con:
        con.execute(
            f"COPY ({select_sql}) TO '{dest_sql}' (FORMAT PARQUET)",
            [str(source_path)],
        )
