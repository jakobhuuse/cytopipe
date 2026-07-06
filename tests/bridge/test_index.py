"""
Tests for cytopipe.bridge.index. 
Image-table reading and DeepProfiler index building.
"""

import pandas as pd
import pytest

from cytopipe.bridge.index import CHANNEL_ORDER, build_index, read_image_table, write_index


def test_read_image_table_single_file(measurement_dir):
    df = read_image_table(measurement_dir / "Image.csv")
    assert len(df) == 2
    assert "Metadata_Well" in df.columns  # header whitespace stripped


def test_read_image_table_concats_directory(tmp_path):
    cols = "Metadata_Plate,Metadata_Well,Metadata_Site," + ",".join(
        f"FileName_Orig{c}" for c in CHANNEL_ORDER
    )
    image_csv = tmp_path / "image_csv"
    image_csv.mkdir()
    (image_csv / "26159.1.Image.csv").write_text(f"{cols}\n26159,A02,1,a,b,c,d,e\n")
    (image_csv / "26159.2.Image.csv").write_text(f"{cols}\n26159,A02,2,a,b,c,d,e\n")

    df = read_image_table(image_csv)
    assert len(df) == 2  # rows unioned across the per-chunk CSVs
    assert sorted(df["Metadata_Site"]) == [1, 2]


def test_read_image_table_empty_dir_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_image_table(tmp_path)


def test_build_index_uses_named_channel_columns_in_fixed_order(measurement_dir):
    image_table = pd.read_csv(measurement_dir / "Image.csv", skipinitialspace=True)
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


def test_build_index_sorted_by_well_then_site(measurement_dir):
    image_table = pd.read_csv(measurement_dir / "Image.csv", skipinitialspace=True)
    index = build_index(image_table, plate="26159")
    assert index["Metadata_Site"].tolist() == [1, 2]  # sorted despite source row order (2, 1)


def test_build_index_missing_channel_column_errors():
    image_table = pd.DataFrame(
        {"Metadata_Well": ["A02"], "Metadata_Site": [1], "FileName_OrigDNA": ["x.tiff"]}
    )
    with pytest.raises(KeyError, match="FileName_OrigRNA"):
        build_index(image_table, plate="26159")


def test_write_index_writes_to_metadata_subdir(tmp_path):
    index = pd.DataFrame({"Metadata_Well": ["A02"], "Metadata_Site": [1]})
    out = write_index(index, tmp_path)
    assert out == tmp_path / "metadata" / "index.csv"
    assert pd.read_csv(out)["Metadata_Well"].tolist() == ["A02"]
