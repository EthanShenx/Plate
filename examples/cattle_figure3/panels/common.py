"""Shared chart conventions and palettes for the synthetic cattle atlas."""

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import plate

STATE_NAMES = [f"State {i}" for i in range(1, 6)]
STATE_COLORS = [plate.colors[name] for name in STATE_NAMES]
MYELOID = ["MA0", "MA1", "MA2", "MA3", "MA4", "MA5", "MO0", "MO1", "MO2"]
SUBTYPES = MYELOID + ["DC0", "DC1", "DC2", "DC3", "DC4"]
SUBTYPE_COLORS = [plate.colors[name] for name in SUBTYPES]
CLUSTER_COLORS = [plate.colors[f"Cluster {i}"] for i in (1, 2, 4, 3)]
DIVERGING = LinearSegmentedColormap.from_list("expression",
                                             ["#235a7a", "#f7f8f6", "#a51e25"])
DARK = "#405065"


def figure():
    return plt.figure(figsize=[value / 25.4 for value in plate.size_mm])


def box(fig, design, x, y, w, h):
    """Place axes using a top-left design grid, independent of physical resize."""
    width, height = design
    return fig.add_axes([x / width, 1 - (y + h) / height, w / width, h / height])


def plain(ax):
    ax.set_axis_off()
    return ax


def swatches(ax, entries, title, step=1.0, font=5.4):
    ax.text(0, 0, title, fontsize=6, va="center")
    for i, (name, color) in enumerate(entries, 1):
        ax.text(.11, i * step, name, fontsize=font, va="center")
        ax.scatter([.027], [i * step], s=24, color=color, marker="s", linewidths=0)
    ax.set(xlim=(0, 1), ylim=((len(entries) + .7) * step, -.4))
    plain(ax)
