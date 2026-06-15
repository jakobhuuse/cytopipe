"""Unit + end-to-end tests for the CellProfiler → DeepProfiler bridge."""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from cytopipe.bridge import run_bridge
from cytopipe.bridge.index import CHANNEL_ORDER, build_index
from cytopipe.bridge.locations import DST_X, DST_Y, clean_nuclei_locations
from cytopipe.bridge.platemap import join_platemap, load_platemap, unmatched_wells

FIXTURES = Path(__file__).parent / "fixtures"
MEASUREMENT = FIXTURES / "cellprofiler" / "26159" / "measurement"
PLATEMAP = FIXTURES / "platemap_default.csv"

CORE_COLS = ["Metadata_Plate", "Metadata_Well", "Metadata_Site", *CHANNEL_ORDER]


def test_clean_nuclei_locations_renames_drops_and_rounds():
    table = pa.table(
        {
            "ImageNumber": [1, 1],
            "ObjectNumber": [1, 2],
            "Location_Center_X": [119.16, 416.87],
            "Location_Center_Y": [15.32, 8.54],
        }
    )
    out = clean_nuclei_locations(table)
    assert out.column_names == [DST_X, DST_Y]
    assert out.column(DST_X).to_pylist() == [119, 417]
    assert out.column(DST_Y).to_pylist() == [15, 9]
    assert pa.types.is_integer(out.schema.field(DST_X).type)


def test_clean_nuclei_locations_no_round_keeps_float():
    table = pa.table({"Location_Center_X": [1.5], "Location_Center_Y": [2.5]})
    out = clean_nuclei_locations(table, as_int=False)
    assert out.column(DST_X).to_pylist() == [1.5]


def test_build_index_uses_named_channel_columns_in_fixed_order():
    image_table = pd.read_csv(MEASUREMENT / "image.csv", skipinitialspace=True)
    index = build_index(image_table, plate="26159")

    assert list(index.columns) == [
        "Metadata_Plate",
        "Metadata_Well",
        "Metadata_Site",
        *CHANNEL_ORDER,
    ]
    # Mito must come from FileName_OrigMito (w2 in this dataset), NOT a w-number guess (w5).
    mito_site1 = index.loc[index["Metadata_Site"] == 1, "Mito"].iloc[0]
    assert mito_site1 == "26159/A02_s1_w2.tiff"
    # ER comes from FileName_OrigER (w5).
    assert index.loc[index["Metadata_Site"] == 1, "ER"].iloc[0] == "26159/A02_s1_w5.tiff"


def test_build_index_sorted_by_well_then_site():
    image_table = pd.read_csv(MEASUREMENT / "image.csv", skipinitialspace=True)
    index = build_index(image_table, plate="26159")
    assert index["Metadata_Site"].tolist() == [1, 2]


def test_build_index_missing_channel_column_errors():
    image_table = pd.DataFrame(
        {"Metadata_Well": ["A02"], "Metadata_Site": [1], "FileName_OrigDNA": ["x.tiff"]}
    )
    with pytest.raises(KeyError, match="FileName_OrigRNA"):
        build_index(image_table, plate="26159")


def test_platemap_join_and_unmatched():
    index = pd.DataFrame(
        {"Metadata_Plate": ["26159", "26159"], "Metadata_Well": ["A02", "Z99"], "DNA": ["a", "b"]}
    )
    pm = load_platemap(FIXTURES / "platemap_small.csv")
    missing = unmatched_wells(index, pm, plate_col="PlateID", well_col="Well")
    assert missing == ["26159/Z99"]

    joined = join_platemap(index, pm, plate_col="PlateID", well_col="Well", cols=None)
    assert joined.loc[joined["Metadata_Well"] == "A02", "pert_name"].iloc[0] == "JUN_WT.2"
    # Unmatched well gets NaN annotations, but the row is kept.
    assert joined["Metadata_Well"].tolist() == ["A02", "Z99"]
    # Redundant right-side key columns are dropped.
    assert "PlateID" not in joined.columns


def test_platemap_join_selects_columns():
    index = pd.DataFrame({"Metadata_Plate": ["26159"], "Metadata_Well": ["A02"], "DNA": ["a"]})
    pm = load_platemap(FIXTURES / "platemap_small.csv")
    joined = join_platemap(index, pm, plate_col="PlateID", well_col="Well", cols=["pert_name"])
    assert "pert_name" in joined.columns
    assert "Split" not in joined.columns  # not requested, so not carried over


def test_platemap_join_unknown_column_errors():
    index = pd.DataFrame({"Metadata_Plate": ["26159"], "Metadata_Well": ["A02"], "DNA": ["a"]})
    pm = load_platemap(FIXTURES / "platemap_small.csv")
    with pytest.raises(KeyError, match="nope"):
        join_platemap(index, pm, plate_col="PlateID", well_col="Well", cols=["nope"])


def test_run_bridge_end_to_end(tmp_path):
    result = run_bridge(MEASUREMENT, tmp_path, PLATEMAP)

    assert result.plate == "26159"  # inferred from the Image table's Metadata_Plate
    assert result.n_location_files == 2
    assert result.n_sites == 2
    assert not result.unmatched_wells

    loc_path = tmp_path / "locations" / "26159" / "A02-1-Nuclei.csv"
    # Bare, unquoted header — matches DeepProfiler's reference locations files.
    assert loc_path.read_text().splitlines()[0] == f"{DST_X},{DST_Y}"
    loc = pd.read_csv(loc_path)
    assert list(loc.columns) == [DST_X, DST_Y]
    assert loc[DST_X].tolist() == [119, 417, 388]
    assert loc[DST_X].dtype.kind == "i"

    index = pd.read_csv(tmp_path / "metadata" / "index.csv")
    # Core columns come first, then the default treatment + replicate annotations.
    assert list(index.columns) == [*CORE_COLS, "Metadata_Compound", "Metadata_Batch"]
    assert index.loc[index["Metadata_Site"] == 1, "Mito"].iloc[0] == "26159/A02_s1_w2.tiff"
    assert index.loc[index["Metadata_Site"] == 1, "Metadata_Compound"].iloc[0] == "DMSO"


def test_run_bridge_is_idempotent(tmp_path):
    run_bridge(MEASUREMENT, tmp_path, PLATEMAP)
    first = (tmp_path / "metadata" / "index.csv").read_bytes()
    run_bridge(MEASUREMENT, tmp_path, PLATEMAP)
    assert (tmp_path / "metadata" / "index.csv").read_bytes() == first


def test_run_bridge_accepts_plate_dir(tmp_path):
    # Passing the plate dir (which contains measurement/) also works.
    result = run_bridge(MEASUREMENT.parent, tmp_path, PLATEMAP)
    assert result.n_sites == 2
