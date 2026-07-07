"""Generate a CellProfiler LoadData CSV from a plate's raw channel images."""

from dataclasses import dataclass
from pathlib import Path

from .build import build_loaddata, write_chunks, write_loaddata
from .scan import scan_images

__all__ = ["generate_loaddata", "LoadDataResult"]


@dataclass
class LoadDataResult:
    plate: str
    n_image_sets: int
    with_illum: bool
    n_chunks: int = 0

    def summary(self) -> str:
        """One-line description of what was generated."""
        kind = "with illum" if self.with_illum else "no illum"
        chunks = f", {self.n_chunks} chunks" if self.n_chunks else ""
        return f"plate {self.plate}: {self.n_image_sets} image sets ({kind}){chunks}"


def generate_loaddata(
    input_dir: Path,
    output_csv: Path,
    *,
    plate: str | None = None,
    with_illum: bool = False,
    chunk_size: int = 0,
    images_subdir: str = "images",
    illum_subdir: str = "illum",
) -> LoadDataResult:
    """Scan a plate's raw TIFFs and write its LoadData CSV, plus a ``chunks/`` dir when
    ``chunk_size > 0``.
    """
    input_dir = Path(input_dir)
    output_csv = Path(output_csv)
    plate = plate or input_dir.resolve().name
    images = scan_images(input_dir)
    table = build_loaddata(
        images,
        plate,
        images_subdir=images_subdir,
        with_illum=with_illum,
        illum_subdir=illum_subdir,
    )
    write_loaddata(table, output_csv)
    n_chunks = 0
    if chunk_size > 0:
        n_chunks = write_chunks(table, output_csv.parent / "chunks", chunk_size)
    return LoadDataResult(
        plate=plate, n_image_sets=len(table), with_illum=with_illum, n_chunks=n_chunks
    )
