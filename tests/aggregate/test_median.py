"""Tests for the DuckDB streaming median aggregation (pycytominer-aggregate drop-in).

Equivalence is checked against pandas' own ``groupby(...).median()``, which is the
exact operation pycytominer performs (after casting features to float64), so these
lock in numerical agreement without importing pycytominer.
"""

import numpy as np
import pandas as pd
import pytest

from cytopipe.aggregate import aggregate_median
from cytopipe.aggregate.median import _infer_features


def _pycytominer_median(df, strata, features):
    """Reproduce pycytominer's median: float64 cast, skipna median, groups sorted."""
    feat = df[features].astype(float)
    grouped = pd.concat([df[strata], feat], axis="columns").groupby(strata, dropna=False)
    return grouped.median().reset_index().sort_values(strata).reset_index(drop=True)


def _run(tmp_path, df, *, strata, features, **kwargs):
    src = tmp_path / "single_cell.parquet"
    dest = tmp_path / "aggregated.parquet"
    df.to_parquet(src)
    aggregate_median(src, dest, strata=strata, features=features, **kwargs)
    return pd.read_parquet(dest)


def test_matches_pandas_median_including_even_count_interpolation(tmp_path):
    df = pd.DataFrame(
        {
            "Metadata_Plate": ["p1", "p1", "p1", "p2", "p2"],
            "Metadata_Well": ["A01", "A01", "A02", "A01", "A01"],
            "Cells_Area": [1.0, 3.0, 5.0, 2.0, 8.0],
            "Nuclei_Int": [10.0, 20.0, 30.0, 40.0, 50.0],
        }
    )
    strata = ["Metadata_Plate", "Metadata_Well"]
    features = ["Cells_Area", "Nuclei_Int"]

    got = _run(tmp_path, df, strata=strata, features=features)
    got = got.sort_values(strata).reset_index(drop=True)
    expected = _pycytominer_median(df, strata, features)

    # Even-count groups exercise interpolation: p1/A01 -> (1+3)/2, p2/A01 -> (2+8)/2.
    pd.testing.assert_frame_equal(got[expected.columns], expected, check_dtype=False)


def test_nan_is_skipped_like_pandas(tmp_path):
    # median([1, 3]) == 2.0 if NaN is skipped; a naive DuckDB median would sort NaN
    # highest and return 3.0. Asserting 2.0 proves parity with pandas skipna=True.
    df = pd.DataFrame({"Metadata_Well": ["A01", "A01", "A01"], "Cells_X": [1.0, np.nan, 3.0]})

    got = _run(tmp_path, df, strata=["Metadata_Well"], features=["Cells_X"])

    assert got.loc[0, "Cells_X"] == 2.0


def test_null_strata_forms_its_own_group(tmp_path):
    # groupby(dropna=False): the two null-well rows aggregate together, not dropped.
    df = pd.DataFrame({"Metadata_Well": ["A01", None, None], "Cells_X": [1.0, 2.0, 4.0]})

    got = _run(tmp_path, df, strata=["Metadata_Well"], features=["Cells_X"])

    assert len(got) == 2
    null_row = got[got["Metadata_Well"].isna()]
    assert len(null_row) == 1
    assert null_row["Cells_X"].iloc[0] == 3.0  # median([2, 4])


def test_infer_selects_only_compartment_columns(tmp_path):
    df = pd.DataFrame(
        {
            "Metadata_Well": ["A01", "A01"],
            "Metadata_Site": [1, 2],
            "ImageNumber": [1, 1],
            "Cells_A": [1.0, 3.0],
            "Nuclei_B": [4.0, 6.0],
            "Cytoplasm_C": [2.0, 8.0],
        }
    )

    got = _run(tmp_path, df, strata=["Metadata_Well"], features=None)

    # Non-feature columns (Metadata_Site, ImageNumber) are neither grouped nor aggregated,
    # exactly as pycytominer drops them.
    assert list(got.columns) == ["Metadata_Well", "Cells_A", "Nuclei_B", "Cytoplasm_C"]


def test_infer_raises_without_cellprofiler_features(tmp_path):
    df = pd.DataFrame({"Metadata_Well": ["A01"], "efficientnet_1": [1.0]})

    with pytest.raises(ValueError, match="no CellProfiler feature"):
        _run(tmp_path, df, strata=["Metadata_Well"], features=None)


def test_explicit_features_for_non_cellprofiler_names(tmp_path):
    df = pd.DataFrame(
        {
            "Metadata_Plate": ["p1", "p1", "p1"],
            "Metadata_Well": ["A01", "A01", "A01"],
            "Metadata_Compound": ["x", "x", "x"],
            "efficientnet_1": [1.0, 2.0, 6.0],
            "efficientnet_2": [10.0, 20.0, 30.0],
        }
    )
    strata = ["Metadata_Plate", "Metadata_Well", "Metadata_Compound"]
    features = ["efficientnet_1", "efficientnet_2"]

    got = _run(tmp_path, df, strata=strata, features=features)
    got = got.sort_values(strata).reset_index(drop=True)
    expected = _pycytominer_median(df, strata, features)

    pd.testing.assert_frame_equal(got[expected.columns], expected, check_dtype=False)


def test_output_preserves_requested_feature_order(tmp_path):
    df = pd.DataFrame(
        {
            "Metadata_Well": ["A01", "A01"],
            "Cells_A": [1.0, 3.0],
            "Nuclei_B": [4.0, 6.0],
        }
    )

    got = _run(tmp_path, df, strata=["Metadata_Well"], features=["Nuclei_B", "Cells_A"])

    assert list(got.columns) == ["Metadata_Well", "Nuclei_B", "Cells_A"]


def test_missing_column_raises(tmp_path):
    df = pd.DataFrame({"Metadata_Well": ["A01"], "Cells_A": [1.0]})

    with pytest.raises(ValueError, match="not present"):
        _run(tmp_path, df, strata=["Metadata_Well"], features=["Nope"])


def test_empty_strata_raises(tmp_path):
    df = pd.DataFrame({"Metadata_Well": ["A01"], "Cells_A": [1.0]})

    with pytest.raises(ValueError, match="at least one grouping column"):
        _run(tmp_path, df, strata=[], features=["Cells_A"])


def test_memory_limit_is_honored_and_still_correct(tmp_path):
    # A tiny memory_limit forces DuckDB to spill; output must be unchanged.
    df = pd.DataFrame(
        {
            "Metadata_Well": ["A01"] * 1000 + ["A02"] * 1000,
            "Cells_X": list(range(1000)) + list(range(1000, 2000)),
        }
    ).astype({"Cells_X": float})

    got = _run(
        tmp_path,
        df,
        strata=["Metadata_Well"],
        features=["Cells_X"],
        memory_limit="256MB",
        temp_directory=str(tmp_path),
    )
    got = got.sort_values("Metadata_Well").reset_index(drop=True)

    assert got.loc[0, "Cells_X"] == np.median(range(1000))
    assert got.loc[1, "Cells_X"] == np.median(range(1000, 2000))


def test_temp_directory_is_created_if_missing(tmp_path):
    # The process points spill at a task-local dir it may not have created yet.
    df = pd.DataFrame({"Metadata_Well": ["A01", "A01"], "Cells_X": [1.0, 3.0]})
    spill = tmp_path / "does" / "not" / "exist"

    got = _run(
        tmp_path,
        df,
        strata=["Metadata_Well"],
        features=["Cells_X"],
        temp_directory=str(spill),
    )

    assert spill.is_dir()
    assert got.loc[0, "Cells_X"] == 2.0


def test_infer_features_helper_matches_prefix_rule():
    columns = ["Metadata_Well", "Cells_A", "Nuclei_B", "Cytoplasm_C", "efficientnet_1"]
    assert _infer_features(columns) == ["Cells_A", "Nuclei_B", "Cytoplasm_C"]
