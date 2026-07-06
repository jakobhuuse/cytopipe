"""Generate a CellProfiler LoadData CSV from a plate's raw channel images."""

from dataclasses import dataclass
from pathlib import Path

from .build import build_loaddata, write_loaddata
from .scan import scan_images

__all__ = ["generate_loaddata", "LoadDataResult"]


@dataclass
class LoadDataResult:
    plate: str
    n_image_sets: int
    with_illum: bool

    def summary(self) -> str:
        """One-line description of what was generated."""
        kind = "with illum" if self.with_illum else "no illum"
        return f"plate {self.plate}: {self.n_image_sets} image sets ({kind})"


def generate_loaddata(
    input_dir: Path,
    output_csv: Path,
    *,
    plate: str | None = None,
    with_illum: bool = False,
    images_token: str = "__IMAGES__",
    illum_token: str = "__ILLUM__",
) -> LoadDataResult:
    """Scan a plate's raw channel TIFFs and write a CellProfiler LoadData CSV."""
    input_dir = Path(input_dir)
    plate = plate or input_dir.resolve().name
    images = scan_images(input_dir)
    table = build_loaddata(
        images,
        plate,
        images_token=images_token,
        with_illum=with_illum,
        illum_token=illum_token,
    )
    write_loaddata(table, output_csv)
    return LoadDataResult(plate=plate, n_image_sets=len(table), with_illum=with_illum)
