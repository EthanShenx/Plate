import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
import numpy as np

mouse = PANEL == "a"
labels = (
    ["Keratinocyte", "Skeletal muscle progenitor", "Bulge hair-follicle stem cell",
     "Vascular smooth muscle cell", "Schwann cell", "Fibroblast", "Sebaceous gland cell",
     "Immune", "Lymphatic endothelial cell", "Vascular endothelial cell"]
    if mouse else
    ["Vascular endothelial cell", "Smooth muscle cell", "Melanocyte", "Fibroblast",
     "Immune", "Keratinocyte", "Eccrine sweat gland cell"]
)
rng = np.random.default_rng(14 if mouse else 15)
values = np.sort(rng.uniform(.74, .97 if mouse else .91, len(labels)))[::-1]
cmap = plt.colormaps["Reds" if mouse else "GnBu"]
norm = Normalize(.65, 1.0)
fig = plt.figure()
ax = fig.add_axes([.49, .20, .28, .72])
y = np.arange(len(labels))
ax.hlines(y, .7, values, color="#aeb4bc", linewidth=.48)
ax.scatter(values, y, c=values, cmap=cmap, norm=norm, s=17, linewidth=0, zorder=3)
ax.set(yticks=y, yticklabels=labels, xlim=(.7, 1), xticks=[.7, .8, .9, 1.0],
       ylim=(len(y)-.35, -.65), title="Mouse" if mouse else "Human", xlabel="Mean Augur AUC")
ax.tick_params(axis="y", length=2, pad=2)
ax.tick_params(axis="x", length=2, pad=2)
legend = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap),
                      cax=fig.add_axes([.82, .33, .026, .36]), ticks=[.75, .85, .95])
legend.ax.tick_params(length=1.3, labelsize=4.7, pad=1)
legend.ax.set_title("AUC", fontsize=5.1, loc="left", pad=3)
legend.solids.set_rasterized(False)
