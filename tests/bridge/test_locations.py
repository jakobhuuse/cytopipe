"""
Tests for cytopipe.bridge.locations. 
Nuclei-location cleaning and tree conversion.
"""

import pyarrow as pa

from cytopipe.bridge.locations import DST_X, DST_Y, clean_nuclei_locations, convert_locations_tree


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


def test_convert_locations_tree_writes_bare_header_files(measurement_dir, tmp_path):
    n = convert_locations_tree(measurement_dir, tmp_path, "26159")

    assert n == 2  # A02-1-Nuclei.csv and A02-2-Nuclei.csv
    out = tmp_path / "locations" / "26159" / "A02-1-Nuclei.csv"
    assert out.exists()
    # DeepProfiler expects a bare, unquoted header line.
    assert out.read_text().splitlines()[0] == f"{DST_X},{DST_Y}"


def test_convert_locations_tree_no_sources_returns_zero(tmp_path):
    (tmp_path / "locations").mkdir()
    assert convert_locations_tree(tmp_path, tmp_path / "out", "26159") == 0
