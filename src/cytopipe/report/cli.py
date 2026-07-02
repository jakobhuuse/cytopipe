"""``cytopipe report`` — render the four standard Cell Painting figures from a results tree."""

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from . import figures
from .data import ProfileSet, discover_profiles, load_profiles, plate_well_values
from .theme import apply_theme


class Engine(StrEnum):
    auto = "auto"
    deepprofiler = "deepprofiler"
    cellprofiler = "cellprofiler"


class ImageFormat(StrEnum):
    png = "png"
    svg = "svg"


def _parse_only(only: str | None) -> set[int]:
    if not only:
        return {1, 2, 3, 4}
    try:
        chosen = {int(part) for part in only.split(",") if part.strip()}
    except ValueError as exception:
        raise typer.BadParameter("--only must be a comma-separated list, e.g. 1,3,4") from exception
    invalid = chosen - {1, 2, 3, 4}
    if invalid:
        raise typer.BadParameter(f"--only figures must be in 1-4, got {sorted(invalid)}")
    return chosen


def _emit(label: str, build: Callable[[], Path]) -> None:
    """Run one figure builder, reporting written/skipped/failed without aborting the others."""
    try:
        path = build()
    except figures.FigureSkipped as skip:
        typer.secho(f"{label}: skipped ({skip})", fg=typer.colors.YELLOW)
    except Exception as error:  # noqa: BLE001 — one bad figure shouldn't kill the report
        typer.secho(f"{label}: failed ({error})", fg=typer.colors.RED)
    else:
        typer.secho(f"{label} → {path}", fg=typer.colors.GREEN)


def report_command(
    results_dir: Annotated[
        Path,
        typer.Argument(help="Results tree, experiment dir, or engine dir.", exists=True),
    ],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory for figures.")] = Path(
        "report"
    ),
    engine: Annotated[
        Engine, typer.Option(help="Which engine's profiles (auto-detected by default).")
    ] = Engine.auto,
    only: Annotated[
        str | None, typer.Option(help="Comma list of figures to render (1-4); default all.")
    ] = None,
    top_n: Annotated[
        int, typer.Option(help="Compounds in the similarity clustermap (0 = all).")
    ] = 50,
    fmt: Annotated[ImageFormat, typer.Option("--format", help="Image format.")] = ImageFormat.png,
) -> None:
    """Render plate heatmaps, a UMAP embedding, replicate reproducibility, and a clustermap."""
    try:
        profiles: ProfileSet = discover_profiles(results_dir, engine.value)
    except (FileNotFoundError, ValueError) as exception:
        typer.secho(f"report failed: {exception}", fg=typer.colors.RED)
        raise typer.Exit(1) from exception

    selected = _parse_only(only)
    out.mkdir(parents=True, exist_ok=True)
    apply_theme()
    ext = fmt.value
    typer.secho(f"Profiles: {profiles.engine} @ {profiles.root}", fg=typer.colors.CYAN)

    # Load the well-level cohort once; shared by figures 2 and 3.
    cohort = load_profiles(profiles.cohort_source()) if selected & {2, 3} else None

    if 1 in selected:
        plates, value_label = plate_well_values(profiles)
        _emit("1 plate heatmaps", lambda: figures.plate_heatmaps(plates, value_label, out, ext))
    if 2 in selected:
        _emit("2 UMAP embedding", lambda: figures.embedding_umap(cohort, out, ext))
    if 3 in selected:
        _emit(
            "3 replicate reproducibility",
            lambda: figures.replicate_reproducibility(cohort, out, ext),
        )
    if 4 in selected:
        _emit(
            "4 similarity clustermap",
            lambda: figures.similarity_clustermap(profiles.consensus, out, ext, top_n),
        )
