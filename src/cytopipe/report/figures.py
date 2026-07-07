"""The four standard Cell Painting report figures.

Each renders one figure to ``out_dir`` and returns its path, or raises ``FigureSkipped`` when the
data is insufficient so the CLI can skip instead of crashing.
"""

import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
from sklearn.preprocessing import StandardScaler
from umap import UMAP

from cytopipe.columns import (
    CONTROL_COMPOUND,
    METADATA_BATCH,
    METADATA_COMPOUND,
    METADATA_PLATE,
)

from . import theme
from .data import (
    clean_features,
    infer_grid_shape,
    parse_wells,
    split_metadata_features,
)


class FigureSkipped(Exception):
    """Raised when the input data can't support a figure (reported as a skip, not a crash)."""


def _out(out_dir: Path, name: str, fmt: str) -> Path:
    return out_dir / f"{name}.{fmt}"


def _row_zscores(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Row-standardise so that ``z_i . z_j / n_features`` is the Pearson correlation of rows.

    Returns the z-scored rows and the boolean mask of rows kept (those with non-zero variance).
    """
    centered = matrix - matrix.mean(axis=1, keepdims=True)
    std = matrix.std(axis=1, keepdims=True)
    keep = std[:, 0] > 0
    return centered[keep] / std[keep], keep


# --- 1. Plate QC heatmaps -------------------------------------------------------------------


def plate_heatmaps(
    plates: list[tuple[str, pd.DataFrame]], value_label: str, out_dir: Path, fmt: str
) -> Path:
    """Grid of per-plate well heatmaps (one subplot per plate) coloured by ``value_label``."""
    if not plates:
        raise FigureSkipped("no plate data available")

    grids, max_row, max_col = [], 0, 0
    all_values = []
    for plate_id, wells in plates:
        coords = parse_wells(wells["well"]).assign(value=wells["value"].to_numpy())
        coords = coords.dropna(subset=["row", "col"])
        if coords.empty:
            continue
        max_row = max(max_row, int(coords["row"].max()))
        max_col = max(max_col, int(coords["col"].max()))
        grids.append((plate_id, coords))
        all_values.append(coords["value"].to_numpy())

    if not grids:
        raise FigureSkipped("no parseable wells")

    rows, cols = infer_grid_shape(max_row, max_col)
    vmax = float(np.percentile(np.concatenate(all_values), 99)) or 1.0

    ncols = min(len(grids), 5)
    nrows = math.ceil(len(grids) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.0 * ncols, 2.3 * nrows), squeeze=False)
    flat_axes = axes.flatten()
    cmap = plt.get_cmap(theme.SEQUENTIAL_CMAP).with_extremes(bad=theme.EMPTY_CELL)

    mesh = None
    for ax, (plate_id, coords) in zip(flat_axes, grids, strict=False):
        grid = np.full((rows, cols), np.nan)
        grid[coords["row"].astype(int), coords["col"].astype(int)] = coords["value"]
        mesh = ax.imshow(
            np.ma.masked_invalid(grid), cmap=cmap, vmin=0, vmax=vmax, aspect="equal"
        )
        ax.set_title(plate_id, fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
    for ax in flat_axes[len(grids):]:
        ax.set_visible(False)

    if mesh is not None:
        cbar = fig.colorbar(mesh, ax=axes, fraction=0.025, pad=0.02)
        cbar.set_label(value_label)
    fig.suptitle(f"Per-well {value_label}", fontsize=12, fontweight="bold")

    path = _out(out_dir, "01_platemaps", fmt)
    fig.savefig(path)
    plt.close(fig)
    return path


# --- 2. UMAP embedding ----------------------------------------------------------------------


def _scatter_ordered(ax, embedding: np.ndarray, labels: pd.Series, title: str) -> None:
    categories = sorted(pd.unique(labels))
    ranks = labels.map({c: i for i, c in enumerate(categories)}).to_numpy()
    scatter = ax.scatter(
        embedding[:, 0], embedding[:, 1], c=ranks, cmap=theme.truncated_blues(),
        s=6, linewidths=0, alpha=0.85,
    )
    cbar = ax.figure.colorbar(scatter, ax=ax, fraction=0.046, pad=0.04)
    ticks = np.linspace(0, len(categories) - 1, min(6, len(categories))).round().astype(int)
    cbar.set_ticks(ticks)
    cbar.set_ticklabels([str(categories[t]) for t in ticks])
    ax.set_title(title)


def _scatter_categorical(ax, embedding: np.ndarray, labels: pd.Series, title: str) -> None:
    for i, category in enumerate(sorted(pd.unique(labels))):
        mask = (labels == category).to_numpy()
        ax.scatter(
            embedding[mask, 0], embedding[mask, 1], s=6, linewidths=0, alpha=0.85,
            color=theme.CATEGORICAL[i % len(theme.CATEGORICAL)], label=str(category),
        )
    ax.legend(markerscale=2, loc="best")
    ax.set_title(title)


def _scatter_control(ax, embedding: np.ndarray, compounds: pd.Series, control: str) -> None:
    is_control = (compounds == control).to_numpy()
    ax.scatter(
        embedding[~is_control, 0], embedding[~is_control, 1], s=5, linewidths=0, alpha=0.45,
        color=theme.REST_GRAY, label="treatment",
    )
    ax.scatter(
        embedding[is_control, 0], embedding[is_control, 1], s=9, linewidths=0, alpha=0.9,
        color=theme.SERIES_BLUE, label=control,
    )
    ax.legend(markerscale=2, loc="best")
    ax.set_title(f"{control} vs. treatments")


def embedding_umap(
    cohort: pd.DataFrame, out_dir: Path, fmt: str, control: str = CONTROL_COMPOUND, seed: int = 42
) -> Path:
    """UMAP of well-level profiles, one panel per available metadata + a control highlight."""
    if len(cohort) < 5:
        raise FigureSkipped(f"only {len(cohort)} wells (need >= 5)")

    _, features = split_metadata_features(cohort)
    matrix = clean_features(cohort, features)
    if matrix.shape[1] < 2:
        raise FigureSkipped("fewer than 2 usable features")

    scaled = StandardScaler().fit_transform(matrix.to_numpy())
    reducer = UMAP(n_neighbors=min(15, len(cohort) - 1), random_state=seed)
    with warnings.catch_warnings():
        # A fixed random_state intentionally forces single-threaded UMAP (reproducible layout).
        warnings.filterwarnings(
            "ignore", message="n_jobs value .* overridden", category=UserWarning
        )
        embedding = reducer.fit_transform(scaled)

    panels = []
    if METADATA_PLATE in cohort:
        panels.append(("ordered", cohort[METADATA_PLATE].astype(str), "by plate"))
    if METADATA_BATCH in cohort:
        panels.append(("categorical", cohort[METADATA_BATCH].astype(str), "by batch"))
    if METADATA_COMPOUND in cohort:
        panels.append(("control", cohort[METADATA_COMPOUND].astype(str), ""))

    fig, axes = plt.subplots(1, len(panels), figsize=(4.6 * len(panels), 4.2), squeeze=False)
    for ax, (kind, labels, title) in zip(axes.flat, panels, strict=True):
        if kind == "ordered":
            _scatter_ordered(ax, embedding, labels, title)
        elif kind == "categorical":
            _scatter_categorical(ax, embedding, labels, title)
        else:
            _scatter_control(ax, embedding, labels, control)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlabel("UMAP-1")
        ax.set_ylabel("UMAP-2")
    fig.suptitle("Well-level profile embedding (UMAP)", fontsize=12, fontweight="bold")

    path = _out(out_dir, "02_umap", fmt)
    fig.savefig(path)
    plt.close(fig)
    return path


# --- 3. Replicate reproducibility -----------------------------------------------------------


def replicate_reproducibility(
    cohort: pd.DataFrame,
    out_dir: Path,
    fmt: str,
    control: str = CONTROL_COMPOUND,
    n_null: int = 5000,
    seed: int = 0,
) -> Path:
    """Replicate vs. null correlation distributions + percent replicating.

    Replicate score per compound is the median pairwise correlation among its wells. The null is
    correlations of random cross-compound well pairs. Controls are excluded from the numerator.
    """
    if METADATA_COMPOUND not in cohort:
        raise FigureSkipped(f"no {METADATA_COMPOUND} column")

    _, features = split_metadata_features(cohort)
    matrix = clean_features(cohort, features)
    zscores, kept = _row_zscores(matrix.to_numpy())
    compounds = cohort[METADATA_COMPOUND].astype(str).to_numpy()[kept]
    n_features = zscores.shape[1]

    groups = {c: np.flatnonzero(compounds == c) for c in np.unique(compounds)}
    replicate_scores = []
    for compound, idx in groups.items():
        if compound == control or len(idx) < 2:
            continue
        corr = (zscores[idx] @ zscores[idx].T) / n_features
        replicate_scores.append(np.median(corr[np.triu_indices(len(idx), k=1)]))

    if len(replicate_scores) < 1:
        raise FigureSkipped("no compound has >= 2 replicate wells")

    rng = np.random.default_rng(seed)
    left = rng.integers(0, len(zscores), size=n_null)
    right = rng.integers(0, len(zscores), size=n_null)
    different = compounds[left] != compounds[right]
    null = np.einsum("ij,ij->i", zscores[left[different]], zscores[right[different]]) / n_features

    replicate_scores = np.asarray(replicate_scores)
    threshold = float(np.percentile(null, 95))
    percent_replicating = 100.0 * np.mean(replicate_scores > threshold)

    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    bins = np.linspace(
        min(null.min(), replicate_scores.min()), max(null.max(), replicate_scores.max()), 40
    )
    ax.hist(
        null, bins=bins, density=True, color=theme.NULL_GRAY, alpha=0.7,
        label="null (non-replicate pairs)",
    )
    ax.hist(
        replicate_scores, bins=bins, density=True, color=theme.SERIES_BLUE, alpha=0.8,
        label="replicate (per compound)",
    )
    ax.axvline(threshold, color=theme.INK_SECONDARY, linestyle="--", linewidth=1)
    ax.text(
        0.98, 0.95, f"Percent replicating: {percent_replicating:.0f}%",
        transform=ax.transAxes, ha="right", va="top", fontsize=11, fontweight="bold",
        color=theme.INK,
    )
    ax.set_xlabel("profile correlation")
    ax.set_ylabel("density")
    ax.set_title("Replicate reproducibility", fontweight="bold")
    ax.legend(loc="upper left")

    path = _out(out_dir, "03_replicate_reproducibility", fmt)
    fig.savefig(path)
    plt.close(fig)
    return path


# --- 4. Similarity clustermap ---------------------------------------------------------------


def similarity_clustermap(
    consensus_path: Path | None,
    out_dir: Path,
    fmt: str,
    control: str = CONTROL_COMPOUND,
    top_n: int = 50,
) -> Path:
    """Clustered compound x compound correlation of the ``top_n`` most active consensus profiles."""
    if consensus_path is None:
        raise FigureSkipped("no consensus.parquet")

    df = pd.read_parquet(consensus_path)
    if METADATA_COMPOUND not in df:
        raise FigureSkipped(f"no {METADATA_COMPOUND} column")

    _, features = split_metadata_features(df)
    matrix = clean_features(df, features)
    compounds = df[METADATA_COMPOUND].astype(str).reset_index(drop=True)
    matrix = matrix.reset_index(drop=True)

    is_control = compounds == control
    if is_control.any():
        reference = matrix[is_control].mean(axis=0)
    else:
        reference = pd.Series(0.0, index=matrix.columns)
    activity = np.sqrt(((matrix - reference) ** 2).sum(axis=1))
    activity[is_control] = -np.inf  # never select the control itself

    order = activity.sort_values(ascending=False).index
    if top_n and top_n > 0:
        order = order[:top_n]
    selected = matrix.loc[order]
    labels = compounds.loc[order]
    if len(selected) < 2:
        raise FigureSkipped(f"only {len(selected)} compounds after control exclusion (need >= 2)")

    corr = pd.DataFrame(np.corrcoef(selected.to_numpy()), index=labels, columns=labels)
    corr.index.name = corr.columns.name = None  # drop the "Metadata_Compound" axis labels
    show_labels = len(corr) <= 60
    side = min(0.22 * len(corr) + 3, 22)

    grid = sns.clustermap(
        corr, cmap=theme.DIVERGING_CMAP, center=0, vmin=-1, vmax=1,
        figsize=(side, side), xticklabels=show_labels, yticklabels=show_labels,
        dendrogram_ratio=0.12, cbar_pos=(0.02, 0.83, 0.03, 0.15),
    )
    grid.ax_heatmap.tick_params(labelsize=6)
    grid.figure.suptitle(
        f"Consensus profile similarity (top {len(corr)} compounds)",
        fontsize=13, fontweight="bold",
    )

    path = _out(out_dir, "04_similarity_clustermap", fmt)
    grid.savefig(path)
    plt.close(grid.figure)
    return path
