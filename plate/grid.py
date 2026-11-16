"""Independent panel rectangles on a figure measured in millimetres."""

from copy import deepcopy
from itertools import product

from .layout import AXES, EPSILON, Layout, number
from .model import Panel

DEFAULT_GRID_STEP = 2


def is_grid(layout):
    return isinstance(layout, dict) and layout.get("mode") == "grid"


def as_grid(project):
    if not is_grid(project.layout):
        project.layout = {"mode": "grid", "rects": Layout(project).rects}


def validate_panel_groups(project):
    panels = {panel.id for panel in project.panels}
    seen_groups = set()
    seen_panels = set()
    for group in project.groups:
        group_id = group["id"]
        name = group["name"]
        members = group["panels"]
        if not isinstance(group_id, str) or not group_id or group_id in seen_groups:
            raise ValueError("Panel groups need unique identifiers.")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Enter a panel group name.")
        if not isinstance(members, list) or len(members) < 2 or len(members) != len(set(members)):
            raise ValueError("Select at least two distinct panels to group.")
        if not set(members) <= panels or seen_panels.intersection(members):
            raise ValueError("Each panel can belong to one group.")
        seen_groups.add(group_id)
        seen_panels.update(members)


def validate_rect(rect, panel, width, height, minimum):
    if not isinstance(rect, dict) or set(rect) != {"x", "y", "w", "h"}:
        raise ValueError("A panel needs X, Y, width and height.")
    for origin, dimension, span in (("x", "w", width), ("y", "h", height)):
        offset = number(rect[origin], f"Panel {origin.upper()}", 0, span)
        size = number(rect[dimension], f"Panel {dimension}", minimum - EPSILON, span)
        if offset + size > span + EPSILON:
            raise ValueError("Keep the panel inside the artboard.")
        if dimension in panel.locks:
            locked = number(panel.locks[dimension], "Locked size", minimum - EPSILON, span)
            if abs(size - locked) > EPSILON:
                raise ValueError("Unlock the panel dimension before resizing it.")
    return rect


def overlaps(a, b, gap=0):
    return (a["x"] + a["w"] + gap > b["x"] + EPSILON and
            b["x"] + b["w"] + gap > a["x"] + EPSILON and
            a["y"] + a["h"] + gap > b["y"] + EPSILON and
            b["y"] + b["h"] + gap > a["y"] + EPSILON)


def initial_rect(layout, position=None):
    step = layout.grid_step
    w = min(layout.width, max(layout.minimum, step * round(layout.width / (3 * step))))
    h = min(layout.height, max(layout.minimum, step * round(layout.height / (3 * step))))
    if position is not None:
        return dict(x=min(layout.width - w, number(position["x"], "X", 0, layout.width)),
                    y=min(layout.height - h, number(position["y"], "Y", 0, layout.height)), w=w, h=h)
    # Try existing edges plus the preferred gap before using a staggered position.
    def snap_up(value):
        return int((value + step - EPSILON) // step) * step

    margin_x = min(snap_up(layout.margin), layout.width - w)
    margin_y = min(snap_up(layout.margin), layout.height - h)
    existing = layout.rects.values()
    xs = {margin_x, *(snap_up(r["x"] + r["w"] + layout.gutter) for r in existing)}
    ys = {margin_y, *(snap_up(r["y"] + r["h"] + layout.gutter) for r in existing)}
    for y, x in product(sorted(ys), sorted(xs)):
        candidate = dict(x=x, y=y, w=w, h=h)
        if x + w <= layout.width and y + h <= layout.height and not any(
                overlaps(candidate, other, layout.gutter) for other in existing):
            return candidate
    inset = step * (len(layout.rects) % 7)
    return dict(x=min(layout.width - w, margin_x + inset),
                y=min(layout.height - h, margin_y + inset), w=w, h=h)


def fit_artboard(project):
    """Keep rects inside a newly sized figure, retaining dimensions where possible."""
    for panel in project.panels:
        rect = project.layout["rects"][panel.id]
        for span, (origin, dimension) in zip((project.size.width_mm, project.size.height_mm), AXES.values(), strict=True):
            span = number(span, "Artboard size", 1)
            if dimension not in panel.locks:
                rect[dimension] = min(rect[dimension], span)
            rect[origin] = max(0, min(rect[origin], span - rect[dimension]))


def apply_grid(project, operation):
    """Apply a grid edit to a copy, so a failed edit leaves the project intact."""
    project = deepcopy(project)
    as_grid(project)
    layout = Layout(project)
    rects = project.layout["rects"]
    panel_id = operation.get("panel")
    kind = operation["kind"]
    if kind == "add":
        panel = Panel(type=operation["type"], name=operation["name"])
        rects[panel.id] = initial_rect(layout, operation.get("position"))
        project.panels.append(panel)
    else:
        panel = layout.panels[panel_id]
        rect = rects[panel_id]
        if kind == "delete":
            project.panels.remove(panel)
            del rects[panel_id]
            for group in project.groups:
                group["panels"] = [member for member in group["panels"] if member != panel_id]
            project.groups = [group for group in project.groups if len(group["panels"]) >= 2]
        elif kind == "place":
            rects[panel_id] = deepcopy(operation["rect"])
        elif kind == "edit":
            field = operation["field"]
            if field not in rect:
                raise ValueError("Unknown panel dimension.")
            rect[field] = operation["value"]
        elif kind == "lock":
            field = operation["field"]
            if field not in {"w", "h"}:
                raise ValueError("Only width and height can be locked.")
            if operation["enabled"]:
                panel.locks[field] = rect[field]
            else:
                panel.locks.pop(field, None)
        elif kind == "stack":
            direction = operation["direction"]
            if direction not in {"front", "back"}:
                raise ValueError("Unknown stacking direction.")
            project.panels.remove(panel)
            project.panels.insert(len(project.panels) if direction == "front" else 0, panel)
        else:
            raise ValueError("Unknown layout operation.")
    Layout(project)
    return project
