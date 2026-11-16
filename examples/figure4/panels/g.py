import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

rng = np.random.default_rng(74 + (0 if PART == "legend" else PART))
labels = ["Immune", "Keratinocyte", "Fibroblast", "Melanocyte", "Schwann cell",
          "Vascular endothelium", "Lymphatic endothelium", "Smooth muscle",
          "Sebaceous gland", "Hair-follicle stem cells"]
colors = ["#9a4e90", "#dd810a", "#24843e", "#9979ad", "#a35c33",
          "#486aa6", "#c74b84", "#188d94", "#659f34", "#bf5051"]
fig = plt.figure()
if PART == "legend":
    fig.legend(handles=[Line2D([], [], lw=0, marker="o", ms=np.sqrt(3+count/90),
                               color="#414955", label=str(count)) for count in (200, 600, 1200)],
               title="Count", ncol=3, loc="center", frameon=False, fontsize=4.2,
               title_fontsize=4.3, handlelength=.65, handletextpad=.35, columnspacing=.8)
else:
    title, x_limit, y_limit = [
        ("Human - healthy", 8, 5.5), ("Human - psoriasis", 11, 5.5),
        ("Mouse - healthy", 16, 9), ("Mouse - IMQ", 27, 17),
    ][PART]
    ax = fig.add_axes([.19, .20, .78, .68])
    # A stratified point layout provides enough separation to exercise the label rendering.
    positions = np.array([[.16,.64],[.24,.90],[.76,.445],[.58,.79],[.47,.28],
                          [.55,.52],[.18,.20],[.82,.71],[.82,.12],[.21,.39]])
    positions += rng.uniform(-.014,.014,positions.shape)
    if "healthy" not in title:
        positions[0,0] += .12
    counts = rng.integers(50, 1200 if "Mouse" in title else 600, len(labels))
    for (x,y), label, color, count in zip(positions, labels, colors, counts, strict=True):
        ax.scatter(x*x_limit, y*y_limit, color=color, s=3 + count/90, lw=0)
        ax.annotate(label, (x*x_limit, y*y_limit), xytext=(-2 if x>.5 else 3, 2),
                    textcoords="offset points", ha="right" if x>.5 else "left",
                    color=color, fontsize=4, fontweight="bold" if label=="Immune" else "normal")
    ax.set(title=title, xlim=(0,x_limit), ylim=(0,y_limit),
           xlabel="Outgoing interaction strength", ylabel="Incoming interaction strength")
    ax.xaxis.labelpad = 2
    ax.yaxis.labelpad = 2
    ax.tick_params(length=2, pad=1.4, labelsize=4.6)
