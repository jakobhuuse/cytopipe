"""cytopipe aggregate: memory-bounded well-level median aggregation."""

from pathlib import Path
from typing import Annotated

import duckdb
import typer

from . import DEFAULT_THREADS, aggregate_median


def _split_csv(value: str) -> list[str]:
    """Parse a comma-separated column list, dropping blanks and surrounding space."""
    return [item.strip() for item in value.split(",") if item.strip()]


def aggregate_command(
    source_path: Annotated[
        Path,
        typer.Argument(help="Single-cell parquet to aggregate.", exists=True, dir_okay=False),
    ],
    dest_path: Annotated[Path, typer.Argument(help="Destination aggregated parquet path.")],
    strata: Annotated[
        str,
        typer.Option(help="Comma-separated grouping columns, e.g. Metadata_Plate,Metadata_Well."),
    ],
    features: Annotated[
        str,
        typer.Option(
            help="Comma-separated feature columns, or 'infer' for CellProfiler "
            "(Cells/Nuclei/Cytoplasm) features."
        ),
    ] = "infer",
    threads: Annotated[
        int,
        typer.Option(help="DuckDB threads. Pass the task's CPU count."),
    ] = DEFAULT_THREADS,
    memory_limit: Annotated[
        str | None,
        typer.Option(
            help="DuckDB memory_limit (e.g. 6GB). Set below the task's memory so DuckDB "
            "spills instead of being OOM-killed."
        ),
    ] = None,
    temp_directory: Annotated[
        str | None,
        typer.Option(
            help="DuckDB spill directory for out-of-core aggregation. Defaults to the system "
            "temp dir (TMPDIR). Point at a large volume when node-local disk is small."
        ),
    ] = None,
) -> None:
    """Aggregate single-cell profiles to per-group medians (drop-in for pycytominer aggregate)."""
    feature_list = None if features.strip().lower() == "infer" else _split_csv(features)
    try:
        aggregate_median(
            source_path,
            dest_path,
            strata=_split_csv(strata),
            features=feature_list,
            threads=threads,
            memory_limit=memory_limit,
            temp_directory=temp_directory,
        )
    except (ValueError, duckdb.Error) as exception:
        typer.secho(f"aggregate failed: {exception}", fg=typer.colors.RED)
        raise typer.Exit(1) from exception

    typer.secho(f"{source_path} → {dest_path}", fg=typer.colors.GREEN)
