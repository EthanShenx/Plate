from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from plate.bundle import write_workspace
from plate.layout import Layout, leaf
from plate.model import Panel, Project
from plate.render import render_script
from plate.interpreters import probe
from plate.style import PT_PER_MM


PYTHON = """
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot([0, 1], [0, 1])
ax.set(xlabel="Axis title", ylabel="Response", xticks=[0, 1], yticks=[0, 1])
ax.annotate("Annotation", (0.4, 0.2))
ax.plot([], [], label="Series")
ax.legend(title="Legend title")
print("runner stdout")
"""
R = """
p <- ggplot(data.frame(x=c(0,1), y=c(0,1), group="Series"), aes(x, y, linetype=group)) +
  geom_line() + annotate("text", x=.4, y=.2, label="Annotation") +
  scale_x_continuous(breaks=c(0,1)) + scale_y_continuous(breaks=c(0,1)) +
  labs(x="Axis title", y="Response", linetype="Legend title")
cat("runner stdout\\n")
"""


class Runners(unittest.TestCase):
    def round_trip(self, language, executable, source):
        if not executable:
            self.skipTest(f"{language} interpreter unavailable")
        missing = probe(executable, language)["missing"]
        if missing:
            self.skipTest(f"{language} missing packages: {', '.join(missing)}")
        panel = Panel(type=language, interpreter=executable, script=source)
        project = Project(panels=[panel], layout=leaf(panel.id))
        project.style.update(font_family="Arial", axis_title_pt=8, tick_label_pt=6,
                             annotation_pt=7, legend_title_pt=9, legend_text_pt=6.5,
                             line_axis_pt=0.5, line_data_pt=0.75, tick_width_pt=0.4)
        with TemporaryDirectory() as scratch:
            workspace = Path(scratch)
            write_workspace(project, workspace)
            rect = Layout(project).rects[panel.id]
            result = render_script(project, panel, rect, workspace, None)
            self.assertIn("runner stdout", result["stdout"])
            self.assertTrue(render_script(project, panel, rect, workspace, None)["cached"])
            sizes = {"Axis title": 8, "Response": 8, "Annotation": 7, "0": 6, "1": 6,
                     "Legend title": 9, "Series": 6.5}
            observed = set()
            for span in result["metadata"]["text"]:
                self.assertIn("Arial", span["font"])
                for token in span["text"].splitlines():
                    if token in sizes:
                        self.assertAlmostEqual(span["size"], sizes[token], delta=.05)
                        observed.add(token)
            self.assertEqual(observed, sizes.keys())
            self.assertIsNotNone(result["metadata"]["axes"])
            with pymupdf.open(workspace / "cache" / f"{result['key']}.pdf") as pdf:
                widths = [item["width"] for item in pdf[0].get_drawings() if item["width"] is not None]
                for target in (.5, .75, .4):
                    self.assertTrue(any(abs(width - target) <= .02 for width in widths), widths)
                self.assertAlmostEqual(pdf[0].rect.width, rect["w"] * PT_PER_MM, delta=.028)

    def test_python_round_trip(self):
        self.round_trip("script-py", sys.executable, PYTHON)

    def test_r_round_trip(self):
        self.round_trip("script-r", shutil.which("Rscript"), R)
