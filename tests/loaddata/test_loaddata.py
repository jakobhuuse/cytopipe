"""
Tests for the loaddata orchestration (cytopipe.loaddata.__init__).
End-to-end + result.
"""

import pandas as pd

from cytopipe.loaddata import LoadDataResult, generate_loaddata


def test_loaddata_result_summary_reflects_illum():
    assert "with illum" in LoadDataResult("26159", n_image_sets=2, with_illum=True).summary()
    assert "no illum" in LoadDataResult("26159", n_image_sets=2, with_illum=False).summary()


def test_generate_loaddata_end_to_end(tmp_path, make_plate):
    plate_dir = make_plate(tmp_path / "26159")
    out = tmp_path / "ld.csv"

    result = generate_loaddata(plate_dir, out)
    assert result.plate == "26159"  # inferred from the dir name
    assert result.n_image_sets == 2
    assert result.with_illum is False

    table = pd.read_csv(out)
    assert len(table) == 2
    assert "Image_FileName_OrigDNA" in table.columns
    assert "Image_FileName_IllumDNA" not in table.columns


def test_generate_loaddata_explicit_plate_and_illum(tmp_path, make_plate):
    plate_dir = make_plate(tmp_path / "raw")
    out = tmp_path / "ld.csv"

    result = generate_loaddata(plate_dir, out, plate="26159", with_illum=True)
    assert result.plate == "26159"  # explicit override, not the dir name "raw"
    assert result.with_illum is True
    assert "Image_FileName_IllumDNA" in pd.read_csv(out).columns


def test_generate_loaddata_chunked_writes_whole_and_chunks(tmp_path, make_plate):
    plate_dir = make_plate(tmp_path / "26159")
    out = tmp_path / "ld.csv"

    result = generate_loaddata(plate_dir, out, chunk_size=1)  # 2 image sets -> 2 chunks
    assert result.n_chunks == 2
    assert "2 chunks" in result.summary()

    assert out.exists()  # whole-plate CSV still written (illum step needs it)
    chunks = tmp_path / "chunks"
    assert {p.name for p in chunks.glob("*.load_data.csv")} == {
        "chunk1.load_data.csv",
        "chunk2.load_data.csv",
    }
    assert (chunks / "chunk1.images.txt").read_text().count("\n") == 5


def test_generate_loaddata_no_chunks_by_default(tmp_path, make_plate):
    result = generate_loaddata(make_plate(tmp_path / "26159"), tmp_path / "ld.csv")
    assert result.n_chunks == 0
    assert not (tmp_path / "chunks").exists()
