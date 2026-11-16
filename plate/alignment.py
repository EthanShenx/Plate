"""Share physical plot insets without forcing panels to share a plot size."""

from hashlib import sha256
import json

from .model import SCRIPT_EXTENSIONS
from .render import signature
from .style import content_box, resolve


def validate_groups(project):
    ids = {panel.id for panel in project.panels if panel.type in SCRIPT_EXTENSIONS}
    seen = set()
    for group in project.alignment:
        axis, members = group["axis"], group["panels"]
        if axis not in {"row", "column"} or len(members) < 2 or len(set(members)) != len(members):
            raise ValueError("An alignment lock needs at least two distinct script panels.")
        for panel in members:
            if panel not in ids or (axis, panel) in seen:
                raise ValueError("A script panel can join one row lock and one column lock.")
            seen.add((axis, panel))


def participating(project, requested):
    members = set(requested)
    while True:
        expanded = members | {panel for group in project.alignment
                              if members.intersection(group["panels"]) for panel in group["panels"]}
        if expanded == members:
            return expanded
        members = expanded


def dependency_signature(project, panel, rects):
    own = signature(project, panel, rects[panel.id])
    ids = participating(project, {panel.id})
    groups = [group for group in project.alignment if ids.intersection(group["panels"])]
    if not groups:
        return own
    members = [(other.id, rects[other.id]["w"], rects[other.id]["h"],
                signature(project, other, rects[other.id]))
               for other in project.panels if other.id in ids]
    return sha256(json.dumps(["shared-panel-insets", groups, members], sort_keys=True).encode()).hexdigest()


def absolute_axes(box, axes):
    left, bottom, right, top = axes
    return [box["x"] + left*box["w"], box["y"] + (1-top)*box["h"],
            box["x"] + right*box["w"], box["y"] + (1-bottom)*box["h"]]


def normalized_axes(box, axes):
    left, top, right, bottom = axes
    return [(left-box["x"])/box["w"], 1-(bottom-box["y"])/box["h"],
            (right-box["x"])/box["w"], 1-(top-box["y"])/box["h"]]


def fixed_axes(project, rects, measured):
    """Return target normalized axes and warnings keyed by panel ID."""
    boxes = {panel.id: content_box({**rects[panel.id], "x": 0, "y": 0},
                                  panel, resolve(project, panel)["style"])
             for panel in project.panels if panel.id in measured and measured[panel.id]}
    natural = {id: absolute_axes(box, measured[id]) for id, box in boxes.items()}
    adjusted = {id: bounds.copy() for id, bounds in natural.items()}
    warnings = {}
    for group in project.alignment:
        ids = group["panels"]
        if not set(ids).intersection(measured):
            continue
        i, j, dimension = (1, 3, "h") if group["axis"] == "row" else (0, 2, "w")
        if all(id in natural for id in ids):
            extent = {id: rects[id][dimension] for id in ids}
            leading = max(natural[id][i] for id in ids)
            trailing = max(extent[id] - natural[id][j] for id in ids)
            if min(extent.values()) - leading - trailing >= 1:
                for id in ids:
                    adjusted[id][i] = leading
                    adjusted[id][j] = extent[id] - trailing
                continue
            message = f"The shared {group['axis']} margins leave too little plot area in the smallest panel."
        else:
            message = f"The {group['axis']} lock needs measurable axes in every panel."
        for id in ids:
            warnings.setdefault(id, []).append(message)
    targets = {id: normalized_axes(boxes[id], axes) for id, axes in adjusted.items()
               if any(abs(target - current) > 1e-8 for target, current in zip(axes, natural[id], strict=True))}
    return targets, warnings
