"""Resolve physical style tokens and the panel's plotting box."""

import json

from .model import ROOT

HELPERS = ROOT / "helpers"
DEFAULTS = json.loads((HELPERS / "python/plate/defaults.json").read_text())
TOKENS = DEFAULTS["style"]
ROLE_OFFSETS = {
    "axis_title_pt": 0, "tick_label_pt": -1, "legend_title_pt": 0,
    "legend_text_pt": -1, "annotation_pt": 0, "panel_label_pt": 1,
}
BUILTINS = {
    "okabe-ito": {"name": "Okabe–Ito", "safe": True, "colors": DEFAULTS["palette"]},
    "viridis": {"name": "Viridis", "safe": True,
                "colors": ["#440154", "#414487", "#2A788E", "#22A884", "#7AD151", "#FDE725"]},
    "tableau": {"name": "Tableau 10", "safe": False, "colors": [
        "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
        "#EDC949", "#AF7AA1", "#FF9DA7", "#9C755F", "#BAB0AC"]},
    "greys": {"name": "Greyscale", "safe": True,
              "colors": ["#242424", "#545454", "#777777", "#A3A3A3", "#D4D4D4"]},
}
MM_PER_IN = 25.4
PT_PER_MM = 72 / MM_PER_IN


def resolve(project, panel=None):
    overrides = panel.overrides if panel else {}
    style = {**TOKENS, **project.style, **{key: value for key, value in overrides.items()
                                            if key in TOKENS}}
    for role, offset in ROLE_OFFSETS.items():
        if style[role] is None:
            style[role] = max(style["font_min_pt"], style["font_main_pt"] + offset)
    palette_id = overrides.get("palette", project.palettes.get("active", "okabe-ito"))
    palettes = {**BUILTINS, **project.palettes.get("custom", {})}
    colors = {**project.palettes.get("colors", {}), **overrides.get("colors", {})}
    return {"style": style, "palette": palettes.get(palette_id, BUILTINS["okabe-ito"])["colors"],
            "colors": colors, "inject": not overrides.get("opt_out", False)}


def content_box(rect, panel, style):
    reservation = style["label_reserve_mm"] if panel.label or not style["collapse_empty_labels"] else 0
    if rect["h"] - reservation < 1:
        raise ValueError("The label reservation leaves less than 1 mm for panel content.")
    return {**rect, "y": rect["y"] + reservation, "h": rect["h"] - reservation}


def context_for(project, panel, rect):
    context = resolve(project, panel)
    box = content_box(rect, panel, context["style"])
    return {**context, "size_mm": [round(box["w"], 8), round(box["h"], 8)]}
