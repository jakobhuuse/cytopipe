import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cytotable.constants
import duckdb
from cytotable import convert
from parsl.config import Config
from parsl.executors import ThreadPoolExecutor

from cytopipe.columns import METADATA_PLATE, METADATA_WELL

DEFAULT_THREADS = 2


def _cellprofiler_joins() -> str:
    """
    Return the cellprofiler_sqlite join with plate/well aliased to canonical Metadata_ names.
    """
    from cytotable.presets import config

    joins = config["cellprofiler_sqlite"]["CONFIG_JOINS"]
    aliases = {
        "per_image.Image_Metadata_Well": METADATA_WELL,
        "per_image.Image_Metadata_Plate": METADATA_PLATE,
    }
    for source_expr, alias in aliases.items():
        needle = f"{source_expr},"
        if needle not in joins:
            raise RuntimeError(
                f"cellprofiler_sqlite preset no longer selects {source_expr!r}; "
                "the join alias override in cytopipe needs updating"
            )
        joins = joins.replace(needle, f"{source_expr} AS {alias},")
    return joins


@dataclass(frozen=True)
class CellProfilerConversion:
    """Outcome of ``cellprofiler_to_parquet``: sources converted vs skipped as empty."""

    converted: list[Path]
    skipped: list[Path]

    @property
    def produced_output(self) -> bool:
        """True when at least one source had data and a parquet was written."""
        return bool(self.converted)


def _source_has_all_compartments(sqlite_path: Path) -> bool:
    """True if every CellProfiler compartment table in the SQLite has at least one row.

    A missing or empty compartment table means CytoTable cannot join single cells
    from this source.
    """
    uri = f"{sqlite_path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as con:
        for table in ("Per_Cells", "Per_Nuclei", "Per_Cytoplasm"):
            try:
                (count,) = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()
            except sqlite3.OperationalError:
                return False  # table absent entirely
            if count == 0:
                return False
    return True


def convert_to_parquet(
    source_path: Path,
    dest_path: Path,
    preset: str,
    *,
    threads: int = DEFAULT_THREADS,
    **convert_kwargs: Any,
) -> None:
    """Run a CytoTable conversion, raising on failure (FileNotFoundError/CytoTableException)."""
    cytotable.constants.MAX_THREADS = threads
    convert_kwargs.setdefault("data_type_cast_map", {"float": "float32"})
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
    source_path: Path,
    dest_path: Path,
    *,
    threads: int = DEFAULT_THREADS,
    chunk_size: int | None = None,
) -> CellProfilerConversion:
    """Convert CellProfiler SQLite output into single-cell parquet.

    Sources whose compartment tables are empty are skipped rather than allowed to
    abort the whole plate inside CytoTable.
    When no source has data, no parquet is written and the returned result
    reports ``produced_output == False`` so the caller can treat the plate as
    yielding no single cells.

    ``chunk_size`` bounds the row count CytoTable joins per pagination chunk
    (default: the ``cellprofiler_sqlite`` preset's own value, 1000). Lower it
    to trade join throughput for a smaller peak memory footprint.
    """
    sqlites = sorted(source_path.rglob("*.sqlite")) if source_path.is_dir() else [source_path]
    if not sqlites:
        raise FileNotFoundError(f"no CellProfiler SQLite files under {source_path}")

    convertible = [s for s in sqlites if _source_has_all_compartments(s)]
    skipped = [s for s in sqlites if s not in convertible]

    if not convertible:
        return CellProfilerConversion(converted=[], skipped=skipped)

    joins = _cellprofiler_joins()
    if not skipped:
        convert_to_parquet(
            source_path,
            dest_path,
            "cellprofiler_sqlite",
            threads=threads,
            joins=joins,
            chunk_size=chunk_size,
        )
    else:
        # Convert only the populated sources, staged as symlinks in a temp dir so
        # CytoTable never opens an empty compartment table.
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            for source in convertible:
                (staged / source.name).symlink_to(source.resolve())
            convert_to_parquet(
                staged,
                dest_path,
                "cellprofiler_sqlite",
                threads=threads,
                joins=joins,
                chunk_size=chunk_size,
            )

    return CellProfilerConversion(converted=convertible, skipped=skipped)


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
            # No cast map: .npz is not tabular, so CytoTable cannot describe its columns.
            data_type_cast_map=None,
        )
        concat_parquets(parts_dir, dest_path, threads=threads)
