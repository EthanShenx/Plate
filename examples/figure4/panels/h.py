import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import plate

rng = np.random.default_rng(84 + (0 if PART == "legend" else PART))
pathways = [
    "CXCL ADGRG ADGRE VISFATIN CD45 MIF CD99 CyPA CLDN TNF GALECTIN MHC-II".split(),
    "SELE CXCL IL2 PLAU ADGRE Cholesterol Prostaglandin FN1 COLLAGEN LAMININ MIF CD99 APP TNF IL16 CSF IGFBP CLDN GALECTIN MHC-II".split(),
    "THBS FN1 COLLAGEN SPP1 VEGF ADGRG COMPLEMENT ANNEXIN ICAM IL1 TNF MIF Testosterone GALECTIN CD80 Cholesterol CCL CD45 PSAP DHEA SELPLG VCAM UNC5 FLRT PLAU CADM GDF ADGRL".split(),
    "MK ANNEXIN IGF JAM ICAM THY1 PTN CCL GDF FN1 CD80 CSF TNF MIF COLLAGEN CXCL LAMININ ANGPTL CD45 ANGPT COMPLEMENT THBS SPP1 TENASCIN SEMA7 FLRT IL6 PLAU SELE Prostaglandin Cholesterol FGF NCAM NOTCH CADM KIT".split(),
]
fig = plt.figure()
healthy, disease = (plate.colors[key] for key in ("Healthy", "Disease"))
if PART == "legend":
    fig.legend(handles=[Patch(fc=healthy,label="Healthy"),
                        Patch(fc=disease,label="Psoriasis / IMQ")],
               ncol=2, loc="center", frameon=False, handlelength=.85,
               borderaxespad=0, columnspacing=1.1, fontsize=4.6)
else:
    names = pathways[PART]
    ax = fig.add_axes([.51,.12,.46,.77])
    shares = np.sort(rng.beta(.67,.7,len(names)))[::-1]
    y = np.arange(len(names))
    ax.barh(y,shares,height=.78,color=healthy)
    ax.barh(y,1-shares,left=shares,height=.78,color=disease)
    ax.axvline(.5,color="#2e333d",lw=.35,ls=":")
    ax.set(ylim=(len(y)-.45,-.55), xlim=(0,1), xticks=[0,1], yticks=y, yticklabels=names)
    ax.tick_params(axis="both", length=1.1, pad=1, labelsize=4.1)
    species = "Human" if PART < 2 else "Mouse"
    role = "sender" if PART % 2 == 0 else "target"
    ax.set_title(f"{species} {role}", fontsize=4.9, pad=3, loc="right")
    ax.set_xlabel("Relative flow", fontsize=4.5, labelpad=1)
    for label, share in zip(ax.get_yticklabels(), shares, strict=True):
        if share > .69 or share < .30:
            label.set_color("#9f3b37" if share>.69 else disease)
