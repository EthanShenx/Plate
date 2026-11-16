This is a synthetic reconstruction of Figure 3 from Han et al., [*A multi-tissue single-cell expression atlas in cattle*](https://doi.org/10.1038/s41588-025-02329-5). Each chart constructs its own data from a fixed random seed. The embedded scripts use NumPy and Matplotlib and carry no source images or external data files.

Run from the Plate checkout.

```sh
.venv/bin/python -m examples.cattle_figure3.build
make run BUNDLE=output/cattle-atlas-figure-3/cattle-immune-atlas-figure-3-synthetic.plate
```

In Plate, select any plot and choose **Edit script** to adjust the synthetic observations or chart styling. Panels e and f and the native state legend use the same project colours. The clustermaps and dense point clouds use raster artwork inside the PDF to keep it manageable. Panel letters, chart text, annotations, bars and the ribbons export separately.

The **Cluster connectors** script references the content boxes of both the heatmap and enrichment table. Move or resize either one within the connector panel’s drawing area. The ribbons rerender using the revised positions and sizes. Select **Geometry → Referenced panels** on the connector panel to see the two references.
