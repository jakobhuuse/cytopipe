"""
Tests for cytopipe.loaddata.filter.
Dropping excluded (Plate, Well, Site) image sets from a built LoadData table.
"""

import pandas as pd

from cytopipe.loaddata.build import build_loaddata
from cytopipe.loaddata.filter import filter_loaddata
from cytopipe.loaddata.scan import scan_images


def _table(tmp_path, make_plate):
    df = scan_images(make_plate(tmp_path, sites=(1, 2, 3)))
    return build_loaddata(df, "26159")


def test_filter_loaddata_drops_matching_rows(tmp_path, make_plate):
    table = _table(tmp_path, make_plate)  # 3 image sets, sites 1/2/3
    excluded = pd.DataFrame(
        {"Metadata_Plate": ["26159"], "Metadata_Well": ["A02"], "Metadata_Site": [2]}
    )

    filtered = filter_loaddata(table, excluded)

    assert len(filtered) == 2
    assert set(filtered["Metadata_Site"]) == {1, 3}


def test_filter_loaddata_empty_exclude_is_a_no_op(tmp_path, make_plate):
    table = _table(tmp_path, make_plate)
    excluded = pd.DataFrame(columns=["Metadata_Plate", "Metadata_Well", "Metadata_Site"])

    filtered = filter_loaddata(table, excluded)

    assert len(filtered) == len(table)
    pd.testing.assert_frame_equal(filtered, table.reset_index(drop=True))


def test_filter_loaddata_only_matches_full_plate_well_site_triple(tmp_path, make_plate):
    table = _table(tmp_path, make_plate)
    # Different plate id, same well/site, must not match anything in this plate's table.
    excluded = pd.DataFrame(
        {"Metadata_Plate": ["other-plate"], "Metadata_Well": ["A02"], "Metadata_Site": [1]}
    )

    filtered = filter_loaddata(table, excluded)

    assert len(filtered) == len(table)
