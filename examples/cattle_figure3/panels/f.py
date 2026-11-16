"""Normalized state proportions from synthetic multinomial cell counts."""

rng = np.random.default_rng(306)
probs = np.array([[0,0,0,0,1], [0,.04,.85,0,.11], [0,0,.84,0,.16], [0,.105,.02,0,.875],
                  [0,0,0,0,1], [.17,.37,.22,.10,.14], [.82,.025,0,.155,0],
                  [.20,.025,.125,.65,0], [.87,.02,0,.11,0]])
counts = np.stack([rng.multinomial(int(n), p) for n,p in zip(rng.integers(250,1000,9), probs)])
shares = counts / counts.sum(axis=1, keepdims=True)
fig = figure()
ax = box(fig, (54, 37), 5.8, 3.7, 46.1, 29.45)
order = [4,3,0,1,2]
# Each category uses the same project-level colors as the trajectory and legend.
left = np.zeros(len(shares))
for state in order:
    ax.barh(np.arange(len(shares)), shares[:,state], left=left, color=STATE_COLORS[state],
            edgecolor="white", linewidth=.7, height=.81)
    left += shares[:,state]
ax.set(xlim=(0,1), ylim=(len(shares)-.52,-.48), yticks=range(len(shares)), yticklabels=MYELOID,
       xticks=[0,.25,.5,.75,1], xticklabels=["0","0.25","0.5","0.75","1"],
       title="Proportion of states")
ax.tick_params(axis="y", length=1.4, pad=1.1)
ax.spines[:].set_visible(True)
