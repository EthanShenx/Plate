"""Simulated branched trajectory plus a pseudotime inset."""

from matplotlib.colors import LinearSegmentedColormap

rng = np.random.default_rng(305)
fig = figure()
design = (56, 47)
ax = plain(box(fig, design, 1.8, 0, 53.5, 44.5))
inset = plain(box(fig, design, 9, 2.9, 24.5, 19.6))
root = np.array([.58, .43])
branches = [
    (1, [(.58,.43),(.55,.62),(.62,.86),(.56,.98)]),
    (2, [(.58,.43),(.65,.39),(.75,.34),(.81,.37)]),
    (3, [(.79,.37),(.83,.30),(.87,.21),(.91,.15)]),
    (4, [(.79,.37),(.86,.38),(.89,.46),(.92,.43)]),
    (5, [(.58,.43),(.47,.31),(.18,.36),(.045,.29)]),
]
time_cmap = LinearSegmentedColormap.from_list("pseudotime", ["#142c47","#5aafe3"])
for state, nodes in branches:
    t = np.linspace(0, 1, 46)
    points = np.array(nodes)
    track = ((1-t)**3)[:,None]*points[0] + (3*t*(1-t)**2)[:,None]*points[1] + (
        3*t*t*(1-t))[:,None]*points[2] + (t**3)[:,None]*points[3]
    x, y = np.repeat(track, 15, axis=0).T + rng.normal(0, .009, (2, 690))
    ax.scatter(x, y, s=1.2, color=STATE_COLORS[state-1], alpha=.82, linewidths=0, rasterized=True)
    inset.scatter(x, y, s=.60, c=np.repeat(t if state != 1 else .36*(1-t), 15), cmap=time_cmap,
                  vmin=0, vmax=1, linewidths=0, rasterized=True)
ax.scatter(*root, s=10, color=DARK, zorder=3)
ax.set(xlim=(-.07, 1.01), ylim=(0, 1.06))
inset.set(xlim=(0, 1), ylim=(.08, 1.06))
bar = box(fig, design, 6, 4.4, 2, 13)
bar.imshow(np.linspace(1, 0, 100)[:,None], cmap=time_cmap, aspect="auto", extent=(0,1,0,40))
bar.spines[:].set_visible(False)
bar.set(xticks=[], yticks=[0,10,20,30,40])
bar.yaxis.tick_right()
bar.tick_params(axis="y", length=0, pad=1.5, labelsize=4.5)
bar.set_ylabel("Pseudotime", fontsize=5.1, labelpad=2)
for label, coords in [("MO0, MO2",(.68,.95)),("MO1",(.87,.51)),("MA1, MA2",(.68,.12)),
                      ("MA0, MA3, MA4",(.12,.18))]:
    ax.text(*coords, label, fontsize=5.4)
for tail, tip, curve in [((.52,.85),(.17,.35),-.38), ((.64,.86),(.9,.24),.22)]:
    ax.annotate("", tip, tail, arrowprops={"arrowstyle": "->", "color": DARK,
                                           "lw": 1.15, "connectionstyle": f"arc3,rad={curve}"})
ax.annotate("", (.16,.04), (-.024,.04), arrowprops={"arrowstyle": "->", "color": DARK, "lw": .8})
ax.annotate("", (-.024,.22), (-.024,.04), arrowprops={"arrowstyle": "->", "color": DARK, "lw": .8})
ax.text(.11, -.008, "Component 1", fontsize=5, ha="center")
ax.text(-.057, .143, "Component 2", fontsize=5, va="center", ha="right", rotation=90)
