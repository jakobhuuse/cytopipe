"""
Tests for cytopipe.report.theme.
Matplotlib styling helpers.
"""

from matplotlib.colors import Colormap

from cytopipe.report import theme


def test_apply_theme_installs_shared_surface():
    import matplotlib.pyplot as plt

    theme.apply_theme()
    assert plt.rcParams["figure.facecolor"] == theme.SURFACE
    assert plt.rcParams["axes.spines.top"] is False


def test_truncated_blues_returns_colormap():
    cmap = theme.truncated_blues()
    assert isinstance(cmap, Colormap)
    # Low end is trimmed of near-white, so it stays visible on marks.
    assert cmap(0.0) != (1.0, 1.0, 1.0, 1.0)
