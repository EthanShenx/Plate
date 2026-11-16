import matplotlib.pyplot as plt
from matplotlib.patches import Patch

fig = plt.figure()
fig.text(.09, .81, "Immune TF classification", fontsize=5.5)
ax = fig.add_axes([.09,.045,.29,.75])
labels = ["Shared same direction", "Human-specific", "Mouse-specific", "Discordant"]
counts = [39, 96, 37, 31]
colors = ["#679b56", "#b34448", "#346748", "#77848c"]
ax.pie(counts, colors=colors, startangle=90, wedgeprops={"edgecolor":"white","linewidth":.55},
       autopct=lambda pct: str(round(pct*sum(counts)/100)), pctdistance=.7,
       textprops={"color":"white","fontsize":5})
fig.legend(handles=[Patch(fc=c,label=l) for c,l in zip(colors,labels,strict=True)],
           fontsize=4.8, frameon=False, loc="center left", bbox_to_anchor=(.34,.47),
           ncol=2, handlelength=1, columnspacing=.8, borderaxespad=0)
