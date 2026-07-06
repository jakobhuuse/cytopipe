"""Tests for the bridge orchestration (cytopipe.bridge.__init__)."""

import shutil

import pandas as pd

from cytopipe.bridge import BridgeResult, bridge
from cytopipe.bridge.index import CHANNEL_ORDER, read_image_table
from cytopipe.bridge.locations import DST_X

CORE_COLS = ["Metadata_Plate", "Metadata_Well", "Metadata_Site", *CHANNEL_ORDER]


# BridgeResult


def test_bridge_result_summary_and_no_warning():
    result = BridgeResult(plate="26159", n_location_files=2, n_sites=2)
    assert "26159" in result.summary()
    assert "2 location files" in result.summary()
    assert result.warning() is None


def test_bridge_result_warning_lists_unmatched_wells():
    result = BridgeResult(
        plate="26159", n_location_files=1, n_sites=1, unmatched_wells=["26159/Z99"]
    )
    warning = result.warning()
    assert warning is not None
    assert "26159/Z99" in warning


# E2E


def test_bridge_end_to_end(measurement_dir, platemap_default, tmp_path):
    result = bridge(measurement_dir, tmp_path, platemap_default)

    assert result.plate == "26159"  # inferred from the Image table's Metadata_Plate
    assert result.n_location_files == 2
    assert result.n_sites == 2
    assert not result.unmatched_wells

    loc_path = tmp_path / "locations" / "26159" / "A02-1-Nuclei.csv"
    # Bare, unquoted header — matches DeepProfiler's reference locations files.
    assert loc_path.read_text().splitlines()[0] == f"{DST_X},Nuclei_Location_Center_Y"
    loc = pd.read_csv(loc_path)
    assert loc[DST_X].tolist() == [119, 417, 388]
    assert loc[DST_X].dtype.kind == "i"

    index = pd.read_csv(tmp_path / "metadata" / "index.csv")
    # Core columns come first, then the default treatment + replicate annotations.
    assert list(index.columns) == [*CORE_COLS, "Metadata_Compound", "Metadata_Batch"]
    assert index.loc[index["Metadata_Site"] == 1, "Mito"].iloc[0] == "26159/A02_s1_w2.tiff"
    assert index.loc[index["Metadata_Site"] == 1, "Metadata_Compound"].iloc[0] == "DMSO"


def test_bridge_is_idempotent(measurement_dir, platemap_default, tmp_path):
    bridge(measurement_dir, tmp_path, platemap_default)
    first = (tmp_path / "metadata" / "index.csv").read_bytes()
    bridge(measurement_dir, tmp_path, platemap_default)
    assert (tmp_path / "metadata" / "index.csv").read_bytes() == first


def test_bridge_accepts_plate_dir(measurement_dir, platemap_default, tmp_path):
    # Passing the plate dir (which contains measurement/) also works.
    result = bridge(measurement_dir.parent, tmp_path, platemap_default)
    assert result.n_sites == 2


def test_bridge_accepts_chunked_image_csv_dir(measurement_dir, platemap_default, tmp_path):
    # Reassembled per-chunk Image tables arrive under measurement/image_csv/, not Image.csv.
    measurement = tmp_path / "measurement"
    (measurement / "image_csv").mkdir(parents=True)
    (measurement / "locations").mkdir()

    full = read_image_table(measurement_dir / "Image.csv")
    for site, group in full.groupby("Metadata_Site"):
        group.to_csv(measurement / "image_csv" / f"26159.{site}.Image.csv", index=False)
    for loc in (measurement_dir / "locations").glob("*-Nuclei.csv"):
        shutil.copy(loc, measurement / "locations" / loc.name)

    result = bridge(measurement, tmp_path / "out", platemap_default)
    assert result.plate == "26159"
    assert result.n_sites == 2
    index = pd.read_csv(tmp_path / "out" / "metadata" / "index.csv")
    assert index.loc[index["Metadata_Site"] == 1, "Mito"].iloc[0] == "26159/A02_s1_w2.tiff"
