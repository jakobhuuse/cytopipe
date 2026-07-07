"""cytopipe loaddata: CLI for generating a CellProfiler LoadData CSV."""

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
    chunk_size: Annotated[
        int,
        typer.Option(
            help="If >0, also write chunks/chunk{i}.load_data.csv + .images.txt "
            "of this many image sets each (for per-chunk distributed runs)."
        ),
    ] = 0,
    images_subdir: Annotated[
        str,
        typer.Option(help="Image PathName, relative to CellProfiler's default input folder (-i)."),
    ] = "images",
    illum_subdir: Annotated[
        str,
        typer.Option(help="Illum-function PathName, relative to the default input folder (-i)."),
    ] = "illum",
) -> None:
    """Generate a CellProfiler LoadData CSV from a plate's raw channel images."""
    try:
        result = generate_loaddata(
            input_dir,
            output_csv,
            plate=plate,
            with_illum=with_illum,
            chunk_size=chunk_size,
            images_subdir=images_subdir,
            illum_subdir=illum_subdir,
        )
    except (FileNotFoundError, ValueError) as exception:
        typer.secho(f"loaddata failed: {exception}", fg=typer.colors.RED)
        raise typer.Exit(1) from exception

    typer.secho(f"{result.summary()} → {output_csv}", fg=typer.colors.GREEN)
