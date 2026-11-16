import matplotlib.pyplot as plt
from matplotlib.patches import Circle

fig = plt.figure()
ax = fig.add_axes([.04, .06, .91, .92])
ax.set(xlim=(0, 5.6), ylim=(-.05, 3.15), aspect="equal")
ax.set_axis_off()
mouse, human, shared = 485, 810, 28  # Illustrative counts
ax.add_patch(Circle((1.71, 1.63), 1.22, fc="#ed8b86", ec="#292e36", lw=.55))
ax.add_patch(Circle((4.02, 1.63), 1.43, fc="#43516e", ec="#292e36", lw=.55, alpha=.96))
for x, label, number in [(1.55, "Mouse-specific\nDEGs", mouse), (4.04, "Human-specific\nDEGs", human)]:
    ax.text(x, 1.90, label, ha="center", va="center", color="white", fontsize=5.6)
    ax.text(x, 1.35, str(number), ha="center", color="white", fontsize=7)
ax.annotate(f"Shared {shared}", xy=(2.71, .92), xytext=(2.71, .08), ha="center",
            fontsize=5.2, arrowprops={"arrowstyle": "-", "lw": .45, "color": "#292e36"})
