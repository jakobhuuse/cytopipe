"""
Tests for cytopipe.bridge.platemap. 
Plate-map loading and joining onto the index.
"""

import pandas as pd
import pytest

from cytopipe.bridge.platemap import duplicate_keys, join_platemap, load_platemap, unmatched_wells


def test_load_platemap_strips_header_and_cell_whitespace(platemap_small):
    pm = load_platemap(platemap_small)
    assert list(pm.columns) == ["PlateID", "Well", "pert_name", "Split"]
    # Values are stripped of the leading whitespace present in the CSV.
    assert pm["Well"].tolist() == ["A02", "B05"]
    assert pm["pert_name"].tolist() == ["JUN_WT.2", "EMPTY_"]


def test_platemap_join_and_unmatched(platemap_small):
    index = pd.DataFrame(
        {"Metadata_Plate": ["26159", "26159"], "Metadata_Well": ["A02", "Z99"], "DNA": ["a", "b"]}
    )
    pm = load_platemap(platemap_small)
    missing = unmatched_wells(index, pm, plate_col="PlateID", well_col="Well")
    assert missing == ["26159/Z99"]

    joined = join_platemap(index, pm, plate_col="PlateID", well_col="Well", cols=None)
    assert joined.loc[joined["Metadata_Well"] == "A02", "pert_name"].iloc[0] == "JUN_WT.2"
    # Unmatched well gets NaN annotations, but the row is kept.
    assert joined["Metadata_Well"].tolist() == ["A02", "Z99"]
    # Redundant right-side key columns are dropped.
    assert "PlateID" not in joined.columns


def test_platemap_join_selects_columns(platemap_small):
    index = pd.DataFrame({"Metadata_Plate": ["26159"], "Metadata_Well": ["A02"], "DNA": ["a"]})
    pm = load_platemap(platemap_small)
    joined = join_platemap(index, pm, plate_col="PlateID", well_col="Well", cols=["pert_name"])
    assert "pert_name" in joined.columns
    assert "Split" not in joined.columns  # not requested, so not carried over


def test_platemap_join_unknown_column_errors(platemap_small):
    index = pd.DataFrame({"Metadata_Plate": ["26159"], "Metadata_Well": ["A02"], "DNA": ["a"]})
    pm = load_platemap(platemap_small)
    with pytest.raises(KeyError, match="nope"):
        join_platemap(index, pm, plate_col="PlateID", well_col="Well", cols=["nope"])


def test_duplicate_keys_finds_repeated_well(platemap_small):
    pm = load_platemap(platemap_small)
    dupe_row = pm.iloc[[0]]  # duplicate the A02/26159 row
    pm_with_dupe = pd.concat([pm, dupe_row], ignore_index=True)

    assert duplicate_keys(pm_with_dupe, plate_col="PlateID", well_col="Well") == ["26159/A02"]
    assert duplicate_keys(pm, plate_col="PlateID", well_col="Well") == []


def test_join_platemap_raises_on_duplicate_key(platemap_small):
    index = pd.DataFrame({"Metadata_Plate": ["26159"], "Metadata_Well": ["A02"], "DNA": ["a"]})
    pm = load_platemap(platemap_small)
    pm_with_dupe = pd.concat([pm, pm.iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="26159/A02"):
        join_platemap(index, pm_with_dupe, plate_col="PlateID", well_col="Well", cols=None)


def test_platemap_well_only_join_ignores_plate(platemap_small):
    # plate_col=None joins on well alone: a differing plate still matches by well.
    index = pd.DataFrame({"Metadata_Plate": ["99999"], "Metadata_Well": ["A02"], "DNA": ["a"]})
    pm = load_platemap(platemap_small)
    assert unmatched_wells(index, pm, plate_col=None, well_col="Well") == []
    joined = join_platemap(index, pm, plate_col=None, well_col="Well", cols=["pert_name"])
    assert joined["pert_name"].iloc[0] == "JUN_WT.2"
