"""The resolved Plate context, also usable in standalone scripts."""

import json
import os
from pathlib import Path


def load(path=None):
    defaults = json.loads(Path(__file__).with_name("defaults.json").read_text())
    path = path or os.environ.get("PLATE_STYLE")
    override = json.loads(Path(path).read_text()) if path else {}
    context = {**defaults, **override, "style": {**defaults["style"], **override.get("style", {})}}
    style = context["style"]
    for token, offset in {
        "axis_title_pt": 0, "tick_label_pt": -1, "legend_title_pt": 0,
        "legend_text_pt": -1, "annotation_pt": 0, "panel_label_pt": 1,
    }.items():
        if style[token] is None:
            style[token] = max(style["font_min_pt"], style["font_main_pt"] + offset)
    return context


context = load()
colors = context["colors"]
palette = context["palette"]
size_mm = context["size_mm"]
style = context["style"]
