"""Executed in the plotting interpreter, independently of the server."""

import json
from pathlib import Path
import runpy
import sys
import warnings

import matplotlib as mpl
from matplotlib import font_manager, pyplot as plt
from matplotlib.axes import Axes

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


def outer_axes(fig):
    boxes = [axis.get_position() for axis in fig.axes if axis.get_visible()]
    if not boxes:
        return None
    return [min(box.x0 for box in boxes), min(box.y0 for box in boxes),
            max(box.x1 for box in boxes), max(box.y1 for box in boxes)]


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
    fig.canvas.draw()
    bounds = outer_axes(fig)
    if bounds and context.get("fixed_axes"):
        left, bottom, right, top = context["fixed_axes"]
        x0, y0, x1, y1 = bounds
        sx, sy = (right-left)/(x1-x0), (top-bottom)/(y1-y0)
        if hasattr(fig, "set_layout_engine"):
            fig.set_layout_engine("none")
        for axis in fig.axes:
            if not axis.get_visible():
                continue
            box = axis.get_position()
            axis.set_position([left+(box.x0-x0)*sx, bottom+(box.y0-y0)*sy,
                               box.width*sx, box.height*sy])
        fig.canvas.draw()
        bounds = outer_axes(fig)
    with mpl.rc_context({"savefig.bbox": None, "pdf.fonttype": 42}):
        fig.savefig(output, format="pdf", bbox_inches=None, dpi=300,
                    transparent=context["inject"] and style["background"] == "none")
    Path(metadata).write_text(json.dumps({"axes": bounds}))


if __name__ == "__main__":
    main()
