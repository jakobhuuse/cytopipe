"""Shared fixtures. Fixture-data paths and synthetic-data factories used across modules."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def measurement_dir() -> Path:
    """CellProfiler ``measurement/`` dir for plate 26159 (well A02, 2 sites)."""
    return FIXTURES / "cellprofiler" / "26159" / "measurement"


@pytest.fixture
def platemap_default() -> Path:
    return FIXTURES / "platemap_default.csv"


@pytest.fixture
def platemap_small() -> Path:
    return FIXTURES / "platemap_small.csv"


@pytest.fixture
def make_plate():
    """Factory building a ``TimePoint_1/`` tree of empty channel TIFFs (project naming)."""

    def _make(root: Path, wells=("A02",), sites=(1, 2), channels=(1, 2, 3, 4, 5)) -> Path:
        tp = root / "TimePoint_1"
        tp.mkdir(parents=True)
        for well in wells:
            for site in sites:
                for ch in channels:
                    (tp / f"2025-W51_{well}_s{site}_w{ch}ABCDEF.tif").touch()
        (tp / "2025-W51_A02_s1_w1_thumbXYZ.tif").touch()  # thumbnail, must be ignored
        return root

    return _make


@pytest.fixture
def synthetic_cohort():
    """Factory: well-level normalized-style frame (Metadata_* + efficientnet_*) with signal."""

    def _make(
        n_plates=3, wells_per_plate=16, n_compounds=6, n_features=40, seed=0
    ) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        compounds = ["DMSO", *[f"HY-{i:03d}" for i in range(1, n_compounds)]]
        centers = {c: rng.normal(size=n_features) for c in compounds}
        rows = []
        for plate in range(n_plates):
            plate_id = 26157 + plate
            for well_i in range(wells_per_plate):
                compound = compounds[well_i % n_compounds]
                row, col = divmod(well_i, 12)
                features = centers[compound] + rng.normal(scale=0.3, size=n_features)
                rows.append(
                    {
                        "Metadata_Plate": plate_id,
                        "Metadata_Well": f"{chr(ord('A') + row)}{col + 1:02d}",
                        "Metadata_Compound": compound,
                        **{f"efficientnet_{j + 1}": features[j] for j in range(n_features)},
                    }
                )
        return pd.DataFrame(rows)

    return _make
