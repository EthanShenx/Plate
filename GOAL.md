## 0. Your role and how to work

You are building a local tool, end to end, in this repository. Work autonomously. When something is ambiguous, make the most reasonable choice, keep going, and record it in `DECISIONS.md` (one line per decision: what, why, alternatives). Even though the goal is the full v1 in one pass, build in the stage order in §8 so the app is runnable and tested after every stage. Commit at each stage boundary.

## 1. Product summary

Researchers build main-text figures out of several small panels (a, b, c…). Today each panel is made separately in R or Python, exported, and then assembled by hand in Illustrator. This breaks the work into many files, and font sizes, line widths and colours drift between panels.

Plate is a **local web app** for **macOS**, used by one researcher or a small lab, that:

1. Makes each panel from an **R or Python plotting script**, rendered **directly into the composed figure** at its exact final physical size. No intermediate export/import step.
2. Applies **one global style** to every panel at once: main font size, minimum font size, font family, role-based text sizes, line widths, markers/ticks, axis style, gutters, palette.
3. Lets the user **freely drag and resize panels**, while an auto-fill solver guarantees that **the panels always tile the whole frame with no blank areas** (apart from uniform gutters).
4. Offers **journal size presets**.
5. Exports a **vector PDF that stays editable** (live text, clean object tree, untouched embedded rasters), plus high-res **TIFF/PNG**.

## 2. Fixed decisions (from the product owner)

| Area | Decision |
|---|---|
| Users | Owner and their lab; internal tool. Favour correctness and speed of iteration over polish. |
| Platform | Local web app: a local server bound to `127.0.0.1`, with the UI in the browser. **macOS only.** |
| Languages | **R and Python, equal first-class support** (ggplot2 / base R; matplotlib / seaborn). |
| Runtime | The **user's own environments**: detect Rscript, system/Homebrew Python, conda envs, venvs. Nothing is bundled. |
| Style delivery | **Auto-inject the global style before each script runs, with per-panel opt-out/overrides.** |
| Panel types | Script plots (one script may produce facets/subplots), **imported raster images**, **imported vectors (PDF/SVG)**, **text / legend panels**. |
| Panel labels | **Manual**: the user types each label. The app styles and positions labels consistently. |
| Code editing | **Both**: an in-app code editor, plus live reload when a script file changes in an external editor. |
| Layout | **Free drag + auto-fill solver**: no blanks, ever. |
| Re-render | **On demand**: resized or restyled panels show a scaled preview marked *stale* until the user refreshes. |
| Alignment | **Optional per row/column lock** of plot-area edges across panels. |
| Sizes | **Journal presets** (width), stored in an editable JSON file. The user sets the height. |
| Typography | Main size, minimum size, font family, role-based sizes, all in **physical points at final print size** (never rescaled). |
| Min-font rule | **Warn + highlight** violations on the canvas. Export is not blocked. |
| Palette | Built-in palettes (colourblind-safe + common), custom palette editor, **semantic colour map** (same group = same colour in every panel). |
| Other unified styles | Line widths, markers & ticks, panel gutters/margins, axis style (spines, grid, background). |
| Export | **Vector PDF** + **TIFF/PNG** at 300/600/1200 dpi. |
| PDF editability | Text stays **live text** with embedded fonts. **Clean object tree** with no needless clip masks or nested junk groups. **Embedded rasters keep native resolution.** |
| Project file | **Single bundled file** (see §4.12). |
| Data | Scripts load data **from their own paths**. The app does not manage data. |
| Stack | **Your choice.** Justify it in `ARCHITECTURE.md` (see §7). |

## 3. Core domain model

- **Project**: one figure. It holds the figure size, global style, palette and semantic colour map, the layout, and its panels.
- **FigureSize**: a preset ID plus a width in mm (from the preset) and a height in mm (set by the user). Also an outer margin and the gutter in mm.
- **Panel**: id, type (`script-r`, `script-py`, `image`, `vector`, `text`, `legend`), label text (manual), label style overrides, style overrides (opt-out), and its render state (`fresh`, `stale`, `rendering`, `error`). Script panels also store the script source and interpreter selection.
- **Layout**: the solver state (see §4.2). Panel rectangles in mm are always *derived* from it, never stored as free coordinates.
- **Style**: a flat, typed set of tokens (see §4.4). Every token has a global value and may be overridden per panel.

Use **mm** for geometry and **pt** (1/72 in) for type and stroke throughout the data model. Convert to each backend's native units only at the injection boundary.

## 4. Functional requirements

### 4.1 Figure sizes
- Load presets from `presets/journals.json`, which the user can edit and extend. Ship these entries, each with `source_url` and a `verified` flag:
  - **Nature**: single 89 mm, 1.5-col 120 mm and 136 mm, double 183 mm. Full page depth 247 mm, 170 mm max if the legend must fit below. Verified at nature.com final-submission guidelines and research-figure-guide.nature.com.
  - **Cell Press (2-column journals)**: 85 / 114 / 174 mm. `verified: false`. Confirm against cell.com figure guidelines.
  - **PNAS**: 87 / 114 / 178 mm, max height 225 mm. `verified: false`. Confirm against the PNAS Digital Art Guidelines.
  - **Science**: secondary sources conflict, so ship the entry with `widths: null`, `verified: false` and a TODO. The UI must disable presets that have null widths.
- The user picks a preset width and types a height. Show the preset's max height as a non-blocking guide line on the canvas.

### 4.2 Layout: free drag + auto-fill, no blanks
**Invariant (must hold after every operation):** the panel rectangles, separated by exactly `gutter` mm and inset by exactly `margin` mm, tile the frame completely. There are no overlaps and no gaps, and every panel is at least the minimum size (default 12 × 12 mm, configurable).

Recommended internal model: a **guillotine split tree** (each internal node splits horizontally or vertically into ≥2 children, with weights). Any arrangement reached by the UI must be one this solver can represent. If you choose a different model (e.g. a constraint solver), it must keep the same invariant and pass the same property tests.

Interactions:
- **Move (free drag):** drag a panel by its body. While dragging, show drop targets on every other panel: left, right, top or bottom edge zone (insert beside, splitting that panel's region) and centre (swap). On drop, the solver re-tiles and the result animates into place. Dropping on the frame edge inserts a full-width row or full-height column.
- **Resize:** drag any shared edge. Every panel bordering that edge line moves with it, and the neighbours shrink or grow to compensate. Clamp at the minimum panel size.
- **Numeric edit:** an inspector shows x, y, w, h in mm. Edits are applied through the solver, which adjusts neighbours.
- **Add:** a new panel splits the currently selected panel, or is dropped into a target. **Delete:** its siblings expand to fill the space.
- **Optional per-panel lock** on width or height in mm, so it survives other resizes. If locks over-constrain the layout, show a clear message instead of breaking the invariant.
- **Snapping:** edges snap to align with other panels' edges and to simple ratios (1/2, 1/3, 2/3) when within a few px.
- Undo/redo covers all layout, style and label operations.

### 4.3 Script panels: execution contract
- **Interpreter discovery (macOS):** find `Rscript` on PATH, in `/opt/homebrew/bin`, in `/usr/local/bin` and in `/Library/Frameworks/R.framework/Resources/bin`. Find Python from PATH, `conda env list`, and user-added venv paths. A browser-launched server may not inherit the login-shell PATH, so resolve it explicitly. The project sets a default interpreter for each language, and each panel can override it.
- **Dependency check:** verify required packages (R: `ggplot2`, `jsonlite`, plus whatever your render pipeline needs; Python: `matplotlib`). Show copy-pasteable install commands, and never install anything automatically.
- **Working directory:** a project-level "data root" (defaults to the folder containing the bundle file). Warn when a script uses absolute paths, since those break portability.
- **What the runner does for each render:**
  1. Start an isolated execution (fresh process, or a warm worker with fully reset state; no rcParams/theme leakage between panels).
  2. Inject the resolved style for this panel (§4.4) and the panel's exact **content box size in mm**: the panel rect minus the label reservation, if any.
  3. Run the user script.
  4. Capture the result. Python: the figure the script created (`plt.gcf()` or a variable named `fig`). R: an object named `p`, the last visible ggplot/patchwork value, or base-graphics output drawn into a device the runner opened beforehand.
  5. Force the final size to exactly the content box and save in the pipeline's vector format. **Never use `bbox_inches="tight"` or any auto-cropping**, because the output must be exactly the box size.
  6. Return the output, captured stdout/stderr, timing and a metadata JSON (text runs with font size, font name and bbox; plot-area bbox, for alignment).
- **Timeout** per render (default 60 s, configurable). Errors appear on the panel as a red state, with the traceback shown in the editor pane.
- **Helper library (ship it):** a tiny R package and Python module, both named `plate`. Scripts can read `plate$colors` / `plate.colors` (semantic map), `plate$palette`, `plate$size_mm` and `plate$style`. Scripts must also run **standalone** outside the app: the helper falls back to defaults, or to a style JSON exported from the project. This keeps panels reproducible.

### 4.4 Global style system and injection
Style tokens (all physical units):
- Text: `font_family`, `font_main_pt`, `font_min_pt`, plus role sizes `axis_title_pt`, `tick_label_pt`, `legend_title_pt`, `legend_text_pt`, `annotation_pt` and `panel_label_pt`, with `panel_label_weight` (bold by default). Role sizes default to values derived from main/min but are individually editable.
- Strokes: `line_data_pt`, `line_axis_pt`, `tick_length_pt`, `tick_width_pt`, `tick_direction` (in/out).
- Markers: `marker_size_pt`.
- Axis style: spines (all / left-bottom / none), grid (none / major), panel background (none / white).
- Colour: active palette and semantic colour map.
- Spacing: `gutter_mm`, `margin_mm`, label reservation size and offset.

Injection:
- **Python:** set `matplotlib.rcParams` (font.family, font.size, axes.labelsize, xtick/ytick sizes and widths, lines.linewidth, lines.markersize, axes.linewidth, axes.prop_cycle from the palette, axes.spines.*, axes.grid, legend.fontsize, and so on), plus `pdf.fonttype = 42` and `svg.fonttype = "none"` so text stays text. If seaborn is importable, apply the palette to it too. Matplotlib already works in pt, so map tokens 1:1.
- **R:** call `theme_set()` with a generated theme, `update_geom_defaults()` for line widths and point sizes, and the `ggplot2.discrete.colour` / `ggplot2.discrete.fill` options for the palette. Expose the semantic map so `scale_*_manual(values = plate$colors)` works. Use `par()` for base graphics.
  - **Unit pitfalls you must handle and test:** ggplot2 text `size` is in mm (`pt / .pt`), while `theme(element_text(size=))` is in pt. ggplot2 `linewidth` is multiplied by `.pt` into grid `lwd`, and grid/R devices treat `lwd = 1` as 1/96 inch, not 1 pt. Derive the exact conversion, and **verify it by measuring stroke widths in the output PDF** (see §9).
- **Fonts:** the chosen family must resolve to the same font in R (`systemfonts`) and in matplotlib (`font_manager`). Detect silent fallback (matplotlib's DejaVu Sans substitution, for example) by checking font names in the rendered output, and raise a warning.
- **Opt-out:** in the inspector, any token can be overridden per panel (for example, a heatmap with its own continuous palette). Overrides are shown visibly, so it is always clear which panels deviate from the global style.
- Any change to the global style marks every affected panel *stale*.

### 4.5 Palettes and semantic colour map
- Built-in palettes: at least Okabe–Ito, a viridis family sampler, Tableau 10, and a greyscale set. Mark which are colourblind-safe.
- Custom palette editor: add/remove/reorder colours, hex input, save to the project, export/import as JSON.
- **Semantic colour map:** a `{group label → colour}` table at project level (for example Control → grey, Treatment → orange). It is injected into both languages and drives the auto-generated legend panel (§4.9). Renaming a key updates every panel on the next refresh.

### 4.6 Optional plot-area alignment
- The user can lock alignment for a row or column of panels. Locked panels share left/right (column lock) or top/bottom (row lock) plot-area edges, so axes line up across panels.
- Algorithm (two-pass): render each panel once to measure its natural plot-area insets from the metadata JSON. Compute the maximum inset needed on the shared side. Re-render each locked panel with a **fixed plot-area inset** injected: matplotlib via absolute axes position in inches; R via fixed panel size or margins (for example `ggh4x::force_panelsizes`, `egg::set_panel_size` or a gtable approach; choose one and document it).
- Panels with multiple subplots align on their outermost plot-area bbox.

### 4.7 Rendering, refresh and cache
- Re-rendering is **on demand**. When a panel is resized or its style changes, show the last render scaled into the new box, with a clear *stale* badge. Buttons: **Refresh panel**, **Refresh all stale**, each with a keyboard shortcut that does not collide with browser reload.
- Keep a content-hash cache (script + resolved style + box size + interpreter version) inside the working directory, so unchanged panels are never re-run.
- The canvas shows panel previews at screen resolution. It has a zoom control and an **actual-size** mode with a one-time screen calibration (the user matches an on-screen ruler to a physical ruler).

### 4.8 Panel labels (manual)
- The user types any label text (for example "a", "b", "i"). The app places every label at a consistent offset in the panel's top-left label reservation, with `panel_label_pt` and its weight. The user can nudge the global offset, but not per panel. Panels with an empty label reserve no space if "collapse empty labels" is on.

### 4.9 Non-script panels
- **Image (raster):** fit modes contain / cover with a crop rect. Embedded at **native pixel data**, scaled only by placement and never resampled. Show the effective dpi and warn below 300.
- **Vector (PDF/SVG):** placed as vector. Global style cannot be injected, so show a badge for that. Min-font checking still applies.
- **Text:** a text box using the global family and role sizes (main/annotation), with left/centre/right alignment.
- **Legend:** auto-generated from the semantic colour map. The user selects which keys to show, horizontal or vertical layout, and the swatch type (patch / line / point).

### 4.10 Code editor (in-app + external)
- An in-app editor (Monaco or CodeMirror) with R/Python syntax highlighting sits beside the canvas for the selected panel. It has a Run button and shows the error/stdout output.
- Scripts are real files in the project's working directory (§4.12). "Open in external editor" reveals the path or opens it. A file watcher reloads external changes into the in-app editor and marks the panel stale. Unsaved in-app edits that conflict with an external change trigger a prompt.

### 4.11 Validation: minimum font size and fonts
- After each render, read the text runs from the metadata, or parse the panel's vector output (effective size = font size × text matrix scale × CTM scale).
- Any text below `font_min_pt` is **highlighted on the canvas** with an outline box and listed in a **Checks** sidebar (panel, text string, actual size). Clicking an entry selects that panel.
- Also flag: fonts that are not the chosen family, imported rasters below 300 dpi, panels whose render is stale at export time, and presets that are not verified.
- Checks never block export. The export dialog shows a summary of open warnings.

### 4.12 Project bundle (single file)
- File extension `.plate`: a zip containing `manifest.json` (with `schema_version`), `layout.json`, `style.json`, `palettes.json`, `panels/<id>/script.(R|py)` + `panel.json`, `assets/` (imported images/vectors), and optionally `cache/` (the user can strip it to shrink the file).
- On open, unpack to a working directory (for example `~/Library/Application Support/Plate/workspaces/<project-id>/`) so scripts are real files for external editors and the file watcher. Autosave to the working directory. **Save** repacks atomically: write to a temp file, then rename.
- Version the schema from day one and include a migration hook.
- Data files are *not* bundled (scripts load their own paths). Say so in the README.

### 4.13 Export
- **PDF:** page size exactly equals the figure size (tolerance ≤ 0.01 mm). Requirements:
  - Text stays live text with embedded (subset) fonts, editable in Illustrator and Inkscape.
  - Each panel is one top-level group, without needless clip masks or deeply nested wrapper groups. Clip only where content truly exceeds the panel box.
  - Embedded rasters keep their original pixel dimensions.
  - No vector content is rasterised.
- **TIFF/PNG:** rasterise the final PDF at 300 / 600 / 1200 dpi, RGB. Pixel dimensions = round(mm / 25.4 × dpi). DPI metadata is written, and TIFF uses LZW compression.
- **Composition pipeline: you decide, after a spike.** Prototype at least two approaches against the acceptance tests in §9, then pick one and record the evidence in `DECISIONS.md`. Candidates:
  - (A) Each panel renders to PDF, and the panels are composed by placing pages as Form XObjects (pikepdf, PyMuPDF `show_pdf_page`, qpdf, …).
  - (B) Each panel renders to SVG (svglite in R, matplotlib with `svg.fonttype="none"`), the SVGs are composed, and the result is converted to PDF with a converter that preserves text.
  Judge by what Illustrator/Inkscape show when they open the result: live text, the object tree, and font fidelity.

## 5. UI layout (single window)
- **Left:** panel list (reorderable; shows type, label and render state) and the project tree.
- **Centre:** canvas showing the frame at the chosen size, gutters visible, drop targets and stale badges, with zoom and actual-size controls.
- **Right:** context inspector. With nothing selected, it shows the global style (Figure size · Typography · Lines & markers · Axis style · Palette & semantic colours · Spacing). With a panel selected, it shows the panel's geometry, label, interpreter, style overrides and alignment locks.
- **Bottom/side drawer:** code editor + console for the selected script panel, and a Checks tab.
- Top bar: project name, Save, Refresh all, Export.

## 6. Non-functional requirements
- macOS 13+ on Apple Silicon and Intel. The server binds to `127.0.0.1` only, on a random free port. Scripts run with the user's permissions; since it's a local single-user tool, no sandbox is needed. Never expose the server to the network.
- A canvas drag must stay at 60 fps for 12 panels. A typical warm panel render should take under 3 s.
- One command to install and run (for example `make dev` / `make run`). The launch command opens the browser automatically.
- Logs go to the working directory. Crashes in a script must never crash the server.

## 7. Architecture expectations
- Choose the stack. A Python backend (FastAPI + strong PDF tooling) with a React/TypeScript canvas is a natural fit, but it is not mandated. Justify your choice in `ARCHITECTURE.md`: component diagram, render pipeline sequence, solver design, data model, and how R and Python workers are isolated.
- Keep the **layout solver**, **style resolver/injectors**, **runners**, **composer/exporter** and **validators** as separate modules with unit-testable pure cores.

## 8. Build order (each stage must be runnable and tested before moving on)
1. Repository skeleton, `make` targets, data model + schema, bundle open/save, presets.
2. Layout solver + canvas with empty placeholder panels: drag, drop targets, resize, numeric edit, undo/redo. Property tests (§9) pass.
3. Python runner + injector + metadata. Then the R runner + injector + metadata. Stale/refresh flow and cache.
4. Composition pipeline spike → chosen PDF exporter + TIFF/PNG export.
5. Global style inspector, palettes, semantic map, per-panel overrides.
6. Validation (min font, font fallback, dpi) with canvas highlighting and the Checks sidebar.
7. Non-script panels (image, vector, text, legend) and manual labels.
8. In-app editor + external file watching.
9. Row/column plot-area alignment.
10. Sample project, docs, polish.

## 9. Tests and acceptance criteria
**Automated (CI runs everything; tests that need R or Python skip with a clear message when the interpreter is missing):**
- Layout property tests: apply thousands of random operation sequences (move, resize, add, delete, lock). After each one, the rects plus gutters/margins tile the frame exactly (area sum and pairwise non-overlap, within 1e-6 mm), and every panel is at least the minimum size.
- Style round-trip, run for both R and Python: render a panel with known tokens, parse the output PDF, then assert
  - every text run's size equals its role size ±0.05 pt;
  - axis stroke width equals `line_axis_pt` ±0.02 pt;
  - data line width equals `line_data_pt` ±0.02 pt;
  - the font name matches the chosen family.
- Export: page size within 0.01 mm. `pdftotext` (or equivalent) extracts every label and tick string, which proves text is live. There is one top-level group per panel. Embedded image pixel dimensions equal the source. Raster export pixel dimensions match the formula exactly.
- Min-font validator: a fixture panel with a deliberately 4 pt annotation is flagged; a compliant panel produces no warnings.
- Bundle: save → reopen yields an identical project; migration from a v0 fixture works.

**Sample project** (`examples/nature-double.plate`, 183 mm wide, with scripts that generate their own synthetic data):
- (a) ggplot2 with facets; (b) matplotlib with 2 subplots; (c) ggplot2 using the semantic colours Control/Treatment; (d) seaborn using the same semantic colours; (e) an imported microscopy-like PNG; (f) an auto legend panel.
- Main font 7 pt, minimum 5 pt, Arial, axis lines 0.5 pt, data lines 0.75 pt. Row alignment locked for (a)–(b).

**Manual acceptance checklist** (`docs/ACCEPTANCE.md`): open the exported PDF in Illustrator and Inkscape on macOS and confirm live editable text, one group per panel, no stray clip masks, and full-resolution images.

## 10. Deliverables
- Working app + `README.md`: install prerequisites (R, Python, packages), one-command start, a five-minute tutorial.
- `ARCHITECTURE.md`, `DECISIONS.md`, `docs/script-contract.md` (how to write panel scripts in R and Python, with templates), `docs/ACCEPTANCE.md`.
- The `plate` helper libraries for R and Python, the sample project, and the full test suite.