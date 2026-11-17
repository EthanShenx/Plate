# Plate

**Build publication figures from the code that made them.**

Put R and Python plots, images, and legends on one canvas. Resize a panel and Plate redraws the plot at its final print size. Change a group colour once and every plot using it updates. When the figure is ready, export an editable PDF with selectable text or a high-resolution TIFF or PNG.

[Install Plate](#install) · [Make your first figure](#make-your-first-figure)

## Watch Plate in action

See how to build three panels from code, change a colour across the figure, and make room for a panel before exporting.

https://github.com/user-attachments/assets/6be71697-e6bc-4618-8e06-54d2d3d3ff21

## Install

Build Plate on your Mac. You’ll need [Python 3.10 or later](https://www.python.org/downloads/macos/), [Node.js 20 or later](https://nodejs.org/en/download), and Apple’s command-line tools (`xcode-select --install`). Install [R](https://cran.r-project.org/bin/macosx/) if you use R plots or want to try the sample figure.

```sh
git clone https://github.com/EthanShenx/Plate.git
cd Plate
```

### Mac app

Requires macOS 14 or later. Build it once, then open **Plate** from your Applications folder or Spotlight. Quit Plate before rebuilding it after an update.

```sh
make macos MAC_APP="$HOME/Applications/Plate.app"
open "$HOME/Applications/Plate.app"
```

### Browser

On macOS 13 or later, run `make run`. Keep Terminal open while you work. The Mac app and browser use the same `.plate` format and keep separate draft libraries.

### Plotting packages

If you already have a plotting environment, select its interpreter in Plate. For the sample below, install these packages once after building or starting Plate.

```sh
.venv/bin/python -m pip install matplotlib seaborn
Rscript -e 'install.packages(c("ggplot2", "jsonlite", "systemfonts", "patchwork"), repos="https://cloud.r-project.org")'
```

## Make your first figure

Open [`examples/nature-double.plate`](examples/nature-double.plate) with **File → Open**. In the browser version, run `make run BUNDLE=examples/nature-double.plate`. The sample mixes R and Python plots with a synthetic microscopy image and a shared legend.

1. **Arrange the panels.** Drag a panel to move it or drag a corner to resize it. Use **Geometry** to enter exact dimensions in millimetres.
2. **Set the figure style.** New artboards start in portrait at 122 × 183 mm. Choose **Swap width and height** under **Figure settings → Artboard** to switch orientation. Pick a journal width and set fonts, strokes, and group colours in **Figure settings**.
3. **Revise a plot.** Select a script panel, choose **Edit script**, then click **Run**. List its data files and helpers under **Source → Render inputs** so Plate refreshes the plot when they change.
4. **Check and export.** Open **Checks** to review small text, low-resolution images, and other print warnings. Save your work as a `.plate` file, then export an editable PDF or a TIFF or PNG at 300, 600, or 1200 dpi.

To start from scratch, choose **New project** and **Add panel**. You can mix R and Python scripts with images, PDF or SVG artwork, text, and legends.

## Share a figure

Choose **File → Save shareable copy…** and send the resulting `.plate` file. The recipient opens it in Plate and can edit the layout, scripts, and styles. Imported artwork and the data files and helpers listed under each script panel’s **Source → Render inputs** travel with the copy. Use paths relative to the data folder in both your scripts and the input list.

The recipient uses their own R and Python installations. **Compare render environment** shows which versions, packages, and fonts the sender used. To edit bundled input files directly, choose **File → Show workspace in Finder** and open the `data` folder. You can also point Plate to a different folder under **Figure settings → Advanced → Local data folder**.

Plate runs locally and opens plotting scripts with your permissions. Use scripts and bundles from sources you trust.

## More help

- [macOS build and troubleshooting](docs/macos.md)
- [Writing R and Python panels](docs/script-contract.md)
- [Building and exporting figures from the command line](docs/cli.md)
