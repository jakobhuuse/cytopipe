from pathlib import Path
from typing import Annotated, Any

import typer
from cytotable import convert
from cytotable.exceptions import CytoTableException
from parsl.config import Config
from parsl.executors import ThreadPoolExecutor

from cytopipe.cellprofiler_deepprofiler import bridge
from cytopipe.cellprofiler_deepprofiler.platemap import (
    PLATEMAP_COLS,
    PLATEMAP_PLATE_COL,
    PLATEMAP_WELL_COL,
)

app = typer.Typer(
    name="cytopipe",
    help="CytoTable-based glue layer for a cell-painting feature-extraction pipeline.",
    no_args_is_help=True,
    add_completion=False,
)


def _convert_to_parquet(
    command: str,
    source_path: Path,
    dest_path: Path,
    preset: str,
    **convert_kwargs: Any,
) -> None:
    """Run a CytoTable conversion and report the outcome, exiting non-zero on failure."""
    try:
        convert(
            source_path=str(source_path),
            dest_path=str(dest_path),
            dest_datatype="parquet",
            preset=preset,
            # CytoTable defaults to a HighThroughputExecutor, whose worker pool +
            # ZMQ interchange deadlocks under amd64 qemu emulation. Run in-process.
            # cytopipe runs each plate in parallell, so the performance impact
            # should be negligable.
            parsl_config=Config(executors=[ThreadPoolExecutor()]),
            **convert_kwargs,
        )
    except (FileNotFoundError, CytoTableException) as exception:
        typer.secho(f"{command} failed: {exception}", fg=typer.colors.RED)
        raise typer.Exit(1) from exception

    typer.secho(f"{source_path} → {dest_path}", fg=typer.colors.GREEN)


@app.command()
def cellprofiler_parquet(
    source_path: Annotated[
        Path,
        typer.Argument(help="CellProfiler SQLite output to convert.", exists=True),
    ],
    dest_path: Annotated[Path, typer.Argument(help="Destination single-cell parquet path.")],
) -> None:
    """Convert CellProfiler SQLite output into single-cell parquet (CytoTable)."""
    _convert_to_parquet("cellprofiler-parquet", source_path, dest_path, "cellprofiler_sqlite")


@app.command()
def deepprofiler_parquet(
    source_path: Annotated[
        Path,
        typer.Argument(help="DeepProfiler single-cell output to convert.", exists=True),
    ],
    dest_path: Annotated[Path, typer.Argument(help="Destination single-cell parquet path.")],
) -> None:
    """Convert DeepProfiler single-cell output into parquet (CytoTable)."""
    _convert_to_parquet(
        "deepprofiler-parquet",
        source_path,
        dest_path,
        "deepprofiler",
        source_datatype="npz",
        join=False,
    )


@app.command()
def cellprofiler_deepprofiler(
    source_path: Annotated[
        Path,
        typer.Argument(
            help="CellProfiler measurement/ dir (or a plate dir containing one).",
            exists=True,
            file_okay=False,
        ),
    ],
    dest_path: Annotated[Path, typer.Argument(help="Destination directory.")],
    platemap: Annotated[
        Path,
        typer.Argument(
            help="Plate-map CSV with treatment/replicate annotations (required by DeepProfiler).",
            exists=True,
            dir_okay=False,
        ),
    ],
    platemap_plate_col: Annotated[
        str,
        typer.Option(help="Plate-map column to join on plate (empty string = well-only join)."),
    ] = PLATEMAP_PLATE_COL,
    platemap_well_col: Annotated[
        str, typer.Option(help="Plate-map column to join on well.")
    ] = PLATEMAP_WELL_COL,
    platemap_cols: Annotated[
        str,
        typer.Option(help="Comma-separated plate-map columns to carry into index.csv."),
    ] = ",".join(PLATEMAP_COLS),
) -> None:
    """Build DeepProfiler metadata from CellProfiler output."""
    cols = tuple(c.strip() for c in platemap_cols.split(",") if c.strip())
    try:
        result = bridge(
            source_path,
            dest_path,
            platemap,
            platemap_plate_col=platemap_plate_col,
            platemap_well_col=platemap_well_col,
            platemap_cols=cols,
        )
    except (FileNotFoundError, KeyError, ValueError) as exception:
        typer.secho(f"bridge failed: {exception}", fg=typer.colors.RED)
        raise typer.Exit(1) from exception

    typer.secho(
        f"plate {result.plate}: {result.n_location_files} location files, "
        f"{result.n_sites} index rows → {dest_path}",
        fg=typer.colors.GREEN,
    )

    if result.unmatched_wells:
        typer.secho(
            f"Warning: {len(result.unmatched_wells)} index key(s) had no plate-map match: "
            f"{', '.join(result.unmatched_wells)}",
            fg=typer.colors.YELLOW,
        )
