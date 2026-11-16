"""Clustered synthetic correlation heatmap with an open lower triangle."""

from matplotlib.colors import ListedColormap
from matplotlib.patches import Polygon

rng = np.random.default_rng(302)
groups = ["T / NK cells", "Myeloid cells", "Mast cells", "Erythroid cells",
          "Plasma cells", "Brain microglia", "Neutrophils"]
counts = [109, 55, 30, 20, 16, 15, 15]
ends = np.r_[0, np.cumsum(counts)]
n = ends[-1]
systems = ["Digestive", "Endocrine", "Cardiovascular", "Lymphatic", "Female reproductive",
           "Respiratory", "Male reproductive", "Nervous", "Urinary", "Skeletal", "Integumentary"]
system_colors = ["#eb6667", "#f5925a", "#b5ab62", "#73c5a7", "#acb8c9",
                 "#a9bf88", "#92d359", "#6fd9df", "#4e78b4", "#624b86", "#926869"]
group_colors = ["#78cbd8", "#c7c363", "#d7c6a7", "#b7c645", "#798fa9", "#6da5a3", "#e79737"]
group_id = np.repeat(np.arange(len(groups)), counts)
# Correlations come from synthetic expression profiles sharing correlated factors.
shared = rng.normal(size=(7, 100))
shared[:2] = .45 * shared[2] + .89 * shared[:2]
expression = (shared[group_id] * rng.uniform(.55, 1.2, (n, 1)) +
              .65 * rng.normal(size=(n, 100)) + .32 * rng.normal(size=(1, 100)))
correlation = np.corrcoef(expression)
fig = figure()
design = (110, 105)
heat = box(fig, design, 17, 12, 92, 92)
image = heat.imshow(correlation, extent=(0, n, n, 0), aspect="auto", cmap="YlOrRd",
                    vmin=0, vmax=1, interpolation="nearest")
triangle = Polygon([(0, 0), (n, 0), (n, n)], closed=True, edgecolor="#282324",
                   linewidth=.55, facecolor="none")
heat.add_patch(triangle)
image.set_clip_path(triangle)
for start, end in zip(ends[:-1], ends[1:], strict=True):
    heat.plot([start, end, end], [start, start, end], color="#342725", linewidth=.45)
for index in (0, 1):
    start, end = ends[index:index+2]
    heat.text((start + end) / 2, start + 15, groups[index], ha="center", va="center", fontsize=6)
for index, dy in [(2, -11), (3, -10), (4, -12), (5, 8), (6, 10)]:
    start, end = ends[index:index+2]
    heat.annotate(groups[index], (start + 3, start + 2), (min(n - 5, end + 12), start + dy),
                  ha="right", va="center", fontsize=5.1,
                  arrowprops={"arrowstyle": "->", "color": DARK, "lw": .55})
heat.set(xlim=(0, n), ylim=(n, 0))
plain(heat)

tree = plain(box(fig, design, 17, .4, 92, 7.7))
tree.set(xlim=(0, n), ylim=(-.02, 1.5))

def dendrogram(leaves, base, interval):
    """Average-linkage tree over the supplied correlation distances."""
    clusters = [[(leaf,), leaf + .5, base] for leaf in leaves]
    while len(clusters) > 1:
        # Use adjacent clusters to keep the simulated lineage strip contiguous.
        distance = [1 - correlation[np.ix_(left[0], right[0])].mean()
                    for left, right in zip(clusters, clusters[1:])]
        i = int(np.argmin(distance))
        left, right = clusters[i:i+2]
        level = max(left[2], right[2]) + interval * (.55 + distance[i])
        tree.plot([left[1], left[1], right[1], right[1]], [left[2], level, level, right[2]],
                  color="#242222", linewidth=.24)
        clusters[i:i+2] = [[left[0]+right[0], (left[1]+right[1])/2, level]]
    return clusters[0]

roots = [dendrogram(range(start, end), 0, .024) for start, end in zip(ends[:-1], ends[1:])]
for (left, right), level in zip(zip(roots, roots[1:]), np.linspace(.87, 1.33, len(roots)-1)):
    tree.plot([left[1], left[1], right[1], right[1]], [left[2], level, level, right[2]],
              color="#242222", linewidth=.32)
for row, (track, colors, title) in enumerate([
        (rng.integers(len(systems), size=n), system_colors, "Tissue systems"),
        (group_id, group_colors, "Cell lineages")]):
    track_ax = plain(box(fig, design, 17, 8.35 + row * 1.74, 92, 1.55))
    track_ax.imshow([track], cmap=ListedColormap(colors), vmin=0, vmax=len(colors)-1,
                    interpolation="nearest", aspect="auto")
    track_ax.text(-.012, .5, title, transform=track_ax.transAxes, va="center", ha="right", fontsize=5.2)
swatches(box(fig, design, .5, 14.4, 26, 29.3), list(zip(systems, system_colors)), "Tissue systems")
swatches(box(fig, design, .5, 45.1, 24, 21.2), list(zip(groups, group_colors)), "Cell lineages")
color_ax = box(fig, design, 28, 44.2, 1.6, 17.2)
colorbar = fig.colorbar(image, cax=color_ax, ticks=[0, .25, .5, .75, 1])
colorbar.outline.set_visible(False)
colorbar.ax.tick_params(length=1, pad=1)
colorbar.set_label("Pearson correlation", fontsize=5.2)
