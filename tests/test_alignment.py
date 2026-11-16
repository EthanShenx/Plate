from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

from plate.alignment import absolute_axes, fixed_axes
from plate.bundle import save_bundle
from plate.interpreters import probe
from plate.layout import Layout, leaf, split
from plate.model import Panel, Project
from plate.server import Session
from plate.style import content_box, resolve


class Alignment(unittest.TestCase):
    def test_insets_are_shared_within_panels(self):
        a, b = Panel(), Panel()
        layout = {"mode": "grid", "rects": {
            a.id: {"x": 4, "y": 4, "w": 40, "h": 40},
            b.id: {"x": 48, "y": 4, "w": 40, "h": 40},
        }}
        project = Project(panels=[a, b], layout=layout,
                          alignment=[{"axis": "row", "panels": [a.id, b.id]}])
        boxes = Layout(project).rects
        measured = {
            a.id: [.1, .2, .9, .9], b.id: [.1, .1, .9, .8],
        }
        targets, warnings = fixed_axes(project, boxes, measured)
        self.assertFalse(warnings)
        self.assertEqual(targets[a.id][3], .8)
        self.assertAlmostEqual(targets[b.id][1], .2)
        shifted = {**boxes, b.id: {**boxes[b.id], "y": boxes[b.id]["y"] + 16}}
        self.assertEqual(fixed_axes(project, shifted, measured), (targets, warnings))
        shifted[b.id]["h"] -= 8
        targets, warnings = fixed_axes(project, shifted, measured)
        self.assertFalse(warnings)
        heights = []
        for panel in (a, b):
            box = content_box(shifted[panel.id], panel, resolve(project, panel)["style"])
            axes = absolute_axes(box, targets.get(panel.id, measured[panel.id]))
            heights.append(axes[3] - axes[1])
        self.assertAlmostEqual(heights[0] - heights[1], 8)

    def test_align_mixed_python_and_r(self):
        rscript = shutil.which("Rscript")
        if not rscript or probe(rscript, "script-r")["missing"]:
            self.skipTest("Rscript or R plotting packages unavailable")
        if probe(sys.executable, "script-py")["missing"]:
            self.skipTest("Python matplotlib unavailable")
        a = Panel(type="script-r", interpreter=rscript, script='''
d <- data.frame(x=1:4, y=1:4, group=c("A", "A", "B", "B"))
p <- ggplot(d, aes(x,y)) + geom_point() + facet_wrap(~group) + labs(x="x", y="y")
''')
        b = Panel(type="script-py", interpreter=sys.executable, script='''
import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 2)
fig.subplots_adjust(bottom=.28, top=.73)
for ax in axes:
    ax.plot([1, 2], [3, 4])
''')
        project = Project(panels=[a, b], layout=split("x", [leaf(a.id), leaf(b.id)]),
                          alignment=[{"axis": "row", "panels": [a.id, b.id]}])
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            bundle = root / "test.plate"
            save_bundle(project, root / "source", bundle)
            session = Session(bundle, root / "open")
            session.refresh([b.id])
            renders = session.state()["renders"]
            edges = []
            for panel in (a, b):
                render = renders[panel.id]
                self.assertEqual(render["state"], "fresh", render)
                self.assertFalse(render["warnings"], render)
                edges.append(absolute_axes(render["box"], render["metadata"]["axes"]))
            self.assertAlmostEqual(edges[0][1], edges[1][1], delta=.15)
            self.assertAlmostEqual(edges[0][3], edges[1][3], delta=.15)
            y = Layout(session.project).rects[b.id]["y"]
            delta = 3
            moved = session.update_layout({
                "kind": "edit", "panel": b.id, "field": "y", "value": y + delta,
                "auto_render": True,
            })
            self.assertEqual(moved["panels_to_refresh"], [])
            for panel in (a, b):
                render = moved["renders"][panel.id]
                self.assertEqual(render["state"], "fresh")
                self.assertEqual(render["key"], renders[panel.id]["key"])
            render = moved["renders"][b.id]
            moved_edges = absolute_axes(render["box"], render["metadata"]["axes"])
            self.assertAlmostEqual(moved_edges[1] - edges[0][1], delta, delta=.15)
            self.assertAlmostEqual(moved_edges[3] - edges[0][3], delta, delta=.15)

            height_delta = 15
            resized = session.update_layout({
                "kind": "edit", "panel": b.id, "field": "h",
                "value": moved["geometry"]["rects"][b.id]["h"] - height_delta, "auto_render": True,
            })
            self.assertCountEqual(resized["panels_to_refresh"], [a.id, b.id])
            session.refresh([b.id])
            final = session.state()
            insets = []
            heights = []
            for panel in (a, b):
                render = final["renders"][panel.id]
                self.assertEqual(render["state"], "fresh", render)
                self.assertFalse(render["warnings"], render)
                rect = final["geometry"]["rects"][panel.id]
                _, top, _, bottom = absolute_axes(render["box"], render["metadata"]["axes"])
                insets.append((top - rect["y"], rect["y"] + rect["h"] - bottom))
                heights.append(bottom - top)
            self.assertAlmostEqual(insets[0][0], insets[1][0], delta=.15)
            self.assertAlmostEqual(insets[0][1], insets[1][1], delta=.15)
            self.assertAlmostEqual(heights[0] - heights[1], height_delta, delta=.30)
