# Plate

Plate is a local macOS workbench for assembling publication figures from R and Python scripts, images, imported vectors, text and legends. Each plot renders at its final physical size. The project holds a common style and a layout that retiles as panels move.

## Start on macOS 13 or later

Install Python 3.10 or later, Node.js 20 or later, and the macOS command-line tools. Install R from [CRAN](https://cran.r-project.org/bin/macosx/) if you use R panels. The default Python for plots is the app's repository-local environment. You can select another Python, virtualenv or conda environment from the inspector. Plate uses the framework or Homebrew R installation.

```sh
make run
```

The command installs the app dependencies in this checkout, builds CodeMirror and opens your browser. Plate listens on a randomly selected loopback port. Run scripts and open bundles from sources you trust, since the interpreters run with your permissions.

For the default environment and the sample project, install the plotting packages once.

```sh
.venv/bin/python -m pip install matplotlib seaborn
Rscript -e 'install.packages(c("ggplot2", "jsonlite", "systemfonts", "patchwork"), repos="https://cloud.r-project.org")'
```

Use `brew install librsvg` if you plan to import SVG. You can check an individual interpreter and copy the relevant package command from the **Dependencies** button. Plot packages are installed by the user.

## Five-minute tutorial

1. Run `make run BUNDLE=examples/nature-double.plate` and choose **Refresh all stale**. The 183 × 123 mm project contains four plot scripts, a synthetic microscopy image and a shared legend.
2. Drag a panel onto an edge target to insert it beside another panel, or onto a centre target to swap them. A frame-edge target creates a full-width row or full-height column. Drag a gutter to resize. The geometry inspector offers numeric edits and width or height locks.
3. Click the paper margin to open global settings. Change a font role, stroke or semantic colour, then refresh. Stale script previews stay visible. Select a panel to edit its label, opt out of style injection or override individual tokens.
4. Select a script panel and edit it in CodeMirror. **Run** saves and refreshes it. **Reveal script** shows the live workspace file in Finder. Changes saved in an external editor reload into CodeMirror. Use **Checks** to locate print-size warnings.
5. Use **Save** to write a `.plate` bundle and optionally include previews. Choose **Export** for an editable PDF or an RGB TIFF/PNG at 300, 600 or 1200 dpi. Use a different save path to keep the bundled sample available for future tutorials.

**⌘ Enter** runs the selected script. **⌘ Shift Enter** refreshes stale panels. **⌘ Z** and **⌘ Shift Z** undo and redo figure changes. CodeMirror has its own text history. **Actual size** uses a 50 mm calibration ruler. Recalibrate after changing display scale or browser zoom.

A `.plate` file contains layout, styles, scripts and imported figure assets. Data files loaded by scripts stay in their original locations. Set **Runtime → Data root** or place your data relative to the bundle directory. Use the Finder workspace shortcut to inspect extracted project files and logs. The script contract covers plotting, styling and running the helpers outside Plate.

Run the local test suite with `make test` after installing the plotting prerequisites. The render tests report missing interpreters or plotting packages as skips. See the [script contract](docs/script-contract.md), [architecture](ARCHITECTURE.md) and [export acceptance checklist](docs/ACCEPTANCE.md).
