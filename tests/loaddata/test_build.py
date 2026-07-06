"""
Tests for cytopipe.loaddata.build.
Pivoting scanned images into a LoadData table.
"""

import pandas as pd
import pytest

from cytopipe.loaddata.build import build_loaddata, write_loaddata
from cytopipe.loaddata.scan import CHANNEL_BY_NUMBER, scan_images

CHANNELS = list(CHANNEL_BY_NUMBER.values())  # DNA, Mito, AGP, RNA, ER


def test_build_loaddata_columns_and_tokens(tmp_path, make_plate):
    df = scan_images(make_plate(tmp_path))
    table = build_loaddata(df, "26159", images_token="__IMAGES__")

    assert len(table) == 2  # one row per image set
    for ch in CHANNELS:
        assert f"Image_FileName_Orig{ch}" in table.columns
        assert (table[f"Image_PathName_Orig{ch}"] == "__IMAGES__").all()
        assert f"Image_FileName_Illum{ch}" not in table.columns  # no illum unless asked

    first = table.iloc[0]
    assert [first["Metadata_Plate"], first["Metadata_Well"], first["Metadata_Site"]] == [
        "26159",
        "A02",
        1,
    ]
    # Channel name must follow ChannelNumber (Mito = w2), not a w-number guess.
    assert first["Image_FileName_OrigMito"].endswith("_w2ABCDEF.tif")
    assert first["Image_FileName_OrigER"].endswith("_w5ABCDEF.tif")


def test_build_loaddata_with_illum(tmp_path, make_plate):
    df = scan_images(make_plate(tmp_path))
    table = build_loaddata(df, "26159", images_token="__IMAGES__", with_illum=True)
    for ch in CHANNELS:
        assert table[f"Image_FileName_Illum{ch}"].iloc[0] == f"Illum{ch}.npy"
        assert (table[f"Image_PathName_Illum{ch}"] == "__ILLUM__").all()


def test_build_loaddata_missing_channel_errors(tmp_path, make_plate):
    df = scan_images(make_plate(tmp_path, channels=(1, 2, 3, 4)))  # missing w5/ER
    with pytest.raises(ValueError, match="w5"):
        build_loaddata(df, "26159", images_token="__IMAGES__")


def test_write_loaddata_roundtrips(tmp_path, make_plate):
    table = build_loaddata(scan_images(make_plate(tmp_path)), "26159", images_token="__IMAGES__")
    out = tmp_path / "nested" / "ld.csv"
    written = write_loaddata(table, out)
    assert written == out
    assert out.exists()  # parent dir created
    assert len(pd.read_csv(out)) == 2
