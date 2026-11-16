"""Illustrative transcription-factor activity with cell-specific enrichment."""

rng = np.random.default_rng(304)
genes = ("ARID3A CEBPD FOS RFX1 SPI1 ATF4 TAL1 ZBTB7A RXRA RUNX3 IRF7 PRDM1 YBX1 ISL1 "
         "PITX1 HOXB8 IRF4 JUNB ETS2 FOSB ETV3 JUN JUND STAT3 YY1 PPARG CREB1 NFE2L2 "
         "MYC CREB3 IRF3 ZEB1 NFIA KLF12 EP300 IRF8 BHLHE41 SREBF2 SMAD4").split()
order = ["MO0", "MO1", "MO2", "MA1", "MA2", "MA5", "MA3", "MA4", "MA0"]
sizes = [4, 3, 4, 3, 3, 8, 5, 4, 5]
scores = rng.normal(-.28, .54, (sum(sizes), len(order)))
for i, (start,end) in enumerate(zip(np.r_[0, np.cumsum(sizes)[:-1]], np.cumsum(sizes))):
    scores[start:end, i] += rng.uniform(1.3, 2.65, end-start)
    if i:
        scores[start:end, i-1] += rng.uniform(0, .71, end-start)
fig = figure()
ax = box(fig, (64, 78), 2.6, .5, 42.7, 68)
image = ax.imshow(scores, aspect="auto", cmap=DIVERGING, vmin=-2.3, vmax=2.3, interpolation="nearest")
ax.set(xticks=range(len(order)), xticklabels=order, yticks=range(len(genes)), yticklabels=genes)
ax.yaxis.tick_right()
ax.tick_params(axis="both", length=0, pad=1.3)
ax.tick_params(axis="y", labelsize=4.15)
plt.setp(ax.get_xticklabels(), ha="right", rotation=50, fontsize=5)
ax.spines[:].set_visible(False)
colorbar = fig.colorbar(image, cax=box(fig, (64, 78), 56, 23.5, 2.25, 16), ticks=[-2,-1,0,1,2])
colorbar.outline.set_visible(False)
colorbar.ax.tick_params(length=1.1, pad=1)
colorbar.ax.set_title("z-score", fontsize=5.2, loc="left")
