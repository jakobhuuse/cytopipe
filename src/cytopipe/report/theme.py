"""Shared matplotlib styling for report figures (validated light-surface palette).

Colours follow the data-viz reference palette: single-hue sequential (blue) for magnitude,
diverging blue<->red for correlation, a fixed-order categorical set for identity, and
recessive text/grid ink. Figures render to static PNG/SVG, so only the light surface is used.
"""

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

# Chrome / ink
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

# Marks
SERIES_BLUE = "#2a78d6"  # categorical slot 1 / replicate / control
NULL_GRAY = "#898781"  # null distribution
REST_GRAY = "#c9c8c2"  # de-emphasised background points
EMPTY_CELL = "#e6e5df"  # missing wells in a heatmap

# Fixed-order categorical hues (light steps), assigned in order, never cycled past 8.
CATEGORICAL = (
    "#2a78d6",  # blue
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
    "#e87ba4",  # magenta
    "#eb6834",  # orange
)

SEQUENTIAL_CMAP = "Blues"  # single-hue light->dark
DIVERGING_CMAP = "vlag"  # blue<->red, neutral midpoint (used centered at 0)


def apply_theme() -> None:
    """Install recessive, sans-serif rcParams on the shared light surface."""
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans"],
            "text.color": INK,
            "axes.titlecolor": INK,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.labelcolor": INK_SECONDARY,
            "axes.labelsize": 9,
            "axes.edgecolor": BASELINE,
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.frameon": False,
            "legend.fontsize": 8,
            "figure.dpi": 130,
            "savefig.dpi": 150,
            "savefig.bbox": "tight",
        }
    )


def truncated_blues():
    """Single-hue blue ramp trimmed of the near-white low end (stays visible on marks)."""
    base = plt.get_cmap(SEQUENTIAL_CMAP)
    return LinearSegmentedColormap.from_list("blues_trunc", base(np.linspace(0.35, 1.0, 256)))
