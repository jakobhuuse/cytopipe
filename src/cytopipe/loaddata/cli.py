"""cytopipe loaddata: CLI for generating a CellProfiler LoadData CSV."""

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from . import generate_loaddata
from .build import write_chunks, write_loaddata
from .filter import filter_loaddata


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


def loaddata_filter_command(
    load_data_csv: Annotated[
        Path, typer.Argument(help="Existing LoadData CSV to filter.", exists=True, dir_okay=False)
    ],
    exclude_csv: Annotated[
        Path,
        typer.Argument(
            help="CSV of Metadata_Plate/Well/Site rows to drop.", exists=True, dir_okay=False
        ),
    ],
    output_csv: Annotated[Path, typer.Argument(help="Destination, filtered LoadData CSV path.")],
    chunk_size: Annotated[
        int,
        typer.Option(
            help="If >0, also write chunks/chunk{i}.load_data.csv + .images.txt "
            "of this many image sets each."
        ),
    ] = 0,
) -> None:
    """Drop excluded (Plate, Well, Site) image sets from an existing LoadData CSV.

    An absent or empty ``exclude_csv`` (header row only) is a no-op passthrough.
    """
    table = pd.read_csv(load_data_csv)
    excluded = pd.read_csv(exclude_csv)
    filtered = filter_loaddata(table, excluded)
    write_loaddata(filtered, output_csv)

    n_chunks = 0
    if chunk_size > 0:
        n_chunks = write_chunks(filtered, output_csv.parent / "chunks", chunk_size)

    dropped = len(table) - len(filtered)
    chunks_msg = f", {n_chunks} chunks" if n_chunks else ""
    typer.secho(
        f"{len(filtered)} image sets kept, {dropped} excluded{chunks_msg} → {output_csv}",
        fg=typer.colors.GREEN,
    )
