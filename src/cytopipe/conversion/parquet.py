import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

import duckdb
from cytotable import convert
from parsl.config import Config
from parsl.executors import ThreadPoolExecutor


def convert_to_parquet(
    source_path: Path,
    dest_path: Path,
    preset: str,
    **convert_kwargs: Any,
) -> None:
    """Run a CytoTable conversion, raising on failure (FileNotFoundError/CytoTableException)."""
    convert(
        source_path=str(source_path),
        dest_path=str(dest_path),
        dest_datatype="parquet",
        # CytoTable defaults to a HighThroughputExecutor. 
        # This deadlocks under emulation, and unnecessary for per-plate conversion.
        parsl_config=Config(executors=[ThreadPoolExecutor(max_threads=None)]),
        preset=preset,
        **convert_kwargs,
    )


def _row_count(con: duckdb.DuckDBPyConnection, paths: list[str]) -> int:
    return con.execute("SELECT count(*) FROM read_parquet(?)", [paths]).fetchone()[0]


def _assert_uniform_schema(con: duckdb.DuckDBPyConnection, paths: list[str]) -> None:
    """Raise unless all parts share one column set, so union_by_name can't NULL-pad."""

    def columns(path: str) -> set[str]:
        peek = con.execute("SELECT * FROM read_parquet(?) LIMIT 0", [path])
        return {column[0] for column in peek.description}

    reference = columns(paths[0])
    for path in paths[1:]:
        found = columns(path)
        if found != reference:
            raise ValueError(
                f"schema mismatch in {Path(path).name}: "
                f"missing {sorted(reference - found)}, unexpected {sorted(found - reference)}"
            )


def concat_parquets(parts_dir: Path, dest_path: Path) -> None:
    """Concatenate every parquet under parts_dir into a single parquet at dest_path (lossless)."""
    parts = sorted(str(part) for part in parts_dir.rglob("*.parquet"))
    if not parts:
        raise FileNotFoundError(f"no parquet files under {parts_dir}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_sql = str(dest_path).replace("'", "''")

    with closing(duckdb.connect()) as con:
        _assert_uniform_schema(con, parts)
        expected_rows = _row_count(con, parts)

        con.execute(
            f"COPY (SELECT * FROM read_parquet(?, union_by_name => true)) "
            f"TO '{dest_sql}' (FORMAT PARQUET)",
            [parts],
        )

        written_rows = _row_count(con, [str(dest_path)])
        if written_rows != expected_rows:
            raise ValueError(
                f"row-count mismatch into {dest_path.name}: "
                f"parts have {expected_rows}, output has {written_rows}"
            )


def cellprofiler_to_parquet(source_path: Path, dest_path: Path) -> None:
    """Convert CellProfiler SQLite output into single-cell parquet."""
    convert_to_parquet(source_path, dest_path, "cellprofiler_sqlite")


def deepprofiler_to_parquet(source_path: Path, dest_path: Path) -> None:
    """Convert DeepProfiler single-cell output into a single per-plate parquet."""
    with tempfile.TemporaryDirectory() as tmp:
        parts_dir = Path(tmp) / "parts"
        convert_to_parquet(
            source_path,
            parts_dir,
            "deepprofiler",
            source_datatype="npz",
            join=False,
        )
        concat_parquets(parts_dir, dest_path)
