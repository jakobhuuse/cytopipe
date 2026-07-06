"""
Tests for cytopipe.loaddata.scan.
Parsing channel TIFF filenames into image rows.
"""

import pytest

from cytopipe.loaddata.scan import CHANNEL_BY_NUMBER, scan_images


def test_scan_skips_thumbnails_and_parses(tmp_path, make_plate):
    make_plate(tmp_path)
    df = scan_images(tmp_path)
    assert len(df) == 10  # 2 sites × 5 channels; thumbnail excluded
    assert set(df["ChannelNumber"]) == set(CHANNEL_BY_NUMBER)
    assert not df["FileName"].str.contains("_thumb").any()


def test_scan_ignores_unknown_channel_numbers(tmp_path, make_plate):
    # w6 is outside CHANNEL_BY_NUMBER (1-5) and must be dropped, valid channels kept.
    make_plate(tmp_path, sites=(1,), channels=(1, 2, 3, 4, 5, 6))
    df = scan_images(tmp_path)
    assert set(df["ChannelNumber"]) == set(CHANNEL_BY_NUMBER)  # no channel 6


def test_scan_skips_files_not_matching_convention(tmp_path, make_plate):
    make_plate(tmp_path, sites=(1,))
    (tmp_path / "TimePoint_1" / "not_a_channel_image.tif").touch()
    df = scan_images(tmp_path)
    assert len(df) == 5  # only the 5 well-formed channel files


def test_scan_no_matching_images_errors(tmp_path):
    (tmp_path / "notes.txt").touch()
    with pytest.raises(FileNotFoundError):
        scan_images(tmp_path)
