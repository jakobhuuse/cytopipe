"""
Tests for cytopipe.loaddata.build.
Pivoting scanned images into a LoadData table.
"""

import pandas as pd
import pytest

from cytopipe.loaddata.build import (
    build_loaddata,
    image_filenames,
    write_chunks,
    write_loaddata,
)
from cytopipe.loaddata.scan import CHANNEL_BY_NUMBER, scan_images

CHANNELS = list(CHANNEL_BY_NUMBER.values())  # DNA, Mito, AGP, RNA, ER


def test_build_loaddata_columns_and_paths(tmp_path, make_plate):
    df = scan_images(make_plate(tmp_path))
    table = build_loaddata(df, "26159")

    assert len(table) == 2  # one row per image set
    for ch in CHANNELS:
        assert f"Image_FileName_Orig{ch}" in table.columns
        # PathName is the input-folder-relative subdir CellProfiler resolves via -i.
        assert (table[f"Image_PathName_Orig{ch}"] == "images").all()
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
    table = build_loaddata(df, "26159", with_illum=True)
    for ch in CHANNELS:
        assert table[f"Image_FileName_Illum{ch}"].iloc[0] == f"Illum{ch}.npy"
        assert (table[f"Image_PathName_Illum{ch}"] == "illum").all()


def test_build_loaddata_missing_channel_errors(tmp_path, make_plate):
    df = scan_images(make_plate(tmp_path, channels=(1, 2, 3, 4)))  # missing w5/ER
    with pytest.raises(ValueError, match="w5"):
        build_loaddata(df, "26159")


def test_write_loaddata_roundtrips(tmp_path, make_plate):
    table = build_loaddata(scan_images(make_plate(tmp_path)), "26159")
    out = tmp_path / "nested" / "ld.csv"
    written = write_loaddata(table, out)
    assert written == out
    assert out.exists()  # parent dir created
    assert len(pd.read_csv(out)) == 2


def test_image_filenames_lists_only_orig_channels(tmp_path, make_plate):
    # with_illum adds Image_FileName_Illum* cols; those are generated, not staged, so excluded.
    table = build_loaddata(scan_images(make_plate(tmp_path)), "26159", with_illum=True)
    names = image_filenames(table)
    assert len(names) == 10  # 2 image sets x 5 channels, all raw .tif
    assert all(n.endswith(".tif") for n in names)
    assert not any("Illum" in n for n in names)


def test_write_chunks_splits_csv_and_manifest(tmp_path, make_plate):
    table = build_loaddata(scan_images(make_plate(tmp_path)), "26159")  # 2 image sets
    chunk_dir = tmp_path / "chunks"
    n = write_chunks(table, chunk_dir, chunk_size=1)

    assert n == 2  # one image set per chunk
    for i in (1, 2):
        rows = pd.read_csv(chunk_dir / f"chunk{i}.load_data.csv")
        assert len(rows) == 1
        manifest = (chunk_dir / f"chunk{i}.images.txt").read_text().splitlines()
        assert len(manifest) == 5  # the 5 channel tifs that image set references
        assert set(manifest) == set(image_filenames(rows))


def test_write_chunks_uneven_last_chunk(tmp_path, make_plate):
    table = build_loaddata(scan_images(make_plate(tmp_path, sites=(1, 2, 3))), "26159")  # 3 sets
    n = write_chunks(table, tmp_path / "chunks", chunk_size=2)
    assert n == 2  # ceil(3 / 2)
    assert len(pd.read_csv(tmp_path / "chunks" / "chunk2.load_data.csv")) == 1  # remainder
