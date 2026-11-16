"""Tissue counts, simulated cell-type composition and Shannon entropy."""

rng = np.random.default_rng(301)
tissues = ("Mammary gland|Liver|PBMC|Cecum|Spleen|Jejunum|Duodenum|Colon|Lung|Ileum|"
           "Mammary cistern|Mammary duct|Mammary parenchyma|Pituitary gland|Rectum|Rumen|"
           "Blood|Thymus|Reticulum|Omasum|Uterine horn|Rumen papilla|Heart|Cervical lymph node|"
           "Thyroid|Adrenal gland|Bone marrow|Medulla oblongata|Abomasum|Blood vessel|Ovary|"
           "Epididymis|Cerebral cortex|Salivary gland|Hypothalamus|Testis|Pancreas|Rumen muscle|"
           "Oviduct|Skin|Kidney|Frontal lobe|Tongue|Esophagus|Parietal lobe|Bile duct|"
           "Occipital lobe|Cerebellum|Vagina|Trachea|Placenta|Intervertebral disc").split("|")
cell_types = ("Double-negative T cells|T cells|CD4+ T cells|CD8+ T cells|Cytotoxic CD8+ T cells|"
              "γδ T cells|Proliferative T cells|NK T cells|NK cells|Classical monocytes|"
              "Intermediate monocytes|Nonclassical monocytes|Macrophages|Microglia|Kupffer cells|"
              "Dendritic cells|Plasmacytoid DCs|B cells|Plasma cells|Neutrophils|"
              "Mast cells|Erythroid cells|Other immune cells").split("|")
palette = ["#d5c6c7", "#eac8ce", "#edb7ca", "#c67ab1", "#a7497c", "#803955",
           "#665392", "#8199bc", "#83c9d4", "#67b9ad", "#4a9c9e", "#33859b",
           "#74b4a3", "#86c386", "#609d62", "#7a823a", "#b9bb74", "#f4e58d",
           "#efd179", "#d4aa59", "#e0a440", "#edac37", "#efc81f"]
n = len(tissues)
counts = np.sort(np.rint(93000 * np.exp(-np.linspace(0, 5.65, n)) *
                         rng.lognormal(0, .17, n)).astype(int))[::-1]
concentration = .009 + 2.6 * np.exp(-np.linspace(0, 7.5, n))
composition = np.stack([rng.dirichlet(value * np.linspace(1.2, .8, len(cell_types)))
                        for value in concentration])
entropy = -np.sum(composition * np.log(composition + 1e-14), axis=1)
fig = figure()
ax = box(fig, (68, 114), 3, 7.2, 45.5, 100.4)
y = np.arange(n)
left = np.zeros(n)
for share, color in zip(composition.T, palette, strict=True):
    values = counts * share
    ax.barh(y, values, height=.89, left=left, color=color, edgecolor="white", linewidth=.18)
    left += values
ax.set(xlim=(max(105000, counts[0] + 5000), 0), ylim=(n - .48, -.6), yticks=y, yticklabels=tissues, xlabel="Cell number",
       xticks=[100000, 75000, 50000, 25000, 0], xticklabels=["100,000", "75,000", "50,000", "25,000", "0"])
ax.yaxis.tick_right()
ax.tick_params(axis="y", length=1.1, pad=1.4, labelsize=4.7)
ax.spines["left"].set_visible(False)
ax.spines["right"].set_visible(True)
top = ax.twiny()
top.set(xlim=(3.35, 0), xlabel="Shannon entropy (nats)", xticks=[3, 2, 1, 0])
top.spines[["left", "bottom"]].set_visible(False)
top.spines["top"].set_visible(True)
top.plot(entropy, y, color="#a4a6a7", linewidth=.6, zorder=1)
top.scatter(entropy, y, s=3, color="#252525", linewidths=0, zorder=2)
for row, count in enumerate(counts):
    ax.text(count + 1300, row, f"{count:,}", ha="right", va="center", fontsize=4.25)
swatches(box(fig, (68, 114), 3.5, 40.2, 25, 65.5), list(zip(cell_types, palette, strict=True)), "Cell types", font=5.2)
