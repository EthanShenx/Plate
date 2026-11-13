from itertools import combinations
from random import Random
import unittest

from plate.layout import Layout, apply
from plate.model import Project


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
