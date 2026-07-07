"""Tests for cytopipe.report.data.
Profile discovery and data shaping for the figures.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cytopipe.report import data
from cytopipe.report.data import ProfileSet


def test_split_metadata_features_by_prefix_and_dtype():
    df = pd.DataFrame(
        {"Metadata_Plate": ["p"], "Metadata_Well": ["A01"], "efficientnet_1": [1.0], "note": ["x"]}
    )
    metadata, features = data.split_metadata_features(df)
    assert metadata == ["Metadata_Plate", "Metadata_Well"]
    assert features == ["efficientnet_1"]  # non-numeric "note" is not a feature


def test_parse_wells_and_grid_shape():
    parsed = data.parse_wells(pd.Series(["A01", "B02", "H12", "P24"]))
    assert list(parsed["row"]) == [0, 1, 7, 15]
    assert list(parsed["col"]) == [0, 1, 11, 23]
    assert data.infer_grid_shape(7, 11) == (8, 12)  # 96-well
    assert data.infer_grid_shape(15, 23) == (16, 24)  # 384-well
    assert data.infer_grid_shape(40, 40) == (41, 41)  # exact fit past standard plates


def test_clean_features_handles_inf_nan_and_constant_columns():
    df = pd.DataFrame(
        {
            "f_good": [1.0, 2.0, 3.0, 4.0],
            "f_const": [5.0, 5.0, 5.0, 5.0],
            "f_allnan": [np.nan] * 4,
            "f_infnan": [np.inf, 1.0, np.nan, 2.0],
        }
    )
    cleaned = data.clean_features(df, list(df.columns))
    assert "f_const" not in cleaned and "f_allnan" not in cleaned
    assert np.isfinite(cleaned.to_numpy()).all()
    assert len(cleaned) == 4


def test_plate_id_from_path():
    assert data.plate_id_from_path(Path("26157.normalized.parquet")) == "26157"
    assert data.plate_id_from_path(Path("26157.parquet")) == "26157"


def test_load_profiles_concatenates(tmp_path):
    for i in (0, 1):
        pd.DataFrame({"a": [i]}).to_parquet(tmp_path / f"p{i}.parquet")
    df = data.load_profiles(sorted(tmp_path.glob("*.parquet")))
    assert len(df) == 2


def test_load_profiles_empty_raises():
    with pytest.raises(FileNotFoundError):
        data.load_profiles([])


# --- discovery --------------------------------------------------------------------------------


def _make_engine_dir(root: Path, engine: str, cohort: pd.DataFrame):
    d = root / engine
    (d / "normalized").mkdir(parents=True)
    cohort.to_parquet(d / "normalized" / "26157.normalized.parquet")
    (d / "consensus.parquet").write_bytes(b"")  # presence is enough for discovery
    return d


def test_discover_profiles_resolves_engine_and_run_layer(tmp_path, synthetic_cohort):
    root = tmp_path / "results" / "2025-W51" / "deepprofiler"
    (root / "normalized").mkdir(parents=True)
    (root / "raw").mkdir()
    synthetic_cohort().to_parquet(root / "normalized" / "26157.normalized.parquet")
    (root / "consensus.parquet").write_bytes(b"")

    # Pointing at the whole results tree discovers the <experiment>/<engine> layer.
    resolved = data.discover_profiles(tmp_path / "results")
    assert resolved.engine == "deepprofiler"
    assert resolved.root == root
    assert len(resolved.normalized) == 1
    assert resolved.consensus is not None
    # Pointing straight at the engine dir also works.
    assert data.discover_profiles(root).root == root


def test_discover_profiles_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        data.discover_profiles(tmp_path)


def test_discover_profiles_multiple_engines_requires_disambiguation(tmp_path, synthetic_cohort):
    exp = tmp_path / "results" / "2025-W51"
    _make_engine_dir(exp, "deepprofiler", synthetic_cohort())
    _make_engine_dir(exp, "cellprofiler", synthetic_cohort())

    with pytest.raises(ValueError, match="multiple profile directories"):
        data.discover_profiles(tmp_path / "results")  # engine="auto" is ambiguous
    # Naming the engine disambiguates.
    assert data.discover_profiles(tmp_path / "results", "cellprofiler").engine == "cellprofiler"


# --- ProfileSet.cohort_source -----------------------------------------------------------------


def test_cohort_source_prefers_feature_select(tmp_path):
    fs = tmp_path / "feature_select.parquet"
    normalized = [tmp_path / "26157.parquet"]
    with_fs = ProfileSet("cellprofiler", tmp_path, normalized, [], None, fs)
    without_fs = ProfileSet("deepprofiler", tmp_path, normalized, [], None, None)
    assert with_fs.cohort_source() == [fs]
    assert without_fs.cohort_source() == normalized


# --- per-well values --------------------------------------------------------------------------


def test_well_cell_counts_groups_by_detected_column(tmp_path):
    raw = tmp_path / "26157.parquet"
    pd.DataFrame({"Metadata_Well": ["A01", "A01", "B02"], "x": [1, 2, 3]}).to_parquet(raw)
    counts = data.well_cell_counts(raw).set_index("well")["value"].to_dict()
    assert counts == {"A01": 2, "B02": 1}


def test_well_cell_counts_missing_well_column_raises(tmp_path):
    raw = tmp_path / "26157.parquet"
    pd.DataFrame({"x": [1, 2]}).to_parquet(raw)
    with pytest.raises(KeyError, match="well column"):
        data.well_cell_counts(raw)


def test_plate_well_values_raw_branch_counts_cells(tmp_path):
    raw = tmp_path / "26157.parquet"
    pd.DataFrame({"Metadata_Well": ["A01", "A01", "B02"], "x": [1, 2, 3]}).to_parquet(raw)
    profiles = ProfileSet("deepprofiler", tmp_path, [], [raw], None, None)

    plates, label = data.plate_well_values(profiles)
    assert label == "cell count"
    assert len(plates) == 1
    plate_id, wells = plates[0]
    assert plate_id == "26157"
    assert set(wells.columns) == {"well", "value"}


def test_plate_well_values_normalized_branch_uses_mean_abs_feature(tmp_path, synthetic_cohort):
    norm = tmp_path / "26157.normalized.parquet"
    synthetic_cohort(n_plates=1).to_parquet(norm)
    profiles = ProfileSet("deepprofiler", tmp_path, [norm], [], None, None)

    plates, label = data.plate_well_values(profiles)
    assert label == "mean |feature|"
    plate_id, wells = plates[0]
    assert plate_id == "26157"
    assert set(wells.columns) == {"well", "value"}
    assert (wells["value"] >= 0).all()  # mean of absolute values
