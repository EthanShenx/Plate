"""Compare direct PDF placement and SVG conversion using identical plot content."""

from pathlib import Path
import shutil
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import pymupdf

from plate.export import compose_pdf


def describe(path):
    with pymupdf.open(path) as pdf:
        page = pdf[0]
        fonts = [(entry[3], bool(pdf.extract_font(entry[0])[3])) for entry in page.get_fonts()]
        return {
            "size_pt": tuple(page.rect)[2:],
            "text": page.get_text().splitlines(),
            "fonts": fonts,
            "top_level_forms": sum(item[2] == 0 for item in page.get_xobjects()),
            "nested_forms": sum(item[2] != 0 for item in page.get_xobjects()),
            "images_px": [(item["width"], item["height"]) for item in page.get_image_info()],
        }


def main(destination):
    destination.mkdir(parents=True, exist_ok=True)
    matplotlib.rcParams.update({"font.family": "Arial", "svg.fonttype": "none", "pdf.fonttype": 42,
                                "image.composite_image": False})
    fig, ax = plt.subplots(figsize=(2, 1.5))
    ax.set(xticks=[0, 1], yticks=[0, 1], xlabel="Live label", xlim=(0, 1), ylim=(0, 1))
    ax.plot([0, 1], [0, 1])
    fig.subplots_adjust(left=.23, bottom=.30, right=.90, top=.90)
    fig.savefig(destination / "source.pdf")
    fig.savefig(destination / "source.svg")
    svg = (destination / "source.svg").read_text()
    bitmap = np.zeros((11, 17, 3), dtype=np.uint8)
    bitmap[:, 6:, 0] = 150
    png = destination / "source.png"
    Image.fromarray(bitmap).save(png)
    with pymupdf.open() as image:
        page = image.new_page(width=20, height=20)
        page.insert_image(page.rect, filename=str(png), keep_proportion=False)
        image.save(destination / "image.pdf")
    figure_size = (66, 38.1)
    content = [(destination / "source.pdf", {"x": 0, "y": 0, "w": 50.8, "h": 38.1}),
               (destination / "image.pdf", {"x": 52, "y": 0, "w": 20*25.4/72, "h": 20*25.4/72})]
    (destination / "placed.pdf").write_bytes(compose_pdf(*figure_size, content))
    print("A · PDF Form XObjects", describe(destination / "placed.pdf"))
    if not shutil.which("rsvg-convert"):
        raise SystemExit("Install librsvg to run the SVG arm of the spike.")
    from base64 import b64encode
    body = svg[svg.index("<svg "):].replace('id="figure_1"', 'id="panel_a"', 1)
    encoded = b64encode(png.read_bytes()).decode()
    (destination / "composed.svg").write_text(f'''<svg xmlns="http://www.w3.org/2000/svg"
        xmlns:xlink="http://www.w3.org/1999/xlink" width="66mm" height="38.1mm"
        viewBox="0 0 {66 * 72 / 25.4} 108">
        <g id="panel_a_wrapper">{body}</g>
        <g id="panel_b"><image x="{52 * 72 / 25.4}" width="20" height="20"
          preserveAspectRatio="none" xlink:href="data:image/png;base64,{encoded}"/></g>
        </svg>''')
    subprocess.run(["rsvg-convert", "--format=pdf", "--output", str(destination / "converted.pdf"),
                    str(destination / "composed.svg")], check=True)
    print("B · Composed SVG via librsvg", describe(destination / "converted.pdf"))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
