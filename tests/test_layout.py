from itertools import combinations
from random import Random
import unittest

from plate.layout import CORNERS, EDGES, Layout, apply, leaf, split
from plate.model import Panel, Project


class LayoutTests(unittest.TestCase):
    def assert_tiling(self, project):
        layout = Layout(project)
        occupied = 0
        for r in layout.rects.values():
            self.assertGreaterEqual(min(r["w"], r["h"]) + 1e-6, layout.minimum)
            self.assertGreaterEqual(min(r["x"], r["y"]) + 1e-6, layout.margin)
            self.assertLessEqual(r["x"] + r["w"], layout.width - layout.margin + 1e-6)
            self.assertLessEqual(r["y"] + r["h"], layout.height - layout.margin + 1e-6)
            occupied += r["w"] * r["h"]
        for a, b in combinations(layout.rects.values(), 2):
            horizontal = max(a["x"] - b["x"] - b["w"], b["x"] - a["x"] - a["w"])
            vertical = max(a["y"] - b["y"] - b["h"], b["y"] - a["y"] - a["h"])
            self.assertGreaterEqual(max(horizontal, vertical) + 1e-6, layout.gutter)
        for handle in layout.handles.values():
            occupied += handle["length"] * layout.gutter
        if layout.rects:
            frame = (layout.width - 2 * layout.margin) * (layout.height - 2 * layout.margin)
            self.assertAlmostEqual(occupied, frame, delta=1e-6)

    def test_random_sequences(self):
        rng = Random(1013)
        for _ in range(2000):
            project = Project()
            for _ in range(18):
                ids = [panel.id for panel in project.panels]
                panel = rng.choice(ids) if ids else None
                handles = list(Layout(project).handles)
                edge = rng.choice(["left", "right", "top", "bottom"])
                choices = [{"kind": "add", "panel": panel, "edge": edge,
                            "type": "script-py", "name": "Panel"}]
                if ids:
                    choices.extend([
                        {"kind": "delete", "panel": panel},
                        {"kind": "lock", "panel": panel, "field": rng.choice(["w", "h"]),
                         "enabled": rng.choice([True, False])},
                        {"kind": "edit", "panel": panel, "field": rng.choice(["w", "h", "x", "y"]),
                         "value": rng.uniform(12, 150)},
                    ])
                if handles:
                    choices.extend([
                        {"kind": "resize", "handle": rng.choice(handles), "delta": rng.uniform(-80, 80)},
                        {"kind": "resize-corner", "panel": panel, "corner": rng.choice(list(CORNERS)),
                         "dx": rng.uniform(-80, 80), "dy": rng.uniform(-80, 80), "snap": 1},
                        {"kind": "move", "panel": panel, "target": rng.choice(ids + [None]),
                         "edge": edge},
                        {"kind": "move", "panel": panel, "target": rng.choice(ids), "edge": "center"},
                    ])
                try:
                    project = apply(project, rng.choice(choices))
                except ValueError:
                    pass
                self.assert_tiling(project)

    def test_collinear_edges_resize_together(self):
        project = Project()
        for index, edge in enumerate(("right", "bottom", "right", "right")):
            target = project.panels[index - 2].id if index >= 2 else None
            project = apply(project, {"kind": "add", "panel": target, "edge": edge,
                                      "type": "script-r", "name": str(index)})
        before = Layout(project)
        vertical = [key for key, item in before.handles.items() if item["axis"] == "x"]
        result = Layout(apply(project, {"kind": "resize", "handle": vertical[0], "delta": 10}))
        self.assertEqual(len(vertical), 2)
        for key in vertical:
            self.assertAlmostEqual(result.handles[key]["at"], before.handles[key]["at"] + 10)

    def test_all_corners_move_their_two_edges(self):
        rows = [[Panel() for _ in range(3)] for _ in range(3)]
        selected = rows[1][1].id
        project = Project(panels=[panel for row in rows for panel in row], layout=split("y", [
            split("x", [leaf(panel.id) for panel in row]) for row in rows
        ]))
        original = Layout(project)
        before = original.rects[selected]
        self.assertEqual(set(original.view()["panel_edges"][selected]), set(EDGES))
        for corner, (horizontal, vertical) in CORNERS.items():
            with self.subTest(corner=corner):
                resized = apply(project, {"kind": "resize-corner", "panel": selected,
                                          "corner": corner, "dx": 5, "dy": 4})
                rect = Layout(resized).rects[selected]
                self.assertAlmostEqual(rect["x"], before["x"] + (5 if horizontal == "left" else 0))
                self.assertAlmostEqual(rect["y"], before["y"] + (4 if vertical == "top" else 0))
                self.assertAlmostEqual(rect["w"], before["w"] + (5 if horizontal == "right" else -5))
                self.assertAlmostEqual(rect["h"], before["h"] + (4 if vertical == "bottom" else -4))
                self.assert_tiling(resized)
        self.assertEqual(Layout(project).rects, original.rects)

    def test_corner_keeps_margin_and_respects_locked_neighbor(self):
        a, b, c = (Panel() for _ in range(3))
        project = Project(panels=[a, b, c], layout=split("y", [
            split("x", [leaf(a.id), leaf(b.id)]), leaf(c.id),
        ]))
        before = Layout(project)
        b.locks["w"] = before.rects[b.id]["w"]
        self.assertEqual(before.view()["panel_edges"][a.id], ["right", "bottom"])
        for corner, expected_height in (("top-right", before.rects[a.id]["h"]),
                                       ("bottom-right", before.minimum)):
            with self.subTest(corner=corner):
                resized = apply(project, {"kind": "resize-corner", "panel": a.id,
                                          "corner": corner, "dx": 20, "dy": -100})
                rect = Layout(resized).rects[a.id]
                self.assertAlmostEqual(rect["y"], before.rects[a.id]["y"])
                self.assertAlmostEqual(rect["w"], before.rects[a.id]["w"])
                self.assertAlmostEqual(rect["h"], expected_height)
                self.assert_tiling(resized)
