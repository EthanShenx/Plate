"""Clustered trajectories and illustrative enrichment terms in separate layers."""

from matplotlib.patches import Polygon

rng = np.random.default_rng(307)
fig = figure()
cluster_rows = np.array([0, .153, .543, .753, 1])
table_edges = np.array([.045, .36, .552, .759, .995])
table_design, table_axes = (59, 68), (.45, .4, 58.3, 67.2)
heat_design, heat_axes = (60, 96), (6.6, 5, 51.4, 82)

if PART == "table":
    ax = plain(box(fig, table_design, *table_axes))
    ax.set(xlim=(0, 1), ylim=(1, 0))
    ax.hlines([0, .045, *table_edges[1:]], 0, 1, color="#222222", lw=.62)
    ax.text(.22, .023, "GO terms", ha="center", va="center", fontsize=5.7)
    ax.text(.88, .023, "P", ha="center", va="center", style="italic", fontsize=5.7)
    terms = [
        ("Nervous system development", "Cellular component morphogenesis",
         "Modulation of synaptic transmission", "Chloride transmembrane transport",
         "Regulation of neurotransmitter secretion"),
        ("Protein modification by small proteins", "Double-strand break repair"),
        ("Peptide metabolic process", "Cellular macromolecule biosynthesis",
         "Proton transmembrane transport"),
        ("Regulation of protein modification", "Nitrogen compound transport",
         "Intracellular signal transduction", "Positive regulation of autophagy"),
    ]
    for i, (top, bottom, cluster, names) in enumerate(zip(table_edges[:-1], table_edges[1:],
                                                          (1, 2, 4, 3), terms)):
        header = top + .041
        ax.text(.021, header*.5 + top*.5, f"Cluster {cluster}", color=CLUSTER_COLORS[i],
                va="center", fontsize=5.65)
        ax.hlines(header, 0, 1, color="#222222", lw=.45)
        ys = np.linspace(header, bottom, len(names)+1)
        pvalues = np.sort(10**-rng.uniform(4, [6.2, 9.1, 22.5, 6.0][i], len(names)))
        for y, name, pval in zip((ys[:-1]+ys[1:])/2, names, pvalues):
            ax.text(.021, y, name, va="center", fontsize=5.25)
            ax.text(.98, y, f"{pval:.2e}", va="center", ha="right", fontsize=5.05)
elif PART == "ribbons":
    ax = plain(fig.add_axes([0, 0, 1, 1]))
    width, height = plate.size_mm
    ax.set(xlim=(0, width), ylim=(height, 0))
    panels = plate.context.get("panel_boxes_mm", {})
    if "g" in panels and "g-table" in panels:
        table, heatmap = panels["g-table"], panels["g"]
        tx, ty, tw, th = table_axes
        hx, hy, _, hh = heat_axes
        left = table["x"] + (tx + tw) * table["w"] / table_design[0]
        right = heatmap["x"] + hx * heatmap["w"] / heat_design[0]
        left_rows = table["y"] + (ty + th * table_edges) * table["h"] / table_design[1]
        right_rows = heatmap["y"] + (hy + hh * cluster_rows) * heatmap["h"] / heat_design[1]
        for i, color in enumerate(CLUSTER_COLORS):
            y0, y1 = left_rows[i:i+2]
            z0, z1 = right_rows[i:i+2]
            ax.add_patch(Polygon([(left,y0), (right,z0), (right,z1-.6), (left,y1-.6)],
                                 closed=True, facecolor=color, alpha=.20, edgecolor="none"))
else:
    design = heat_design
    ax = plain(box(fig, design, *heat_axes))
    nrows, ncols = 360, 146
    u = np.linspace(0, 1, ncols)
    expression = np.zeros((nrows, ncols))
    splits = np.round(nrows * cluster_rows).astype(int)
    for i, (start,end) in enumerate(zip(splits[:-1], splits[1:])):
        n = end-start
        peak = [.87, .97, .27, .11][i]
        center = rng.normal(peak, [.075,.045,.12,.10][i], (n,1))
        width = rng.uniform(.045, .21, (n,1))
        gaussian = np.exp(-.5 * ((u-center)/width)**2)
        smooth = np.stack([np.interp(u, np.linspace(0,1,12), values)
                           for values in rng.normal(0, .44, (n,12))])
        trend = (+1 if i < 2 else -1) * (u - .5)
        expression[start:end] = ((1.2+rng.random((n,1))) * gaussian + trend + smooth +
                                 rng.normal(0,.055,(n,ncols)) - .55)
    expression = (expression - expression.mean(axis=1, keepdims=True)) / expression.std(axis=1, keepdims=True)
    image = ax.imshow(expression, aspect="auto", extent=(0,1,1,0), cmap=DIVERGING, vmin=-3, vmax=3,
                      interpolation="nearest")
    ax.vlines(.5, 0, 1, colors="white", linewidth=1.15)
    ax.hlines(cluster_rows[1:-1], 0, 1, color="white", linewidth=1.4)
    track = plain(box(fig, design, 6.6, 3.4, 51.4, 1.15))
    for x0,x1,color in [(0,.175,"#e8536a"),(.175,.825,"#a3a4a6"),(.825,1,"#8196c4")]:
        track.axvspan(x0,x1, color=color, linewidth=0)
    track.set(xlim=(0,1), ylim=(0,1))
    key = plain(box(fig, design, 6.6, 0, 51.4, 3))
    key.set(xlim=(0,1), ylim=(0,1))
    key.annotate("", (.96,.27), (.08,.27), arrowprops={"arrowstyle": "<->","color":DARK,"lw":.8})
    key.vlines(.5,.11,.41,color=DARK,lw=.8)
    for x,text in [(.09,"States 2–4"),(.5,"State 1"),(.92,"State 5")]:
        key.text(x,.62,text,ha="center",va="bottom",fontsize=5.5)
    dendrogram = plain(box(fig, design, 2.1, 5, 4.45, 82))
    dendrogram.set(xlim=(0,1.1), ylim=(1,0))
    centers = (cluster_rows[:-1]+cluster_rows[1:])/2
    for i, (y0,y1) in enumerate(zip(cluster_rows[:-1],cluster_rows[1:])):
        dendrogram.vlines(1.02,y0+.004,y1-.004,color=CLUSTER_COLORS[i],linewidth=2.3)
        levels = np.linspace(y0+.009,y1-.009,17)
        root = .58+i*.05
        dendrogram.hlines(levels, rng.uniform(root,.89,len(levels)), .94, color="#363438", lw=.25)
        dendrogram.plot([.24,root,root,.94], [centers[i],centers[i],levels[-1],levels[-1]],
                        color="#27252a", linewidth=.42)
    dendrogram.vlines(.24,centers[0],centers[-1],color="#27252a",lw=.48)
    cbar = fig.colorbar(image, cax=box(fig,design,20,90.4,28,1.9), orientation="horizontal",
                        ticks=[-3,-2,-1,0,1,2,3])
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(length=0,pad=1)
    cbar.set_label("Relative expression level", fontsize=5.05,labelpad=1.1)
