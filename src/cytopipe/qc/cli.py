"""cytopipe qc. Aggregate QC metrics and build a review gallery."""

from pathlib import Path
from typing import Annotated

import typer

from . import build_gallery, scan_qc_metrics


def qc_review_command(
    qc_dir: Annotated[
        Path,
        typer.Argument(
            help="Published qc/<plate> dir (chunk*/QCb3/*/Image.csv, chunk*/Overlays/*.png).",
            exists=True,
            file_okay=False,
        ),
    ],
    out_dir: Annotated[
        Path, typer.Option("--out-dir", "-o", help="Where to write gallery.html.")
    ] = Path("qc-review"),
) -> None:
    """Scan a plate's QC output and write a review gallery."""
    try:
        metrics = scan_qc_metrics(qc_dir)
    except FileNotFoundError as exception:
        typer.secho(f"qc review failed: {exception}", fg=typer.colors.RED)
        raise typer.Exit(1) from exception

    out_dir.mkdir(parents=True, exist_ok=True)
    gallery_path = build_gallery(metrics, out_dir / "gallery.html")

    typer.secho(f"{len(metrics)} images scanned", fg=typer.colors.GREEN)
    typer.secho(f"gallery -> {gallery_path}", fg=typer.colors.GREEN)
