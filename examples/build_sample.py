"""Build the portable, deterministic-input Nature double-column sample."""

from hashlib import sha256
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFilter

from plate.bundle import save_bundle
from plate.layout import Layout, leaf, split
from plate.model import FigureSize, Panel, Project

EXAMPLE = Path(__file__).resolve().parent
FACETS = '''library(ggplot2)
d <- expand.grid(Time = seq(0, 12, by = 2), Region = c("Cortex", "Medulla"))
d$Signal <- 0.18 + 0.55 * (1 - exp(-d$Time / 5)) +
  ifelse(d$Region == "Cortex", .1, -.05)
p <- ggplot(d, aes(Time, Signal)) +
  geom_line(colour = "#0072B2") + geom_point(colour = "#0072B2") +
  facet_wrap(~Region) +
  scale_x_continuous(breaks = c(0, 4, 8, 12)) +
  scale_y_continuous(limits = c(0, 1), breaks = c(0, .5, 1)) +
  labs(x = "Time (h)", y = "Normalised signal")
'''
SUBPLOTS = '''import matplotlib.pyplot as plt
import numpy as np

t = np.arange(0, 13, 2)
fig, axes = plt.subplots(1, 2, sharey=True)
fig.subplots_adjust(left=.17, right=.96, bottom=.24, top=.84, wspace=.37)
for ax, (name, tau, color) in zip(axes, [
    ("Early", 3.4, "#0072B2"), ("Late", 6.0, "#009E73")
]):
    ax.plot(t, .15 + .7 * (1 - np.exp(-t/tau)), marker="o", color=color)
    ax.set(title=name, xlabel="Time (h)", xticks=[0, 4, 8, 12],
           yticks=[0, .5, 1], ylim=(0, 1))
axes[0].set_ylabel("Normalised signal")
'''
SEMANTIC_R = '''library(ggplot2)
d <- expand.grid(Dose = 0:5, Group = c("Control", "Treatment"))
d$Response <- 0.12 + ifelse(d$Group == "Treatment", .13, .045) * d$Dose
p <- ggplot(d, aes(Dose, Response, colour=Group)) +
  geom_line() + geom_point() +
  scale_colour_manual(values=plate$colors) +
  scale_y_continuous(limits=c(0, 1), breaks=c(0, .25, .5, .75, 1)) +
  labs(x="Dose (a.u.)", y="Response") + theme(legend.position="none")
'''
SEMANTIC_PY = '''import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import plate

rng = np.random.default_rng(42)
groups = ["Control", "Treatment"]
values = np.concatenate([rng.normal(.39, .075, 24), rng.normal(.67, .10, 24)])
fig, ax = plt.subplots()
fig.subplots_adjust(left=.21, bottom=.21, right=.93, top=.91)
sns.stripplot(x=np.repeat(groups, 24), y=values, hue=np.repeat(groups, 24),
              palette=plate.colors, legend=False, jitter=False, ax=ax,
              size=plate.style["marker_size_pt"])
ax.set(xlabel="", ylabel="Signal (a.u.)", ylim=(0, 1), yticks=[0, .25, .5, .75, 1])
'''


def microscopy(path):
    rng = Random(172)
    width, height = 900, 670
    layers = [Image.new("L", (width, height), base) for base in (13, 20, 19)]
    glow, nuclei = (ImageDraw.Draw(layer) for layer in layers[1:])
    for _ in range(57):
        x, y = rng.randrange(25, width-25), rng.randrange(25, height-25)
        radius = rng.randrange(15, 46)
        glow.ellipse((x-radius, y-radius*.75, x+radius, y+radius*.75),
                     fill=rng.randrange(45, 109))
        radius = rng.randrange(4, 13)
        nuclei.ellipse((x-radius, y-radius, x+radius, y+radius), fill=rng.randrange(130, 230))
    merged = Image.merge("RGB", (layers[0], layers[1].filter(ImageFilter.GaussianBlur(14)),
                                 layers[2].filter(ImageFilter.GaussianBlur(4))))
    merged.save(path)


def main():
    panels = [
        Panel(id="facet", type="script-r", name="Time course by region", label="a", script=FACETS),
        Panel(id="subplots", type="script-py", name="Early and late time courses", label="b", script=SUBPLOTS),
        Panel(id="response", type="script-r", name="Dose response", label="c", script=SEMANTIC_R),
        Panel(id="distribution", type="script-py", name="Signal distribution", label="d", script=SEMANTIC_PY),
        Panel(id="microscopy", type="image", name="Synthetic microscopy", label="e",
              settings={"fit": "cover", "filename": "microscopy.png"}),
        Panel(id="legend", type="legend", name="Shared treatment legend", label="f",
              settings={"direction": "horizontal", "swatch": "line"}),
    ]
    row1 = split("x", [leaf(p.id) for p in panels[:2]])
    row2 = split("x", [leaf(p.id) for p in panels[2:5]])
    row3 = leaf(panels[5].id)
    row1["id"], row2["id"] = "row-one", "row-two"
    row2["weights"] = [1, 1, 1.2]
    tree = split("y", [row1, row2, row3])
    tree["id"], tree["weights"] = "rows", [49, 48, 12]
    project = Project(
        id="nature-double", name="Nature double · Signal response",
        size=FigureSize(width_mm=183, height_mm=123), panels=panels, layout=tree,
        style={"font_family": "Arial", "font_main_pt": 7, "font_min_pt": 5,
               "line_axis_pt": .5, "line_data_pt": .75, "margin_mm": 4, "gutter_mm": 3},
        palettes={"active": "okabe-ito", "colors": {"Control": "#62666B", "Treatment": "#D55E00"}},
        alignment=[{"axis": "row", "panels": ["facet", "subplots"]}],
    )
    Layout(project)
    with TemporaryDirectory() as scratch:
        workspace = Path(scratch)
        path = workspace / "microscopy.png"
        microscopy(path)
        data = path.read_bytes()
        panels[4].asset = f"assets/{sha256(data).hexdigest()}.png"
        (workspace / "assets").mkdir()
        (workspace / panels[4].asset).write_bytes(data)
        save_bundle(project, workspace, EXAMPLE / "nature-double.plate")


if __name__ == "__main__":
    main()
