"""cytopipe loaddata — CLI for generating a CellProfiler LoadData CSV."""

from pathlib import Path
from typing import Annotated

import typer

from . import generate_loaddata


def loaddata_command(
    input_dir: Annotated[
        Path,
        typer.Argument(help="Plate dir of raw channel TIFFs.", exists=True, file_okay=False),
    ],
    output_csv: Annotated[Path, typer.Argument(help="Destination LoadData CSV path.")],
    plate: Annotated[
        str | None, typer.Option(help="Plate id to record in Metadata_Plate (default: dir name).")
    ] = None,
    with_illum: Annotated[
        bool,
        typer.Option(help="Also emit Illum<channel> file/path columns for the analysis pipeline."),
    ] = False,
    images_token: Annotated[
        str,
        typer.Option(help="Placeholder written as image PathName (sed-substituted at run time)."),
    ] = "__IMAGES__",
    illum_token: Annotated[
        str, typer.Option(help="Placeholder written as illum-function PathName.")
    ] = "__ILLUM__",
) -> None:
    """Generate a CellProfiler LoadData CSV from a plate's raw channel images."""
    try:
        result = generate_loaddata(
            input_dir,
            output_csv,
            plate=plate,
            with_illum=with_illum,
            images_token=images_token,
            illum_token=illum_token,
        )
    except (FileNotFoundError, ValueError) as exception:
        typer.secho(f"loaddata failed: {exception}", fg=typer.colors.RED)
        raise typer.Exit(1) from exception

    typer.secho(f"{result.summary()} → {output_csv}", fg=typer.colors.GREEN)
