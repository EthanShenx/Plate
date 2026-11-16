"""Simulated embedding and its separately editable subtype key."""

rng = np.random.default_rng(303)
fig = figure()
if PART == "key":
    descriptions = ["Microglia", "APOE+ MA", "FOLR2+ MA", "CD5L+ MA", "CD163+ MA", "LYVE1+ MA",
                    "Classical MO", "Intermediate MO", "Nonclassical MO", "cDC1", "cDC2",
                    "RUNX1+ mDC", "RUNX2+ mDC", "pDC"]
    entries = [(f"{key} · {description}", color) for key, description, color
               in zip(SUBTYPES, descriptions, SUBTYPE_COLORS, strict=True)]
    swatches(box(fig, (27, 40), .3, 1.1, 26.6, 38), entries, "Cell subtypes (n = 14)")
else:
    ax = plain(box(fig, (44, 37), .8, 0, 42.5, 34.7))
    centers = np.array([(1.2,-2.1), (2.25,2.1), (3.3,.05), (1.18,-.36), (-.43,-1.38),
                        (-2.49,-.05), (-2.25,1.85), (.72,1.71), (-.7,1.98),
                        (-2.48,-1.12), (1.64,-1.06), (-.77,-.02), (1.29,3.55), (4.11,-1.6)])
    params = [(.97,.37,27,4800), (.31,.45,-10,1200), (.61,.99,15,3900), (.23,.32,35,1000),
              (.49,.27,15,1350), (.34,.24,8,850), (.61,.4,70,1800), (.27,.84,53,2000),
              (.36,.36,15,960), (.42,.5,-15,1000), (.13,.16,0,260), (.54,.28,18,1100),
              (.27,.17,-20,720), (.1,.11,20,160)]
    for i, ((x, y), (sx, sy, angle, n)) in enumerate(zip(centers, params, strict=True)):
        theta = np.deg2rad(angle)
        basis = np.array([[np.cos(theta), np.sin(theta)], [-np.sin(theta), np.cos(theta)]])
        polar = rng.uniform(0, 2*np.pi, n)
        radius = np.sqrt(rng.uniform(0, 1, n)) * (1 + .16 * np.sin(3 * polar))
        points = np.c_[sx * np.cos(polar), sy * np.sin(polar)] * radius[:, None] @ basis
        points += rng.normal(0, .055, points.shape)
        ax.scatter(points[:, 0]*2 + x, points[:, 1]*2 + y, s=.31, color=SUBTYPE_COLORS[i],
                   linewidths=0, alpha=.77, rasterized=True)
        ax.text(x, y, str(i+1), ha="center", va="center", color="white", fontsize=4.8, weight="bold")
    ax.set(xlim=(-3.65, 4.6), ylim=(-3.35, 4.06))
    ax.annotate("", (-1.7,-3), (-3.4,-3), arrowprops={"arrowstyle": "->", "color": DARK})
    ax.annotate("", (-3.4,-1.85), (-3.4,-3), arrowprops={"arrowstyle": "->", "color": DARK})
    ax.text(-2.61,-3.3, "tSNE 1", ha="center", fontsize=5)
    ax.text(-3.53,-2.45, "tSNE 2", rotation=90, va="center", ha="right", fontsize=5)
