"""cytopipe convert: CLI for CytoTable conversions to single-cell parquet."""

from pathlib import Path
from typing import Annotated

import typer
from cytotable.exceptions import CytoTableException

from . import (
    DEFAULT_THREADS,
    cellprofiler_to_parquet,
    concat_parquets,
    deepprofiler_to_parquet,
)

app = typer.Typer(
    no_args_is_help=True,
    help="Convert image-tool output into single-cell parquet (CytoTable).",
)

ThreadsOption = Annotated[
    int,
    typer.Option(help="Max parallel workers, bounding memory. Pass the task's CPU count."),
]


def _run_conversion(
    label: str, convert_fn, source_path: Path, dest_path: Path, threads: int
) -> None:
    """Run a CytoTable conversion, reporting success/failure and exiting non-zero on error."""
    try:
        convert_fn(source_path, dest_path, threads=threads)
    except (FileNotFoundError, CytoTableException, ValueError) as exception:
        typer.secho(f"{label} failed: {exception}", fg=typer.colors.RED)
        raise typer.Exit(1) from exception
    typer.secho(f"{source_path} → {dest_path}", fg=typer.colors.GREEN)


@app.command("cellprofiler")
def cellprofiler_command(
    source_path: Annotated[
        Path,
        typer.Argument(help="CellProfiler SQLite output to convert.", exists=True),
    ],
    dest_path: Annotated[Path, typer.Argument(help="Destination single-cell parquet path.")],
    threads: ThreadsOption = DEFAULT_THREADS,
) -> None:
    """Convert CellProfiler SQLite output into single-cell parquet."""
    _run_conversion(
        "convert cellprofiler", cellprofiler_to_parquet, source_path, dest_path, threads
    )


@app.command("deepprofiler")
def deepprofiler_command(
    source_path: Annotated[
        Path,
        typer.Argument(help="DeepProfiler single-cell output to convert.", exists=True),
    ],
    dest_path: Annotated[Path, typer.Argument(help="Destination single-cell parquet path.")],
    threads: ThreadsOption = DEFAULT_THREADS,
) -> None:
    """Convert DeepProfiler single-cell output into a single per-plate parquet."""
    _run_conversion(
        "convert deepprofiler", deepprofiler_to_parquet, source_path, dest_path, threads
    )


@app.command("concat")
def concat_command(
    parts_dir: Annotated[
        Path,
        typer.Argument(help="Directory containing parquets to concatenate.", exists=True),
    ],
    dest_path: Annotated[Path, typer.Argument(help="Destination combined parquet path.")],
    threads: ThreadsOption = DEFAULT_THREADS,
) -> None:
    """Concatenate every parquet under a directory into one (union by name, schema-checked)."""
    _run_conversion("convert concat", concat_parquets, parts_dir, dest_path, threads)
