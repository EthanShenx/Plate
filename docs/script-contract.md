# Panel script contract

Use one script per panel. A single plot can contain facets or subplots. Plate resolves a panel's data root, exact content dimensions and style before running a fresh process. Relative data paths resolve from **Data root**, or from the bundle directory when that field is empty.

## Python

Assign a Matplotlib figure to `fig` or leave the target as the current figure. The runner sets its final size after executing the script. It uses its regular PDF backend with live text.

```python
import matplotlib.pyplot as plt
import plate

fig, ax = plt.subplots(figsize=[mm / 25.4 for mm in plate.size_mm])
fig.subplots_adjust(left=.23, right=.95, bottom=.24, top=.91)
ax.plot([0, 1, 2], [0.2, 0.4, 0.6],
        color=plate.colors.get("Treatment", plate.palette[1]))
ax.set(xlabel="Dose", ylabel="Response")
```

## R

Assign a ggplot2 or patchwork object to `p` or return it visibly from a top-level expression. For base graphics, draw on the device Plate opens. Produce a single page and leave device management to Plate. A script can add a custom theme or explicit aesthetic settings where needed.

```r
library(ggplot2)
if (!exists("plate", inherits = FALSE)) plate <- plate::plate_context()
d <- data.frame(Dose = 0:2, Response = c(.2, .4, .6))
colour <- if ("Treatment" %in% names(plate$colors)) plate$colors[["Treatment"]] else plate$palette[[2]]
p <- ggplot(d, aes(Dose, Response)) +
  geom_line(colour = colour) +
  labs(x = "Dose", y = "Response")
if (!nzchar(Sys.getenv("PLATE_STYLE"))) print(p)
```

For base graphics, use `plot()`, `lines()` and `text()` in the script. Keep space for axis text and titles at the final dimensions. An explicit `par()` call can override device defaults.

## Style and standalone use

The helpers expose `style`, `size_mm`, `palette` and `colors`. Use the semantic map explicitly for mapped group aesthetics, for example `scale_colour_manual(values = plate$colors)` or `palette=plate.colors` in seaborn. Plate reapplies supported panel overrides to Matplotlib and ggplot2 objects after the script runs. Palette overrides supply the default colour cycle. Explicit colours and mapped scales remain under script control. **Use the script’s style** skips injection and still provides the helper context and final content dimensions.

Plate adjusts Matplotlib margins when labels extend past the PDF page. If the full content still exceeds the page, Plate fits it proportionally and reports this in **Checks**. Enlarge the panel to keep the requested font sizes.

To draw connectors or other layout-aware artwork, choose panels in **Geometry → Referenced panels**. A bundle specification can set the same references under a script panel’s `settings.geometry_refs` as a list of panel IDs. In Python, `plate.context.get("panel_boxes_mm", {})` maps those IDs to content rectangles with `x`, `y`, `w` and `h`. R exposes the map as `plate$panel_boxes_mm`. Coordinates are in millimetres from the script panel’s content origin, measured to the right and down. The content rectangle starts below the panel letter. Plate rerenders the script when a referenced rectangle changes relative to it. Deleted references are absent from the map. Give the drawing panel enough room for its connectors to stay within the page it renders.

Install the helpers into your chosen standalone environment from the checkout.

```sh
python -m pip install ./helpers/python
R CMD INSTALL ./helpers/r/plate
```

The helpers load their default context when no style file is configured. To reproduce a style outside Plate, choose **Runtime → Export style JSON**, then run with `PLATE_STYLE=/path/to/plate-style.json`. The exported context contains the figure size. Set its `size_mm` to the standalone panel's content dimensions where needed. Standalone scripts manage their own devices and may apply the helper values explicitly.

Declare file inputs in **Source → Render inputs** or in a script panel’s `input_files` array in the CLI specification. Use paths relative to the active data folder so the same declarations work on other machines. List referenced data files and any local helper scripts they depend on. Python workers can import modules from the data folder. R workers can use relative `source()` paths. Plate fingerprints the contents and renders affected panels again when a declared input changes. A missing or unreadable input produces a render error.

Use **Force render** or the CLI’s `--force` flag when inputs cannot be represented as files or when you change plotting packages.
