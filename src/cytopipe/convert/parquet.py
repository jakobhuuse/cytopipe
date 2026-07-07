import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

import duckdb
from cytotable import convert
from parsl.config import Config
from parsl.executors import ThreadPoolExecutor

DEFAULT_THREADS = 2


def convert_to_parquet(
    source_path: Path,
    dest_path: Path,
    preset: str,
    *,
    threads: int = DEFAULT_THREADS,
    **convert_kwargs: Any,
) -> None:
    """Run a CytoTable conversion, raising on failure (FileNotFoundError/CytoTableException)."""
    convert(
        source_path=str(source_path),
        dest_path=str(dest_path),
        dest_datatype="parquet",
        # ThreadPoolExecutor avoids CytoTable's default HighThroughputExecutor, which deadlocks
        # under emulation. Capping threads keeps memory from scaling with the host core count.
        parsl_config=Config(executors=[ThreadPoolExecutor(max_threads=threads)]),
        preset=preset,
        **convert_kwargs,
    )


def _row_count(con: duckdb.DuckDBPyConnection, paths: list[str]) -> int:
    return con.execute("SELECT count(*) FROM read_parquet(?)", [paths]).fetchone()[0]


def _assert_uniform_schema(con: duckdb.DuckDBPyConnection, paths: list[str]) -> None:
    """Raise unless all parts share one column set, read in a single metadata query."""
    rows = con.execute(
        "SELECT file_name, name FROM parquet_schema(?) WHERE type IS NOT NULL",
        [paths],
    ).fetchall()
    by_file: dict[str, set[str]] = {}
    for file_name, column in rows:
        by_file.setdefault(file_name, set()).add(column)

    reference = by_file[paths[0]]
    for path in paths[1:]:
        found = by_file[path]
        if found != reference:
            raise ValueError(
                f"schema mismatch in {Path(path).name}: "
                f"missing {sorted(reference - found)}, unexpected {sorted(found - reference)}"
            )


def concat_parquets(parts_dir: Path, dest_path: Path, *, threads: int = DEFAULT_THREADS) -> None:
    """Concatenate every parquet under parts_dir into a single parquet at dest_path."""
    parts = sorted(str(part) for part in parts_dir.rglob("*.parquet"))
    if not parts:
        raise FileNotFoundError(f"no parquet files under {parts_dir}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_sql = str(dest_path).replace("'", "''")

    with closing(duckdb.connect(config={"threads": threads})) as con:
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


def cellprofiler_to_parquet(
    source_path: Path, dest_path: Path, *, threads: int = DEFAULT_THREADS
) -> None:
    """Convert CellProfiler SQLite output into single-cell parquet."""
    convert_to_parquet(source_path, dest_path, "cellprofiler_sqlite", threads=threads)


def deepprofiler_to_parquet(
    source_path: Path, dest_path: Path, *, threads: int = DEFAULT_THREADS
) -> None:
    """Convert DeepProfiler single-cell output into a single per-plate parquet."""
    with tempfile.TemporaryDirectory() as tmp:
        parts_dir = Path(tmp) / "parts"
        convert_to_parquet(
            source_path,
            parts_dir,
            "deepprofiler",
            threads=threads,
            source_datatype="npz",
            join=False,
        )
        concat_parquets(parts_dir, dest_path, threads=threads)
