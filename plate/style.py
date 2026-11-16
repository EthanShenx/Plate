"""Resolve physical style tokens and the panel's plotting box."""

import json
import re

from .model import ROOT, SCRIPT_EXTENSIONS

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
                                            if key in TOKENS and not key.startswith("label_offset_")}}
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
    if panel.label:
        from .fonts import label_metrics

        _, _, bounds = label_metrics(panel.label, rect["w"] * PT_PER_MM, (rect["h"]-1) * PT_PER_MM, style)
        reservation = max(reservation, (bounds[3] + 1) / PT_PER_MM)
    if rect["h"] - reservation < 1:
        raise ValueError("Increase panel height or reduce the space for labels.")
    return {**rect, "y": rect["y"] + reservation, "h": rect["h"] - reservation}


def context_for(project, panel, rect):
    context = resolve(project, panel)
    box = content_box(rect, panel, context["style"])
    references = panel.settings.get("geometry_refs")
    if references and panel.type in SCRIPT_EXTENSIONS:
        from .layout import Layout

        layout = Layout(project)
        panel_boxes = {}
        for panel_id in references:
            if panel_id not in layout.panels:
                continue
            other = layout.panels[panel_id]
            target = content_box(layout.rects[panel_id], other, resolve(project, other)["style"])
            panel_boxes[panel_id] = {
                "x": round(target["x"] - box["x"], 8), "y": round(target["y"] - box["y"], 8),
                "w": round(target["w"], 8), "h": round(target["h"], 8),
            }
        context["panel_boxes_mm"] = panel_boxes
    if panel.type in SCRIPT_EXTENSIONS and context["inject"]:
        # The workers reapply explicit panel overrides after the script sets its defaults.
        keys = {key for key in panel.overrides if key in TOKENS}
        if keys.intersection({"font_main_pt", "font_min_pt"}):
            keys.update(role for role in ROLE_OFFSETS
                        if panel.overrides.get(role, project.style.get(role)) is None)
        context["overrides"] = sorted(keys)
    return {**context, "size_mm": [round(box["w"], 8), round(box["h"], 8)]}


ENUMS = {
    "panel_label_weight": ("normal", "bold"),
    "tick_direction": ("in", "out"),
    "spines": ("all", "left-bottom", "none"),
    "grid": ("none", "major"),
    "background": ("none", "white"),
}


def validate_style(project):
    from .layout import number

    def color(value):
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("Colours must use six-digit hex, for example #0072B2.")

    def semantic(values):
        if not isinstance(values, dict):
            raise ValueError("Semantic colours must be a map.")
        for key, value in values.items():
            if not key.strip():
                raise ValueError("A semantic colour needs a nonempty name.")
            color(value)

    palettes = {**BUILTINS, **project.palettes.get("custom", {})}
    for item in palettes.values():
        if not item["name"].strip() or not item["colors"]:
            raise ValueError("Each palette needs a name and at least one colour.")
        for value in item["colors"]:
            color(value)
    if project.palettes.get("active", "okabe-ito") not in palettes:
        raise ValueError("The selected palette is missing.")
    semantic(project.palettes.get("colors", {}))
    for panel in project.panels:
        if "geometry_refs" in panel.settings:
            references = panel.settings["geometry_refs"]
            if (panel.type not in SCRIPT_EXTENSIONS or not isinstance(references, list) or
                    any(not isinstance(ref, str) or not ref or ref == panel.id for ref in references) or
                    len(references) != len(set(references))):
                raise ValueError("Script geometry references need distinct IDs of other panels.")
        crop = panel.settings.get("crop")
        if crop is not None:
            if len(crop) != 4:
                raise ValueError("Crop needs x, y, width and height.")
            x, y, w, h = [number(value, "Crop fraction", 0, 1) for value in crop]
            if min(w, h) <= 0 or max(x + w, y + h) > 1.00000001:
                raise ValueError("Crop must fit within the source image and have positive dimensions.")
    for values in [project.style, *(panel.overrides for panel in project.panels)]:
        for key, value in values.items():
            if key in ROLE_OFFSETS and value is None:
                continue
            if key == "font_family":
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("Enter a font family.")
            elif key in ENUMS:
                if value not in ENUMS[key]:
                    raise ValueError(f"Invalid value for {key}.")
            elif key in {"collapse_empty_labels", "opt_out"}:
                if not isinstance(value, bool):
                    raise ValueError(f"{key} must be true or false.")
            elif key == "palette":
                if value not in palettes:
                    raise ValueError("The override palette is missing.")
            elif key == "colors":
                semantic(value)
            elif key in TOKENS:
                low = 1 if key.startswith("font_") or key in ROLE_OFFSETS else 0
                if key.startswith("label_offset_"):
                    low = -100
                number(value, key.replace("_", " "), low, 500)
    number(project.timeout_s, "Render timeout", 1, 3600)
