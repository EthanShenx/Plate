"""Executed in the plotting interpreter, independently of the server."""

import json
from pathlib import Path
import runpy
import sys
import warnings

import matplotlib as mpl
from matplotlib import font_manager, pyplot as plt
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.lines import Line2D
from matplotlib.text import Text

import plate


def apply_style(style, palette):
    try:
        path = font_manager.findfont(style["font_family"], fallback_to_default=False)
        family = font_manager.FontProperties(fname=path).get_name()
    except ValueError:
        family = style["font_family"]
        warnings.warn(f"Font {family!r} is unavailable to matplotlib.")
    spines = style["spines"]
    background = style["background"]
    params = {
        "font.family": family, "font.size": style["font_main_pt"],
        "axes.labelsize": style["axis_title_pt"], "axes.titlesize": style["font_main_pt"],
        "legend.fontsize": style["legend_text_pt"], "legend.title_fontsize": style["legend_title_pt"],
        "lines.linewidth": style["line_data_pt"], "lines.markersize": style["marker_size_pt"],
        "axes.linewidth": style["line_axis_pt"],
        "axes.prop_cycle": mpl.cycler(color=palette), "axes.grid": style["grid"] == "major",
        "axes.facecolor": background, "figure.facecolor": background,
        "axes.spines.left": spines != "none", "axes.spines.bottom": spines != "none",
        "axes.spines.right": spines == "all", "axes.spines.top": spines == "all",
        "savefig.bbox": None,
    }
    for axis in ("xtick", "ytick"):
        params.update({
            f"{axis}.labelsize": style["tick_label_pt"],
            f"{axis}.major.size": style["tick_length_pt"], f"{axis}.minor.size": style["tick_length_pt"],
            f"{axis}.major.width": style["tick_width_pt"], f"{axis}.minor.width": style["tick_width_pt"],
            f"{axis}.direction": style["tick_direction"],
        })
    # Seaborn's default palette reads the same Matplotlib color cycle.
    mpl.rcParams.update(params)
    annotate, text = Axes.annotate, Axes.text

    def annotation(self, *args, **kwargs):
        if not any(key in kwargs for key in ("size", "fontsize", "fontproperties")):
            kwargs["fontsize"] = style["annotation_pt"]
        return annotate(self, *args, **kwargs)

    def axes_text(self, *args, **kwargs):
        fontdict = args[3] if len(args) > 3 else kwargs.get("fontdict") or {}
        if not any(key in kwargs or key in fontdict for key in ("size", "fontsize", "fontproperties")):
            kwargs["fontsize"] = style["annotation_pt"]
        return text(self, *args, **kwargs)

    Axes.annotate = annotation
    Axes.text = axes_text


def outer_axes(fig, original=False):
    boxes = [axis.get_position(original=original) for axis in fig.axes if axis.get_visible()]
    if not boxes:
        return None
    return [min(box.x0 for box in boxes), min(box.y0 for box in boxes),
            max(box.x1 for box in boxes), max(box.y1 for box in boxes)]


def apply_overrides(fig, style, overrides):
    def text_size(artists, role):
        if role in overrides:
            for artist in artists:
                artist.set_fontsize(style[role])

    if "font_family" in overrides:
        for artist in fig.findobj(Text):
            artist.set_fontfamily(style["font_family"])
    for ax in fig.axes:
        text_size([ax.xaxis.label, ax.yaxis.label], "axis_title_pt")
        text_size([ax.title, ax._left_title, ax._right_title], "font_main_pt")
        text_size(ax.texts, "annotation_pt")
        for axis in (ax.xaxis, ax.yaxis):
            if "tick_label_pt" in overrides:
                axis.set_tick_params(which="both", labelsize=style["tick_label_pt"])
            params = {property: value for key, property, value in (
                ("tick_length_pt", "length", style["tick_length_pt"]),
                ("tick_width_pt", "width", style["tick_width_pt"]),
                ("tick_direction", "direction", style["tick_direction"]),
            ) if key in overrides}
            if params:
                axis.set_tick_params(which="both", **params)
        for side, spine in ax.spines.items():
            if "line_axis_pt" in overrides:
                spine.set_linewidth(style["line_axis_pt"])
            if "spines" in overrides:
                spine.set_visible(style["spines"] == "all" or
                                  style["spines"] == "left-bottom" and side in {"left", "bottom"})
        if "grid" in overrides:
            ax.grid(style["grid"] == "major", which="major")
        if "background" in overrides:
            ax.set_facecolor(style["background"])
        for line in ax.lines:
            if "line_data_pt" in overrides:
                line.set_linewidth(style["line_data_pt"])
            if "marker_size_pt" in overrides:
                line.set_markersize(style["marker_size_pt"])
        if "marker_size_pt" in overrides:
            for points in ax.collections:
                if isinstance(points, PathCollection) and len(points.get_sizes()) == 1:
                    points.set_sizes([style["marker_size_pt"] ** 2])
    legends = [*fig.legends, *(ax.get_legend() for ax in fig.axes if ax.get_legend())]
    for legend in legends:
        text_size(legend.get_texts(), "legend_text_pt")
        text_size([legend.get_title()], "legend_title_pt")
        if "line_data_pt" in overrides:
            for line in legend.findobj(Line2D):
                line.set_linewidth(style["line_data_pt"])
    if "background" in overrides:
        fig.set_facecolor(style["background"])


def position_axes(fig, target):
    x0, y0, x1, y1 = outer_axes(fig, original=True)
    left, bottom, right, top = target
    sx, sy = (right-left)/(x1-x0), (top-bottom)/(y1-y0)
    for axis in fig.axes:
        if axis.get_visible():
            box = axis.get_position(original=True)
            axis.set_position([left+(box.x0-x0)*sx, bottom+(box.y0-y0)*sy,
                               box.width*sx, box.height*sy])


def fit_decorations(fig):
    """Make room for labels measured at the final physical font sizes."""
    for _ in range(6):
        fig.canvas.draw()
        bounds = outer_axes(fig)
        if not bounds:
            return
        renderer = fig.canvas.get_renderer()
        artists = [axis.get_tightbbox(renderer) for axis in fig.axes if axis.get_visible()]
        artists = [box.transformed(fig.transFigure.inverted()) for box in artists if box is not None]
        if not artists:
            return
        # Leave a PDF/Agg font metrics allowance only at edges that need correction.
        px, py = (2.5 / (72 * inches) for inches in fig.get_size_inches())
        left = max(0, px - min(box.x0 for box in artists))
        bottom = max(0, py - min(box.y0 for box in artists))
        right = max(0, max(box.x1 for box in artists) + px - 1)
        top = max(0, max(box.y1 for box in artists) + py - 1)
        if max(left, bottom, right, top) < .0005:
            return
        x0, y0, x1, y1 = bounds
        target = (x0 + left, y0 + bottom, x1 - right, y1 - top)
        if target[2] <= target[0] or target[3] <= target[1]:
            return
        if hasattr(fig, "set_layout_engine"):
            fig.set_layout_engine("none")
        position_axes(fig, target)
    fig.canvas.draw()


def main():
    script, output, metadata = sys.argv[1:]
    context = plate.context
    style, size = context["style"], context["size_mm"]
    mpl.rcParams.update({"pdf.fonttype": 42, "svg.fonttype": "none",
                         "figure.figsize": [mm / 25.4 for mm in size], "savefig.bbox": None})
    if context["inject"]:
        apply_style(style, context["palette"])
    sys.path.insert(0, str(Path(script).parent))
    namespace = runpy.run_path(script, init_globals={"plate": plate}, run_name="__main__")
    fig = namespace.get("fig")
    if not isinstance(fig, mpl.figure.Figure):
        if not plt.get_fignums():
            raise ValueError("The script did not create a matplotlib figure.")
        fig = plt.gcf()
    fig.set_size_inches(*(mm / 25.4 for mm in size))
    if context["inject"] and context.get("overrides"):
        apply_overrides(fig, style, context["overrides"])
    fit_decorations(fig)
    bounds = outer_axes(fig)
    if bounds and context.get("fixed_axes"):
        if hasattr(fig, "set_layout_engine"):
            fig.set_layout_engine("none")
        position_axes(fig, context["fixed_axes"])
        fit_decorations(fig)
        bounds = outer_axes(fig)
    with mpl.rc_context({"savefig.bbox": None, "pdf.fonttype": 42}):
        fig.savefig(output, format="pdf", bbox_inches=None, dpi=300,
                    transparent=context["inject"] and style["background"] == "none")
    Path(metadata).write_text(json.dumps({"axes": bounds}))


if __name__ == "__main__":
    main()
