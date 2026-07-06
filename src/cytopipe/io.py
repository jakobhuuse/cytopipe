"""Small shared I/O helpers used across pipeline stages."""

from pathlib import Path

import duckdb
import pandas as pd


def parquet_columns(con: duckdb.DuckDBPyConnection, path: str | Path) -> list[str]:
    """Column names of a parquet file, read via a zero-row DuckDB peek."""
    peek = con.execute("SELECT * FROM read_parquet(?) LIMIT 0", [str(path)])
    return [column[0] for column in peek.description]


def write_csv(frame: pd.DataFrame, path: Path) -> Path:
    """Write ``frame`` to ``path`` (creating parent dirs, no index) and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path
