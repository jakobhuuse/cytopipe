"""cytopipe CLI — the glue layer between pipeline stages.

Two subcommands wrap the data-management concerns that don't belong to any of the
heavy tool images (CellProfiler, DeepProfiler, pycytominer):

- ``convert`` — CytoTable conversion of CellProfiler output into single-cell parquet
- ``bridge``  — CellProfiler → DeepProfiler metadata handoff

``convert`` stage logic is still stubbed; ``bridge`` is implemented in :mod:`cytopipe.bridge`.
"""

from pathlib import Path
from typing import Annotated

import typer

from cytopipe.bridge import run_bridge

app = typer.Typer(
    name="cytopipe",
    help="CytoTable-based glue layer for a cell-painting feature-extraction pipeline.",
    no_args_is_help=True,
    add_completion=False,
)


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
    """CytoTable conversion of CellProfiler output → single-cell parquet."""
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
    dest_path: Annotated[
        Path, typer.Argument(help="Destination directory for DeepProfiler inputs/.")
    ],
    platemap: Annotated[
        Path,
        typer.Argument(
            help="Plate-map CSV with treatment/replicate annotations (required by DeepProfiler).",
            exists=True,
            dir_okay=False,
        ),
    ],
) -> None:
    """CellProfiler → DeepProfiler handoff: write inputs/locations and inputs/metadata/index.csv."""
    try:
        result = run_bridge(source_path, dest_path, platemap)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        typer.secho(f"bridge failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    typer.secho(
        f"plate {result.plate}: {result.n_location_files} location files, "
        f"{result.n_sites} index rows → {dest_path}",
        fg=typer.colors.GREEN,
    )
    if result.unmatched_wells:
        typer.secho(
            f"warning: {len(result.unmatched_wells)} index key(s) had no plate-map match: "
            f"{', '.join(result.unmatched_wells)}",
            fg=typer.colors.YELLOW,
        )


def _not_implemented(command: str) -> int:
    typer.secho(f"cytopipe {command}: not implemented yet (skeleton).", fg=typer.colors.YELLOW)
    return 1


if __name__ == "__main__":
    app()
