"""
Tests for cytopipe.qc.scan.
Aggregating per-well QC Image.csv files and resolving overlay thumbnails.
"""

import pytest

from cytopipe.qc.scan import channel_columns, scan_qc_metrics


def _row(well, site, dna=-2.0, rna=-1.0):
    return {
        "Metadata_Plate": "26159",
        "Metadata_Well": well,
        "Metadata_Site": site,
        "ImageQuality_PowerLogLogSlope_OrigDNA": dna,
        "ImageQuality_PowerLogLogSlope_OrigRNA": rna,
    }


def test_scan_qc_metrics_concatenates_chunks_and_resolves_overlays(tmp_path, make_qc_dir):
    make_qc_dir(tmp_path, _row("A02", 1, dna=-2.0), chunk=1)
    make_qc_dir(tmp_path, _row("A02", 2, dna=-4.5), chunk=2)  # second chunk, same well dir name

    metrics = scan_qc_metrics(tmp_path)

    assert len(metrics) == 2
    assert set(metrics["Metadata_Site"]) == {1, 2}
    assert metrics.loc[metrics["Metadata_Site"] == 2, "ImageQuality_PowerLogLogSlope_OrigDNA"].iloc[
        0
    ] == -4.5
    # Each row's overlay is resolved to the actual file under its own chunk.
    for path in metrics["overlay_path"]:
        assert path is not None
        assert path.exists()
        assert path.name.startswith("26159_A02_")


def test_scan_qc_metrics_combines_multiple_plates(tmp_path, make_qc_dir):
    # Each plate's chunks live under their own subdirectory (mirroring how CYTOPIPE_QC_REVIEW
    # stages a whole run's plates, each named <plate>.<chunk>, flatly into one parent). Both
    # happen to contain a "chunk1" dir, at different paths, so this also checks that doesn't
    # collide now that the scan is a recursive glob rather than assuming one nesting depth.
    make_qc_dir(tmp_path / "26159.1", _row("A02", 1, dna=-2.0), chunk=1)
    make_qc_dir(
        tmp_path / "26162.1",
        {**_row("A02", 1, dna=-3.5), "Metadata_Plate": "26162"},
        chunk=1,
    )

    metrics = scan_qc_metrics(tmp_path)

    assert len(metrics) == 2
    assert set(metrics["Metadata_Plate"].astype(str)) == {"26159", "26162"}
    for path in metrics["overlay_path"]:
        assert path is not None
        assert path.exists()


def test_scan_qc_metrics_missing_overlay_is_none(tmp_path, make_qc_dir):
    make_qc_dir(tmp_path, _row("A02", 1))
    # Remove the overlay this row would otherwise resolve to.
    (tmp_path / "chunk1" / "Overlays" / "26159_A02_1_overlay.png").unlink()

    metrics = scan_qc_metrics(tmp_path)
    assert metrics["overlay_path"].iloc[0] is None


def test_scan_qc_metrics_raises_when_nothing_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        scan_qc_metrics(tmp_path)


def test_channel_columns_maps_channel_name_to_column(tmp_path, make_qc_dir):
    make_qc_dir(tmp_path, _row("A02", 1))
    metrics = scan_qc_metrics(tmp_path)
    columns = channel_columns(metrics)
    assert columns == {
        "DNA": "ImageQuality_PowerLogLogSlope_OrigDNA",
        "RNA": "ImageQuality_PowerLogLogSlope_OrigRNA",
    }
