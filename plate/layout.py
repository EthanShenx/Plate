"""Guillotine layout in millimetres with recursive minimum and fixed spans."""

from copy import deepcopy
from dataclasses import dataclass
import math

from .model import PANEL_TYPES, Panel, new_id

EPSILON = 1e-7
AXES = {"x": ("x", "w"), "y": ("y", "h")}
EDGES = {"left": ("x", False), "right": ("x", True),
         "top": ("y", False), "bottom": ("y", True)}
CORNERS = {
    "top-left": ("left", "top"), "top-right": ("right", "top"),
    "bottom-left": ("left", "bottom"), "bottom-right": ("right", "bottom"),
}


@dataclass(frozen=True)
class Span:
    minimum: float
    fixed: float | None = None


def number(value, label, low=0, high=5000):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number.")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be between {low} and {high}.")
    return value


def leaf(panel):
    return {"panel": panel}


def split(axis, children):
    return {"id": new_id(), "axis": axis, "children": children, "weights": [1] * len(children)}


def check_span(span, size):
    if size < span.minimum - EPSILON:
        raise ValueError("The frame cannot fit the minimum panel sizes and gutters.")
    if span.fixed is not None and abs(size - span.fixed) > EPSILON:
        raise ValueError("Panel size locks conflict with this layout or figure size.")


class Layout:
    def __init__(self, project):
        self.project = project
        self.gutter = number(project.style.get("gutter_mm", 3), "Gutter")
        self.margin = number(project.style.get("margin_mm", 4), "Margin")
        self.minimum = number(project.size.minimum_mm, "Minimum panel size", 1)
        self.width = number(project.size.width_mm, "Width", 1)
        self.height = number(project.size.height_mm, "Height", 1)
        self.panels = {panel.id: panel for panel in project.panels}
        self.rects = {}
        self.handles = {}
        self.spans = {}
        self.nodes = {}
        self.seen_panels = set()
        if len(self.panels) != len(project.panels) or any(
            panel.type not in PANEL_TYPES for panel in project.panels
        ):
            raise ValueError("Invalid or duplicate panels.")
        if project.layout:
            self.measure(project.layout)
            self.place(project.layout, self.margin, self.margin,
                       self.width - 2 * self.margin, self.height - 2 * self.margin)
        if self.rects.keys() != self.panels.keys():
            raise ValueError("Panel list and layout must contain the same panels.")

    def measure(self, node):
        if "panel" in node:
            panel_id = node["panel"]
            if panel_id in self.seen_panels or panel_id not in self.panels:
                raise ValueError("Invalid or duplicate layout leaf.")
            self.seen_panels.add(panel_id)
            spans = {}
            for axis, (_, dim) in AXES.items():
                lock = self.panels[panel_id].locks.get(dim)
                if lock is not None:
                    lock = number(lock, "Locked span", self.minimum)
                spans[axis] = Span(lock if lock is not None else self.minimum, lock)
        else:
            key, axis = node["id"], node["axis"]
            if key in self.nodes or axis not in AXES:
                raise ValueError("Invalid or duplicate split.")
            self.nodes[key] = node
            children, weights = node["children"], node["weights"]
            if len(children) < 2 or len(children) != len(weights):
                raise ValueError("Each split needs two or more weighted children.")
            for weight in weights:
                number(weight, "Layout weight", EPSILON, 1e9)
            sizes = [self.measure(child) for child in children]
            spans = {}
            for dim in AXES:
                minima = [size[dim].minimum for size in sizes]
                fixed = [size[dim].fixed for size in sizes if size[dim].fixed is not None]
                if dim == axis:
                    minimum = sum(minima) + self.gutter * (len(sizes) - 1)
                    spans[dim] = Span(minimum, minimum if len(fixed) == len(sizes) else None)
                else:
                    minimum = max(minima)
                    if fixed and any(abs(value - minimum) > EPSILON for value in fixed):
                        raise ValueError("Panel size locks conflict across this split.")
                    spans[dim] = Span(minimum, fixed[0] if fixed else None)
        self.spans[id(node)] = spans
        return spans

    def allocate(self, spans, weights, budget):
        sizes = [span.fixed for span in spans]
        remaining = {i for i, size in enumerate(sizes) if size is None}
        budget -= sum(size for size in sizes if size is not None)
        while remaining:
            unit = budget / sum(weights[i] for i in remaining)
            clamped = {i for i in remaining if weights[i] * unit < spans[i].minimum - EPSILON}
            if not clamped:
                for i in remaining:
                    sizes[i] = weights[i] * unit
                break
            for i in clamped:
                sizes[i] = spans[i].minimum
                budget -= sizes[i]
            remaining -= clamped
        return sizes

    def place(self, node, x, y, w, h):
        spans = self.spans[id(node)]
        check_span(spans["x"], w)
        check_span(spans["y"], h)
        if "panel" in node:
            self.rects[node["panel"]] = dict(x=x, y=y, w=w, h=h)
            return
        axis, key = node["axis"], node["id"]
        kids = node["children"]
        spans = [self.spans[id(child)][axis] for child in kids]
        total = w if axis == "x" else h
        sizes = self.allocate(spans, node["weights"], total - self.gutter * (len(kids) - 1))
        cursor = x if axis == "x" else y
        for i, (child, size) in enumerate(zip(kids, sizes, strict=True)):
            self.place(child, cursor, y, size, h) if axis == "x" else self.place(child, x, cursor, w, size)
            cursor += size + self.gutter
            if i < len(kids) - 1:
                self.handles[f"{key}:{i}"] = {
                    "axis": axis, "at": cursor - self.gutter / 2,
                    "start": y if axis == "x" else x, "length": h if axis == "x" else w,
                    "split": key, "index": i, "sizes": sizes,
                }

    def view(self):
        return {
            "rects": self.rects,
            "handles": {key: {field: value for field, value in handle.items()
                              if field not in {"sizes", "split", "index"}}
                        for key, handle in self.handles.items()},
            "panel_edges": {
                panel: [edge for edge in EDGES if self.panel_edge(panel, edge) is not None]
                for panel in self.rects
            },
        }

    def panel_edge(self, panel_id, edge):
        axis, trailing = EDGES[edge]
        origin, dim = AXES[axis]
        other, other_dim = AXES["y" if axis == "x" else "x"]
        rect = self.rects[panel_id]
        position = rect[origin] + (rect[dim] + self.gutter / 2 if trailing else -self.gutter / 2)
        return next((key for key, handle in self.handles.items()
                     if handle["axis"] == axis and abs(handle["at"] - position) <= EPSILON
                     and handle["start"] < rect[other] + rect[other_dim] - EPSILON
                     and handle["start"] + handle["length"] > rect[other] + EPSILON), None)

    def resize_corner(self, panel_id, corner, dx, dy, snap):
        if corner not in CORNERS:
            raise ValueError("Unknown panel corner.")
        snap = number(snap, "Snap distance", 0, 20)
        for edge, delta in zip(CORNERS[corner], (dx, dy), strict=True):
            delta = number(delta, "Movement", -5000, 5000)
            handle = self.panel_edge(panel_id, edge)
            if handle is not None and abs(delta) > EPSILON:
                self.resize(handle, delta, snap)

    def resize(self, handle_id, delta, snap=0):
        handle = self.handles[handle_id]
        axis = handle["axis"]
        delta = number(delta, "Movement", -5000, 5000)
        snap = number(snap, "Snap distance", 0, 20)
        at = handle["at"]
        if snap:
            candidates = [item["at"] for item in self.handles.values() if item["axis"] == axis
                          and abs(item["at"] - at) > EPSILON]
            span = (self.width if axis == "x" else self.height) - 2 * self.margin
            candidates.extend(self.margin + span * ratio for ratio in (1/3, 1/2, 2/3))
            target = min(candidates, key=lambda item: abs(item - at - delta))
            if abs(target - at - delta) <= snap:
                delta = target - at
        linked = [item for item in self.handles.values()
                  if item["axis"] == axis and abs(item["at"] - at) <= EPSILON]
        direction = 1 if delta >= 0 else -1
        amount = abs(delta)
        changes = []
        for item in linked:
            node = self.nodes[item["split"]]
            spans = [self.spans[id(child)][axis] for child in node["children"]]
            sizes = item["sizes"].copy()
            edge = item["index"]
            left = [i for i in range(edge, -1, -1) if spans[i].fixed is None]
            right = [i for i in range(edge + 1, len(sizes)) if spans[i].fixed is None]
            growing, shrinking = (left, right) if direction > 0 else (right, left)
            capacity = sum(max(0, sizes[i] - spans[i].minimum) for i in shrinking)
            amount = min(amount, capacity if growing else 0)
            changes.append((node, spans, sizes, growing, shrinking))
        if amount < EPSILON:
            return
        for node, spans, sizes, growing, shrinking in changes:
            sizes[growing[0]] += amount
            remaining = amount
            for i in shrinking:
                taken = min(remaining, max(0, sizes[i] - spans[i].minimum))
                sizes[i] -= taken
                remaining -= taken
            node["weights"] = sizes

    def edit(self, panel_id, field, value):
        rect = self.rects[panel_id]
        axis = "x" if field in {"x", "w"} else "y"
        origin, dim = AXES[axis]
        value = number(value, field, self.minimum if field == dim else 0)
        delta = value - rect[field]
        if abs(delta) <= EPSILON:
            return
        leading, trailing = ("left", "right") if axis == "x" else ("top", "bottom")
        edges = [(leading, delta)] if field == origin else [(trailing, delta), (leading, -delta)]
        for edge, movement in edges:
            handle = self.panel_edge(panel_id, edge)
            if handle is not None:
                self.resize(handle, movement)
                return
        raise ValueError("That edge is fixed by the figure margin. Move or split the panel first.")


def transform(tree, panel_id, replace):
    if "panel" in tree:
        return replace(tree) if tree["panel"] == panel_id else tree
    children, weights = [], []
    for child, weight in zip(tree["children"], tree["weights"], strict=True):
        next_child = transform(child, panel_id, replace)
        if next_child:
            children.append(next_child)
            weights.append(weight)
    if len(children) <= 1:
        return children[0] if children else None
    return {**tree, "children": children, "weights": weights}


def insert(tree, panel_id, target, edge):
    if not tree:
        return leaf(panel_id)
    axis, after = EDGES[edge]

    def beside(node):
        children = [node, leaf(panel_id)]
        return split(axis, children if after else children[::-1])

    return transform(tree, target, beside) if target else beside(tree)


def apply(project, operation):
    """Apply an operation transactionally, returning a valid new project."""
    project = deepcopy(project)
    kind = operation["kind"]
    panel_id = operation.get("panel")
    tree = project.layout
    if kind == "add":
        panel = Panel(type=operation["type"], name=operation["name"])
        project.panels.append(panel)
        project.layout = insert(tree, panel.id, panel_id, operation.get("edge", "right"))
    elif kind == "delete":
        project.panels = [panel for panel in project.panels if panel.id != panel_id]
        project.layout = transform(tree, panel_id, lambda node: None)
    elif kind == "move":
        target = operation.get("target")
        edge = operation["edge"]
        if target == panel_id:
            return project
        if edge == "center":
            project.layout = transform(tree, panel_id, lambda node: leaf("__swap__"))
            project.layout = transform(project.layout, target, lambda node: leaf(panel_id))
            project.layout = transform(project.layout, "__swap__", lambda node: leaf(target))
        else:
            remaining = transform(tree, panel_id, lambda node: None)
            project.layout = insert(remaining, panel_id, target, edge)
    elif kind == "lock":
        field = operation["field"]
        if field not in {"w", "h"}:
            raise ValueError("Only width and height can be locked.")
        panel = next(panel for panel in project.panels if panel.id == panel_id)
        if operation["enabled"]:
            panel.locks[field] = Layout(project).rects[panel_id][field]
        else:
            panel.locks.pop(field, None)
    elif kind == "resize":
        Layout(project).resize(operation["handle"], operation["delta"], operation.get("snap", 0))
    elif kind == "resize-corner":
        Layout(project).resize_corner(panel_id, operation["corner"], operation["dx"],
                                      operation["dy"], operation.get("snap", 0))
    elif kind == "edit":
        if operation["field"] not in {"x", "y", "w", "h"}:
            raise ValueError("Unknown dimension.")
        Layout(project).edit(panel_id, operation["field"], operation["value"])
    else:
        raise ValueError("Unknown layout operation.")
    Layout(project)
    return project
