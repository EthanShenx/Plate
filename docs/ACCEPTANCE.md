# Export acceptance

1. Open `examples/nature-double.plate`, refresh the scripts and confirm **Checks** has no warnings. Export an editable PDF. Repeat with PNG and TIFF at 300, 600 and 1200 dpi.
2. Open the PDF in Illustrator on macOS. In **Window → Layers**, expand the imported layer. Inspect the six panel groups, then select an axis title and a panel label with the Type tool. The font should resolve to Arial. Inspect clipping around the microscopy cover crop and inspect the embedded image in the Links panel.
3. Open the PDF in Inkscape using the internal PDF importer. Inspect the six groups under the imported page in **Layers and Objects**. Select an axis title and label with the Text tool. Inspect the group hierarchy and the embedded raster.
4. Use `pdffonts` to check that the fonts are embedded and subset, `pdftotext` to check the labels and ticks, and `pdfimages -list` to check for a 900 × 670 image. The figure is 183 × 123 mm. Each raster dimension is `round(mm / 25.4 × dpi)`.

## Recorded on macOS

- The sample exported with six page-level panel forms, subset Arial, selectable labels and a single 900 × 670 embedded raster. The test suite checks the PDF objects and all raster export sizes.
- Illustrator 2025 opened the revised PDF with Arial resolved, including the manual labels and legend. The native font dictionaries use the installed PostScript names.
- Inkscape 1.4.4's internal PDF import created six panel groups under one page group and retained labels, tick strings and the raster as editable objects. It generated additional clip paths during conversion, including for the plot marker forms. The exported PDF retains source plotting clips and the intentional cover crop.
- Chrome's sample workflow refreshed six panels, detected an external edit, saved a bundle with previews and exported the PDF. A 12-panel resize test on the same Apple Silicon Mac measured 60 fps over 60 animation frames.
