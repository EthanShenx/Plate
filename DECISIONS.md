# Decisions

- Python standard-library HTTP with browser ES modules keeps startup small and places physical geometry and persistence in Python. FastAPI and React were considered for a larger app.
- Nature lists the print widths and full page depth in final-submission guidance and recommends 170 mm for a figure with its caption below in its research guide. Cell Press and PNAS retain provisional dimensions because their exact values could not be confirmed from accessible primary guidance. Science remains disabled.
- The visual direction is a quiet print-production workbench with a paper canvas, drafting grid, evergreen controls and serif wordmark. A dark developer-tool shell was considered.
- Native Cairo PDF in R and Matplotlib PDF in Python preserve live text. Cairo R rounds its MediaBox to whole points, so Plate restores the fractional page bounds without transforming content. Matplotlib uses TrueType PDF fonts.
- R linewidth conversion is pt × 96 ÷ 72 ÷ ggplot2 .pt, while annotation size is pt ÷ .pt and theme text is already in pt. PDF tests measure the emitted widths and effective text sizes for both engines.
- The composition spike selected PDF Form XObjects with MuPDF's placement wrapper removed. In the 66 × 38.1 mm fixture, native PDF retained all four ticks, the label, embedded Arial, both panel forms and the native 17 × 11 raster. SVG composed through librsvg 2.61 retained two ticks, embedded Arial and the raster, and produced zero panel forms. Inspecting how desktop editors interpret the PDF remains a separate manual check.
- Stale PDFs are centered and clipped at the current box if needed to retain physical point sizes. The browser stretches the old preview while marked stale, and users can refresh before exporting.
