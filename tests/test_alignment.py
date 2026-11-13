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


class Alignment(unittest.TestCase):
    def test_insets_are_shared_in_figure_coordinates(self):
        a, b = Panel(), Panel()
        project = Project(panels=[a, b], layout=split("x", [leaf(a.id), leaf(b.id)]),
                          alignment=[{"axis": "row", "panels": [a.id, b.id]}])
        boxes = Layout(project).rects
        targets, warnings = fixed_axes(project, boxes, {
            a.id: [.1, .2, .9, .9], b.id: [.1, .1, .9, .8],
        })
        self.assertFalse(warnings)
        self.assertEqual(targets[a.id][3], .8)
        self.assertAlmostEqual(targets[b.id][1], .2)

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
