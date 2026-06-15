from pathlib import Path
from typing import Annotated

import typer

from cytopipe.bridge import run_bridge
from cytopipe.bridge.platemap import PLATEMAP_COLS, PLATEMAP_PLATE_COL, PLATEMAP_WELL_COL

app = typer.Typer(
    name="cytopipe",
    help="CytoTable-based glue layer for a cell-painting feature-extraction pipeline.",
    no_args_is_help=True,
    add_completion=False,
)


def _not_implemented(command: str) -> int:
    typer.secho(f"cytopipe {command}: not implemented yet.", fg=typer.colors.YELLOW)
    return 1


@app.command()
def convert(
    source_path: Annotated[
        Path, typer.Argument(help="CellProfiler output to convert (SQLite/CSV directory).")
    ],
    dest_path: Annotated[Path, typer.Argument(help="Destination single-cell parquet path.")],
    preset: Annotated[
        str, typer.Option(help="CytoTable source preset describing the input layout.")
    ] = "cellprofiler_sqlite_pycytominer",
) -> None:
    raise typer.Exit(_not_implemented("convert"))


@app.command()
def bridge(
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
        str | None,
        typer.Option(help="Comma-separated plate-map columns to carry into index.csv."),
    ] = None,
) -> None:
    cols = tuple(c.strip() for c in platemap_cols.split(",")) if platemap_cols else PLATEMAP_COLS
    try:
        result = run_bridge(
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
