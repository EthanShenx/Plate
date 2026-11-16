import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch
import numpy as np
import plate

rng = np.random.default_rng(111 + (0 if PART == "legend" else PART))
mouse, human, target = "#e98783", "#43516e", "#e4b556"
up, down = (plate.colors[key] for key in ("Up", "Down"))
fig = plt.figure()


def edge_width(score):
    return .2 + .23 * score


def points(degrees):
    radians = np.deg2rad(degrees)
    return np.c_[np.cos(radians), np.sin(radians)]


if PART == "legend":
    fig.legend(handles=[Line2D([],[],lw=.9,color=up,label="Up"),
                        Line2D([],[],lw=.9,color=down,label="Down"),
                        Line2D([],[],lw=edge_width(-np.log10(.05)),color="#686d77",label="p = 0.05"),
                        Line2D([],[],lw=edge_width(3),color="#686d77",label="p = 0.001")],
               title="Differential edges",loc="center",
               frameon=False,handlelength=1.25,fontsize=4.5)
else:
    title, regulators, targets, color, count = [
        ("Mouse-specific psoriasis GRN",
         "E2F1 SPI1 EGR1 Tfap2c MYC ETS1 GATA3 ESR1 CEBPA".split(),
         "APOE TSPAN5 Stk17b ADH5 PLK2 FOSB S100A4 Wnt7b CD55 FOXP2".split(), mouse, 2710),
        ("Human-specific psoriasis GRN",
         "POU2F3 MYC PURA GATA2 SPI1 ETS1 STAT1 EGR1 GATA3".split(),
         "SPRR2A AR ADH5 SLC7A5 RUNX2 DNAJB6 GALM DENND4A EDEM1 APPL2".split(), human, 5160),
    ][PART]
    ax = fig.add_axes([.04,.044,.92,.81])
    ax.set(xlim=(-1.48,1.48),ylim=(-1.14,1.24),aspect="equal")
    ax.set_axis_off()
    ax.set_title(f"{title}\nN = {count}",fontsize=5.4,pad=2)
    angles = np.linspace(112,248,len(regulators))
    ends = np.linspace(68,-68,len(targets))
    left, right = points(angles), points(ends)
    for start in left:
        for k in rng.choice(len(targets), size=3, replace=False):
            stop = right[k]
            arrow = FancyArrowPatch(start,stop,connectionstyle=f"arc3,rad={rng.uniform(-.22,.22):.3f}",
                                    arrowstyle="-|>",mutation_scale=3.3,shrinkA=2.4,shrinkB=2.4,
                                    color=up if rng.random()>.45 else down,lw=edge_width(rng.uniform(1.3,3.5)),
                                    alpha=.8,zorder=1)
            ax.add_patch(arrow)
    for coords, names, tone, align in [(left,regulators,color,"right"),(right,targets,target,"left")]:
        ax.scatter(*coords.T,c=tone,s=19,ec="white",lw=.35,zorder=2)
        for (x,y), label in zip(coords,names,strict=True):
            ax.text(x*1.13,y*1.10,label,ha=align,va="center",fontsize=4.25,fontstyle="italic")
