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
        preset=preset,
        # CytoTable defaults to a HighThroughputExecutor, whose worker pool +
        # ZMQ interchange deadlocks under amd64 qemu emulation and oversubscribes
        # a scheduler's cgroup. Run in-process instead.
        parsl_config=Config(executors=[ThreadPoolExecutor(max_threads=None)]),
        **convert_kwargs,
    )


def concat_parquets(parts_dir: Path, dest_path: Path) -> None:
    """Concatenate every parquet under parts_dir into a single parquet at dest_path."""
    parts = sorted(parts_dir.rglob("*.parquet"))
    if not parts:
        raise FileNotFoundError(f"no parquet files under {parts_dir}")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_sql = str(dest_path).replace("'", "''")
    with closing(duckdb.connect()) as con:
        con.execute(
            f"COPY (SELECT * FROM read_parquet(?, union_by_name => true)) "
            f"TO '{dest_sql}' (FORMAT PARQUET)",
            [[str(part) for part in parts]],
        )


def cellprofiler_to_parquet(source_path: Path, dest_path: Path) -> None:
    """Convert CellProfiler SQLite output into single-cell parquet."""
    convert_to_parquet(source_path, dest_path, "cellprofiler_sqlite")


def deepprofiler_to_parquet(source_path: Path, dest_path: Path) -> None:
    """Convert DeepProfiler single-cell output into a single per-plate parquet."""
    # CytoTable's deepprofiler preset has no join SQL (CONFIG_JOINS=""), so it can only
    # emit one parquet per source (npz/well-group), not a single file — a single-file
    # dest errors with "FROM ()". Convert per-source to a temp dir, then concatenate.
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
