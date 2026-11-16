# Use Plate without a browser

Run these commands from the Plate checkout with its Python environment. They use the same layout, rendering, checks and export code as the browser. The Python and R environments only need the plotting packages used by their panels.

```sh
.venv/bin/python -m plate build figure.json --output figure.plate
.venv/bin/python -m plate inspect figure.plate
.venv/bin/python -m plate apply figure.plate revision.json --output figure-v2.plate
.venv/bin/python -m plate export figure-v2.plate --output figure-v2.pdf
```

For a raster proof or final raster export, use `--output proof.png` or `--output figure.tiff` and optionally `--dpi 300`, `600` or `1200`.

Each command prints one JSON object with `ok`. Successful commands return the project size, panel IDs and rectangles, groups, and checks. Export also returns the output path. Build, apply and export render out-of-date panels before writing the requested file. Render failures return panel errors and captured stderr, exit with status 1, and leave the requested output untouched. Print checks such as possible text overlaps are advisory. Their results include the panel ID and available bounding boxes in PDF points. Inspect reads the saved bundle and does not run scripts.

## Figure specification

Coordinates use millimetres from the upper left of the artboard. The order of panels establishes their stacking order. Script, asset and data paths are relative to the specification file. Panel scripts and imported images or vectors are stored in the bundle. External data read by scripts stays at its source location.

```json
{
  "name": "Two-panel example",
  "size": {"width_mm": 120, "height_mm": 65},
  "style": {"font_family": "Arial", "font_main_pt": 7},
  "panels": [
    {
      "id": "trend",
      "type": "script-py",
      "label": "a",
      "rect": {"x": 4, "y": 4, "w": 54, "h": 56},
      "script_file": "trend.py"
    },
    {
      "id": "summary",
      "type": "text",
      "label": "b",
      "rect": {"x": 63, "y": 4, "w": 53, "h": 56},
      "settings": {"text": "Synthetic data"}
    }
  ],
  "groups": [{"id": "results", "name": "Results", "panels": ["trend", "summary"]}]
}
```

Use `script-r` for R, `script-py` for Python, or `text`, `legend`, `image` and `vector` for native panels. For a script panel, set `script_file` or provide source via `script`. For imported artwork set `asset_file`. See [the script contract](script-contract.md) for the Python and R entry points.

Optional project fields include `palettes`, `alignment`, `interpreters`, `data_root`, `grid_mm`, and `timeout_s`. Panel records can also set `name`, `settings`, `overrides`, `locks` and `interpreter`. When external data changes, rebuild from the source specification to refresh plots whose code has stayed the same.

An apply patch updates panels by ID. Unlisted panels keep their geometry and source. A new panel requires a complete rectangle. A patch can update selected rectangle coordinates or replace a script. If you supply `groups` or `alignment`, it replaces that list. To delete panels, pass their IDs in `remove_panels`.

```json
{
  "panels": [
    {"id": "trend", "rect": {"w": 57}},
    {"id": "summary", "rect": {"x": 65, "w": 51}}
  ]
}
```

Use a distinct output path when the project is already open for editing in the browser. Open the resulting bundle in Plate to continue from the CLI revision.
