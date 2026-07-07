"""cytopipe bridge: CLI for building DeepProfiler inputs from CellProfiler output."""

from pathlib import Path
from typing import Annotated

import typer

from . import bridge
from .platemap import PLATEMAP_COLS, PLATEMAP_PLATE_COL, PLATEMAP_WELL_COL


def bridge_command(
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
    """Command for building DeepProfiler inputs (locations + index.csv) from CellProfiler output."""
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

    typer.secho(f"{result.summary()} → {dest_path}", fg=typer.colors.GREEN)
    warning = result.warning()
    if warning:
        typer.secho(f"Warning: {warning}", fg=typer.colors.YELLOW)
