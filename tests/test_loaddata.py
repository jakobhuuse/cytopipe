"""Unit + end-to-end tests for the CellProfiler LoadData CSV generator."""

from pathlib import Path

import pandas as pd
import pytest

from cytopipe.loaddata import generate_loaddata
from cytopipe.loaddata.build import build_loaddata
from cytopipe.loaddata.scan import CHANNEL_BY_NUMBER, scan_images

CHANNELS = list(CHANNEL_BY_NUMBER.values())  # DNA, Mito, AGP, RNA, ER


def _make_plate(root: Path, wells=("A02",), sites=(1, 2), channels=(1, 2, 3, 4, 5)) -> Path:
    """Create a TimePoint_1/ tree of empty channel TIFFs named per the project convention."""
    tp = root / "TimePoint_1"
    tp.mkdir(parents=True)
    for well in wells:
        for site in sites:
            for ch in channels:
                (tp / f"2025-W51_{well}_s{site}_w{ch}ABCDEF.tif").touch()
    (tp / "2025-W51_A02_s1_w1_thumbXYZ.tif").touch()  # thumbnail, must be ignored
    return root


def test_scan_skips_thumbnails_and_parses(tmp_path):
    _make_plate(tmp_path)
    df = scan_images(tmp_path)
    assert len(df) == 10  # 2 sites × 5 channels; thumbnail excluded
    assert set(df["ChannelNumber"]) == set(CHANNEL_BY_NUMBER)
    assert not df["FileName"].str.contains("_thumb").any()


def test_scan_no_matching_images_errors(tmp_path):
    (tmp_path / "notes.txt").touch()
    with pytest.raises(FileNotFoundError):
        scan_images(tmp_path)


def test_build_loaddata_columns_and_tokens(tmp_path):
    df = scan_images(_make_plate(tmp_path))
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


def test_build_loaddata_with_illum(tmp_path):
    df = scan_images(_make_plate(tmp_path))
    table = build_loaddata(df, "26159", images_token="__IMAGES__", with_illum=True)
    for ch in CHANNELS:
        assert table[f"Image_FileName_Illum{ch}"].iloc[0] == f"Illum{ch}.npy"
        assert (table[f"Image_PathName_Illum{ch}"] == "__ILLUM__").all()


def test_build_loaddata_missing_channel_errors(tmp_path):
    df = scan_images(_make_plate(tmp_path, channels=(1, 2, 3, 4)))  # missing w5/ER
    with pytest.raises(ValueError, match="w5"):
        build_loaddata(df, "26159", images_token="__IMAGES__")


def test_generate_loaddata_end_to_end(tmp_path):
    plate_dir = _make_plate(tmp_path / "26159")
    out = tmp_path / "ld.csv"

    result = generate_loaddata(plate_dir, out)
    assert result.plate == "26159"  # inferred from the dir name
    assert result.n_image_sets == 2
    assert result.with_illum is False

    table = pd.read_csv(out)
    assert len(table) == 2
    assert "Image_FileName_OrigDNA" in table.columns
    assert "Image_FileName_IllumDNA" not in table.columns
