"""Four synthetic marker trajectories, with expression on logarithmic axes."""

rng = np.random.default_rng(308)
fig = figure()
design = (56, 99)
genes = ["CALCR", "CX3CR1", "GPC5", "P2RY12"]
for i, gene in enumerate(genes):
    ax = box(fig, design, 8.2, 3 + 23.2*i, 37.1, 18.6)
    for k, color in enumerate(SUBTYPE_COLORS[:9]):
        center = [96, 52, 68, 78, 81, 48, 15, 27, 25][k]
        x = np.clip(rng.normal(center, [2,8,13,10,9,15,10,12,10][k], 146), 0, 100)
        trend = [
            .56 + 16.5 * (x/100)**9,
            .62 + 5.8 * (x/100)**1.8,
            .54 + 3.7 * (x/100)**7,
            .63 + 9 * (x/100)**5,
        ][i]
        boost = 1 if k == 0 else ([1.6,2.8,1.1,2][i] if k == 1 else .50)
        y = np.maximum(.48, np.round(rng.lognormal(np.log(trend * boost), 1.12) * 1.9)/2)
        zeros = [.42,.22,.43,.30][i] - .07*(k == 0)
        y[rng.random(len(y)) < zeros] = .48
        ax.scatter(x, y, s=2.35, color=color, alpha=.80, linewidths=0, rasterized=True)
    x = np.linspace(0, 100, 120)
    fit = [.48 + 13.2*(x/100)**9, .55 + 4.55*(x/100)**1.8,
           .48 + 3.1*(x/100)**7, .52 + 6.3*(x/100)**5][i]
    ax.plot(x, fit, linestyle=(0,(2.1,2)), lw=.68, color="#262526")
    ax.plot(x[:46], .48 + .09*x[:46]/100, lw=.55, color="#262526")
    ax.set(xlim=(-5,104), yscale="log", ylim=(.4,220 if i!=2 else 80),
           yticks=[1,10,100] if i!=2 else [1,3,10,30],
           yticklabels=["1","10","100"] if i!=2 else ["1","3","10","30"])
    ax.minorticks_off()
    ax.tick_params(length=1.8,pad=1.1)
    ax.text(.51,.98,gene,transform=ax.transAxes, ha="center",va="top",style="italic",fontsize=5.7)
    if i != 3:
        ax.spines["bottom"].set_visible(False)
        ax.set_xticks([])
    else:
        ax.set(xticks=[0,25,50,75,100], xlabel="Pseudotime")
fig.text(.041,.52,"Expression",rotation=90,ha="center",va="center",fontsize=5.5)
legend = plain(box(fig,design,46.7,41.5,9,31))
legend.set(xlim=(0,1),ylim=(9.6,-1))
for y,(name,color) in enumerate(zip(MYELOID,SUBTYPE_COLORS)):
    legend.scatter(.12,y,s=12,color=color,linewidths=0)
    legend.text(.26,y,name,fontsize=4.9,va="center")
legend.text(.11,-.81,"Subtype",fontsize=4.6,ha="left",va="center")
line_key=plain(box(fig,design,47.7,28,7.8,10.6))
line_key.set(xlim=(0,1),ylim=(0,1))
for x,label,style in [(.12,"States 2–4","-"),(.60,"State 5",(0,(2,2)))]:
    line_key.plot([x,x],[.02,.27],lw=.60,linestyle=style,color="#252525")
    line_key.text(x,.34,label,ha="center",va="bottom",rotation=90,fontsize=4.55)
