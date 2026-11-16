import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

rng = np.random.default_rng(123)
groups = {
    "Mouse-specific": "Tfap2c Tbx21 Hif1a E2f2 Nfya Cebpe".split(),
    "Human-specific": "STAT1 SOX2 FOXP1 RUNX1 TP53 SMAD1".split(),
    "Discordant": "SPI1 MYC ETS1 NFKB1 SPIB MAFF".split(),
    "Shared same direction": "GATA3 E2F1 GATA2 EGR1 FOS MITF".split(),
}
fig = plt.figure()
ax = fig.add_axes([.23,.13,.74,.74])
blue, coral = "#43516e", "#e98783"
values, row = [], 0
for index,(title, genes) in enumerate(groups.items()):
    ax.text(-.033,row-.55,title,fontsize=4.5,color=[coral,blue,"#934b79","#226884"][index])
    row += .6
    for gene in genes:
        human,mouse = rng.uniform(.004,.031,2) * rng.choice([-1,1])
        if index == 0:
            human = np.nan
        elif index == 1:
            mouse = np.nan
        elif index == 2:
            mouse = -mouse
        if gene in {"GATA3","E2F1"}:
            sign = -1 if gene=="GATA3" else 1
            human,mouse = sign*.017,sign*.026
        if np.isfinite(human+mouse):
            ax.plot([human,mouse],[row,row],color="#abb6c7",lw=.62,zorder=1)
        ax.scatter([human,mouse],[row,row],c=[blue,coral],s=10,lw=0,zorder=2)
        values.append((row,gene))
        row += 1
    row += .6
ax.set(yticks=[y for y,_ in values],yticklabels=[x for _,x in values], xlim=(-.036,.052),
       ylim=(row-.25,-1.1), xticks=[-.02,0,.02,.04], xlabel="Mean difference")
fig.text(.58,.95,"Top TFs by GRN class",ha="center",fontsize=5.8)
ax.axvline(0,lw=.48,color="#555a64",ls="--")
ax.tick_params(axis="both",pad=1,length=1.4,labelsize=4.25)
ax.xaxis.labelpad = 1.8
fig.legend(handles=[Line2D([],[],color=c,marker="o",ms=2.8,lw=0,label=l)
                    for c,l in [(blue,"Human"),(coral,"Mouse")]],
           loc="lower right",bbox_to_anchor=(.98,.87),frameon=False,ncol=2,
           borderaxespad=0,handlelength=.8,columnspacing=.8,fontsize=4.6)
