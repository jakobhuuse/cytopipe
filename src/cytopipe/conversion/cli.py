from pathlib import Path
from typing import Annotated

import typer
from cytotable.exceptions import CytoTableException

from .parquet import cellprofiler_to_parquet, deepprofiler_to_parquet

app = typer.Typer(
    no_args_is_help=True,
    help="Convert image-tool output into single-cell parquet (CytoTable).",
)


def _run_conversion(label: str, convert_fn, source_path: Path, dest_path: Path) -> None:
    """Run a CytoTable conversion, reporting success/failure and exiting non-zero on error."""
    try:
        convert_fn(source_path, dest_path)
    except (FileNotFoundError, CytoTableException) as exception:
        typer.secho(f"{label} failed: {exception}", fg=typer.colors.RED)
        raise typer.Exit(1) from exception
    typer.secho(f"{source_path} → {dest_path}", fg=typer.colors.GREEN)


@app.command("cellprofiler")
def cellprofiler_parquet(
    source_path: Annotated[
        Path,
        typer.Argument(help="CellProfiler SQLite output to convert.", exists=True),
    ],
    dest_path: Annotated[Path, typer.Argument(help="Destination single-cell parquet path.")],
) -> None:
    """Convert CellProfiler SQLite output into single-cell parquet."""
    _run_conversion("convert cellprofiler", cellprofiler_to_parquet, source_path, dest_path)


@app.command("deepprofiler")
def deepprofiler_parquet(
    source_path: Annotated[
        Path,
        typer.Argument(help="DeepProfiler single-cell output to convert.", exists=True),
    ],
    dest_path: Annotated[Path, typer.Argument(help="Destination single-cell parquet path.")],
) -> None:
    """Convert DeepProfiler single-cell output into a single per-plate parquet."""
    _run_conversion("convert deepprofiler", deepprofiler_to_parquet, source_path, dest_path)
