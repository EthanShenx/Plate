import textwrap

import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.patches import Wedge
import numpy as np

mouse = PANEL == "d"
terms = (
    ["Epidermis development", "Skin development", "Keratinocyte differentiation",
     "Epidermal cell differentiation", "Keratinocyte proliferation", "Keratinization",
     "Cornification", "Keratinocyte development", "Desmosome organization",
     "Epithelial cell proliferation"]
    if mouse else
    ["Leukocyte migration", "T cell migration", "Wound healing", "Inflammatory response to wounding",
     "Response to wounding", "Positive regulation of fibroblast proliferation", "Fibroblast migration",
     "Cell matrix adhesion", "Regulation of anoikis", "Apoptotic signaling pathway"]
)
rng = np.random.default_rng(33 if mouse else 34)
counts = rng.integers(8, 56, len(terms))
scores = rng.uniform(2, 18 if mouse else 9, len(terms))
fig = plt.figure()
fig.text(.52, .955, f"{'Mouse' if mouse else 'Human'}-enriched pathways", ha="center")
ax = fig.add_axes([.06, .21, .88, .68])
ax.set(xlim=(-2.5, 2.5), ylim=(-2.15, 2.15), aspect="equal")
ax.set_axis_off()
cmap = plt.colormaps["YlOrRd"]
norm = Normalize(2, 18 if mouse else 9)
angles = 72 - np.arange(len(terms)) * 36
for angle, term, count, score in zip(angles, terms, counts, scores, strict=True):
    r = np.deg2rad(angle)
    x, y = np.cos(r), np.sin(r)
    radius = .87 + count / 140
    ax.add_patch(Wedge((0, 0), radius, angle-17, angle+17, width=radius-.77,
                       facecolor=cmap(norm(score)), edgecolor="white", linewidth=.45))
    ax.text(.61*x, .61*y, str(count), ha="center", va="center", fontsize=5.4)
    ax.plot([1.28*x, 1.43*x], [1.28*y, 1.43*y], color="#969ca6", lw=.4)
    ax.text(1.53*x, 1.48*y, textwrap.fill(term, 17), ha="left" if x > .3 else
            "right" if x < -.3 else "center", va="center", fontsize=4.6, linespacing=1.1)
ax.add_patch(plt.Circle((0, 0), .77, fill=False, edgecolor="#292e36", linewidth=.62))
end = 18 if mouse else 9
bar = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap.reversed()),
                   cax=fig.add_axes([.22, .105, .56, .032]),
                   orientation="horizontal", ticks=[2, end])
bar.ax.set_xticklabels([f"1e-{end}", "1e-2"])
bar.ax.tick_params(length=2, pad=1.5)
bar.set_label("Adjusted p value", labelpad=2)
bar.solids.set_rasterized(False)
