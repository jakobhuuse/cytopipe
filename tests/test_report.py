"""Tests for the report subcommand: data shaping, discovery, and figure rendering.

Uses a small synthetic cohort (no real profiles needed) with a compound-linked signal so the
degenerate-input guards and the happy path are both exercised.
"""

import numpy as np
import pandas as pd
import pytest

from cytopipe.report import data, figures


def _synthetic_cohort(n_plates=3, wells_per_plate=16, n_compounds=6, n_features=40, seed=0):
    """Well-level normalized-style frame: Metadata_* + efficientnet_* with per-compound signal."""
    rng = np.random.default_rng(seed)
    compounds = ["DMSO", *[f"HY-{i:03d}" for i in range(1, n_compounds)]]
    centers = {c: rng.normal(size=n_features) for c in compounds}
    rows = []
    for plate in range(n_plates):
        plate_id = 26157 + plate
        for well_i in range(wells_per_plate):
            compound = compounds[well_i % n_compounds]
            row, col = divmod(well_i, 12)
            features = centers[compound] + rng.normal(scale=0.3, size=n_features)
            rows.append(
                {
                    "Metadata_Plate": plate_id,
                    "Metadata_Well": f"{chr(ord('A') + row)}{col + 1:02d}",
                    "Metadata_Compound": compound,
                    **{f"efficientnet_{j + 1}": features[j] for j in range(n_features)},
                }
            )
    return pd.DataFrame(rows)


# --- data helpers ---------------------------------------------------------------------------


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


def test_discover_profiles_resolves_engine_and_run_layer(tmp_path):
    root = tmp_path / "results" / "2025-W51" / "deepprofiler"
    (root / "normalized").mkdir(parents=True)
    (root / "raw").mkdir()
    _synthetic_cohort().to_parquet(root / "normalized" / "26157.normalized.parquet")
    (root / "consensus.parquet").write_bytes(b"")  # presence is enough for discovery

    # Pointing at the whole results tree discovers the <experiment>/<engine> layer.
    resolved = data.discover_profiles(tmp_path / "results")
    assert resolved.engine == "deepprofiler"
    assert resolved.root == root
    assert len(resolved.normalized) == 1
    # Pointing straight at the engine dir also works.
    assert data.discover_profiles(root).root == root


def test_discover_profiles_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        data.discover_profiles(tmp_path)


# --- figures --------------------------------------------------------------------------------


def _nonempty(path):
    return path.exists() and path.stat().st_size > 0


def test_all_four_figures_render(tmp_path):
    cohort = _synthetic_cohort()
    plates = [
        (str(plate), pd.DataFrame({"well": grp["Metadata_Well"], "value": range(len(grp))}))
        for plate, grp in cohort.groupby("Metadata_Plate")
    ]
    consensus = cohort.groupby("Metadata_Compound").mean(numeric_only=True).reset_index()
    consensus_path = tmp_path / "consensus.parquet"
    consensus.to_parquet(consensus_path)

    assert _nonempty(figures.plate_heatmaps(plates, "cells per well", tmp_path, "png"))
    assert _nonempty(figures.embedding_umap(cohort, tmp_path, "png"))
    assert _nonempty(figures.replicate_reproducibility(cohort, tmp_path, "png"))
    assert _nonempty(figures.similarity_clustermap(consensus_path, tmp_path, "png", top_n=50))


def test_umap_skips_when_too_few_wells(tmp_path):
    with pytest.raises(figures.FigureSkipped):
        figures.embedding_umap(_synthetic_cohort(n_plates=1, wells_per_plate=3), tmp_path, "png")


def test_replicate_skips_without_replicates(tmp_path):
    # One well per compound → no compound has >= 2 replicate wells.
    single = _synthetic_cohort(n_plates=1, wells_per_plate=6, n_compounds=6)
    with pytest.raises(figures.FigureSkipped):
        figures.replicate_reproducibility(single, tmp_path, "png")


def test_clustermap_skips_without_consensus(tmp_path):
    with pytest.raises(figures.FigureSkipped):
        figures.similarity_clustermap(None, tmp_path, "png")
