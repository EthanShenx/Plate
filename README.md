# Plate

Plate is a local macOS workbench for assembling publication figures from R and Python scripts, images, imported vectors, text and legends. Each plot renders at its final physical size. Panels sit independently on a shared artboard.

## Start on macOS 13 or later

Install Python 3.10 or later, Node.js 20 or later, and the macOS command-line tools. Install R from [CRAN](https://cran.r-project.org/bin/macosx/) if you use R panels. The default Python for plots is the app's repository-local environment. You can select another Python, virtualenv or conda environment from the inspector. Plate uses the framework or Homebrew R installation.

```sh
make run
```

The command installs the app dependencies in this checkout, builds CodeMirror and opens the workspace in your browser. To open it in another tab, use the `http://127.0.0.1:…` address printed in Terminal. Keep the command running while you use Plate. Run scripts and open bundles from sources you trust, since the interpreters run with your permissions.

For the default environment and the sample project, install the plotting packages once.

```sh
.venv/bin/python -m pip install matplotlib seaborn
Rscript -e 'install.packages(c("ggplot2", "jsonlite", "systemfonts", "patchwork"), repos="https://cloud.r-project.org")'
```

Use `brew install librsvg` if you plan to import SVG. If **Dependencies** reports a missing Cairo PDF device in CRAN R, install [XQuartz](https://www.xquartz.org/) with `brew install --cask xquartz`. You can check an individual interpreter and copy the relevant package command from the **Dependencies** button. Plot packages are installed by the user.

## Five-minute tutorial

1. Run `make run BUNDLE=examples/nature-double.plate`. The 183 × 123 mm project contains four plot scripts, a synthetic microscopy image and a shared legend. Plate renders any out-of-date panels automatically.
2. Drag a panel to move it. Drag any corner to resize it against the opposite corner. Both gestures snap to the artboard grid, which defaults to 2 mm. Change **Grid spacing (mm)** in Figure settings. To enter exact positions or sizes, use the panel’s **Geometry** section. Adjust stacking under **Arrange**.
3. Open **Figure settings** to change a font role, stroke or group colour. Select a panel to edit its label or change its style settings. Previous previews stay visible while Plate renders the changes.
4. Select a script panel and choose **Edit script**. **Run** saves and renders it. Choose **More → Show script in Finder** to locate the live workspace file. Changes saved in an external editor reload into CodeMirror. Use **Checks** to locate print-size warnings.
5. Choose **File → Save as…** to save a separate `.plate` bundle and optionally include previews. **Save** writes subsequent changes to that bundle. Choose **Export** for an editable PDF or an RGB TIFF/PNG at 300, 600 or 1200 dpi.

In a script panel’s **Source → Render inputs**, list the data files and helper scripts it reads. Plate refreshes the panel when a listed file changes. Use **Edit script → More → Force render** for a database query or another input outside that list. Export refreshes pending panels and requires current artwork for every panel. If any panel is incomplete, the dialog lists what a draft would reuse or omit and lets you explicitly choose **Export draft**.

Pinch over the canvas to zoom. **Fit** fits the figure to the workspace and **100%** resets the display scale. **⌘ Enter** refreshes the selected panel and **⌘ Shift Enter** refreshes all out-of-date panels. **⌘ Z** and **⌘ Shift Z** undo and redo figure changes. CodeMirror has its own text history.

Drag from empty canvas space to select several panels, or Shift-click panels to add or remove them. Drag a selected panel to move the selection, or drag a selection corner to scale it. In **Selection geometry**, use **Set panel sizes** to give each panel the same width or height. Press **Esc** to clear the selection.

A `.plate` file contains layout, styles, scripts and imported figure assets. Data files loaded by scripts stay in their original locations. Set **Advanced → Data folder** or place your data relative to the bundle directory. Use **File → Show workspace in Finder** to inspect extracted project files and logs. The script contract covers plotting, styling and running the helpers outside Plate.

Saved bundles also record interpreter and loaded package versions and the fonts found in successful renders, even when previews are excluded. In **Figure settings → Advanced**, choose **Compare render environment** to check that record against local installations. Set **Local data folder** to use a different data location for this workspace. Clear it to use the bundle’s data folder again. The local path stays with the workspace.

Run the local test suite with `make test` after installing the plotting prerequisites. The render tests report missing interpreters or plotting packages as skips. See the [script contract](docs/script-contract.md), [architecture](ARCHITECTURE.md) and [export acceptance checklist](docs/ACCEPTANCE.md).

## Command-line authoring

Use `.venv/bin/python -m plate build`, `inspect`, `apply` and `export` to assemble and revise figures from scripts and JSON. The commands return JSON geometry and print checks that an agent can use to make the next edit. [Command reference and specification example](docs/cli.md)
