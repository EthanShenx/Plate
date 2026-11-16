# Figure 4 reconstruction with synthetic data

The reference is Figure 4 on PDF page 28 of Ren, Shen et al., *scSAID: A Comprehensive Cross-Species Single-Cell Skin Atlas Reveals Species-Specific Responses to Psoriasis*, bioRxiv preprint [10.64898/2026.07.20.739409](https://doi.org/10.64898/2026.07.20.739409). The reference is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). This fixture follows the layout and chart types with generated values, illustrative counts and simulated edges.

Run from the repository root.

```sh
.venv/bin/python -m examples.figure4.build --render
make run BUNDLE=output/pdf/figure4-grouped.plate
```

The builder stores editable Matplotlib scripts for the plots and shared legends in the project and writes an editable PDF through Plate. The a/b and d/e pairs share source templates and run independently inside the bundle. The artboard measures 183 × 244 mm. The bottom row has extra height for regulator labels. Plate positions the panels, draws letters a–k and updates any panel whose inputs change. The native text object above the panels identifies the data as synthetic.

| Panels | Simulated visual |
| --- | --- |
| a, b | Ranked AUC dot plots with separate colour scales |
| c | Two overlapping sets with example DEG counts |
| d, e | Circular enrichment plots with term labels, gene counts and p-value scales |
| f | Paired signed fold changes and absolute cross-species differences |
| g | Four scatter plots with point size mapped to simulated counts |
| h | Four normalised stacked-bar columns |
| i | Regulator-class pie chart |
| j | Two directed TF–target networks with line width mapped to simulated significance |
| k | Paired activity changes grouped by regulator class |

## Review and edit in Plate

- Select the heading for g, h or j in **Panels**, then drag any of its members to move the whole group. Select a child row to move or resize it independently. For example, select **Mouse target** in h to adjust that column, or **Edge legend** in j to place the shared legend.
- To group other panels, select one in the panel list, then Shift-click ungrouped rows and choose **Group selected panels**.
- The h condition legend and j edge legend use the same named colours as their charts. Change those colours under **Figure settings → Colours**. The g count legend uses the same point-size formula as its scatter plots.
- Click a possible text overlap in **Checks** to zoom to both text boxes. Plate uses PDF text bounds, so check intentionally overlapping or rotated text visually. It reports overlaps within a panel without moving labels.
- Use **Fit width** to navigate the full page. Zoom in for denser detail. Plate renders higher-resolution previews from the cached panel PDFs as needed.
