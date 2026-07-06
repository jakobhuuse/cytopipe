"""
Tests for cytopipe.report.figures.
The four figures render, and guards skip degenerate input.
"""

import numpy as np
import pandas as pd
import pytest

from cytopipe.report import figures


def _nonempty(path):
    return path.exists() and path.stat().st_size > 0


def test_all_four_figures_render(tmp_path, synthetic_cohort):
    cohort = synthetic_cohort()
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


def test_umap_skips_when_too_few_wells(tmp_path, synthetic_cohort):
    with pytest.raises(figures.FigureSkipped):
        figures.embedding_umap(synthetic_cohort(n_plates=1, wells_per_plate=3), tmp_path, "png")


def test_replicate_skips_without_replicates(tmp_path, synthetic_cohort):
    # One well per compound → no compound has >= 2 replicate wells.
    single = synthetic_cohort(n_plates=1, wells_per_plate=6, n_compounds=6)
    with pytest.raises(figures.FigureSkipped):
        figures.replicate_reproducibility(single, tmp_path, "png")


def test_clustermap_skips_without_consensus(tmp_path):
    with pytest.raises(figures.FigureSkipped):
        figures.similarity_clustermap(None, tmp_path, "png")


def test_control_compound_is_configurable(tmp_path):
    # Only DMSO has replicate wells; the treatments are singletons. Whether the replicate
    # figure has anything to plot therefore hinges on which compound is treated as the control.
    rng = np.random.default_rng(0)
    rows = [
        {"Metadata_Compound": compound, **{f"efficientnet_{j}": rng.normal() for j in range(20)}}
        for compound, n in [("DMSO", 3), ("HY-001", 1), ("HY-002", 1), ("HY-003", 1)]
        for _ in range(n)
    ]
    cohort = pd.DataFrame(rows)

    # DMSO as control → it is excluded, leaving only singletons → skipped.
    with pytest.raises(figures.FigureSkipped):
        figures.replicate_reproducibility(cohort, tmp_path, "png", control="DMSO")

    # A different control keeps DMSO's replicates in play → the figure renders.
    assert _nonempty(figures.replicate_reproducibility(cohort, tmp_path, "png", control="HY-999"))
