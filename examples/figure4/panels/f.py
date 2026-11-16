import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np

genes = ["CPA3/Cpa3", "CTSG/Ctsg", "IL1RL1/Il1rl1", "TPSB2/Tpsb2",
         "IGHA1/Igha", "CXCL14/Cxcl14", "MNDA/Ifi202b", "IL20RA/Il20ra"]
rng = np.random.default_rng(61)
human = np.array([-8, -9, -7, -6, -3, .9, .6, np.nan]) + rng.normal(0, .3, len(genes))
mouse = np.array([2.8, 1.4, 1.0, 2.7, -1.6, -2.5, -2, -1.6]) + rng.normal(0, .3, len(genes))
blue, coral = "#43516e", "#ef8a85"
fig = plt.figure()
fig.text(.52, .953, "Species-differential gene comparison", ha="center")
ax = fig.add_axes([.28, .13, .26, .73])
delta = fig.add_axes([.57, .13, .15, .73], sharey=ax)
y = np.arange(len(genes))
ax.barh(y+.17, human, height=.32, color=blue)
ax.barh(y-.17, mouse, height=.32, color=coral)
ax.axvline(0, color="#30323a", lw=.5)
ax.set(yticks=y, yticklabels=genes, ylim=(len(y)-.45, -.55), xlim=(-11, 6), xticks=[-10, -5, 0, 5])
ax.set_xlabel("log2 FC", labelpad=2)
ax.tick_params(length=2, pad=1.5, labelsize=4.7)
diff = abs(human - mouse)
delta.barh(y, diff, height=.68, color=np.where(human*mouse < 0, "#f6a21c", "#969ca0"))
delta.plot([.85], [7], marker="x", ms=4, color="#b52e37", lw=0)
delta.set(xlim=(0, 14), xticks=[0, 7, 14], xlabel="Δ FC")
delta.xaxis.labelpad = 2
delta.tick_params(axis="both", length=2, pad=1.5, labelsize=4.5)
delta.tick_params(axis="y", left=False, labelleft=False)
for panel in [ax, delta]:
    for side in panel.spines.values():
        side.set_visible(True)
    panel.axhline(4.5, color="#aeb4bc", lw=.45)
fig.legend(handles=[Patch(fc=blue, label="Human"), Patch(fc=coral, label="Mouse")],
           title="Species", frameon=False, loc="upper left", bbox_to_anchor=(.74,.70),
           borderaxespad=0, handlelength=1, fontsize=4.5)
fig.legend(handles=[Patch(fc="#f6a21c", label="Opposite"), Patch(fc="#969ca0", label="Same"),
                    Line2D([],[],color="#b52e37",marker="x",lw=0,label="Missing")],
           title="Direction", frameon=False, loc="upper left", bbox_to_anchor=(.74,.48),
           borderaxespad=0, handlelength=1, fontsize=4.5)
