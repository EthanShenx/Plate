from io import BytesIO
import math
import unittest

from PIL import Image
import pymupdf

from plate.export import compose_pdf, rasterize
from plate.model import Panel, Project
from plate.style import PT_PER_MM, content_box, resolve


class Export(unittest.TestCase):
    def test_live_fonts_and_native_images_in_single_level_forms(self):
        png = BytesIO()
        Image.new("RGB", (37, 29), "#EA7860").save(png, format="PNG")
        font = pymupdf.Font(fontname="tiro")
        box = {"x": 1, "y": 1, "w": 20, "h": 15}
        with pymupdf.open() as document:
            page = document.new_page(width=20 * PT_PER_MM, height=15 * PT_PER_MM)
            writer = pymupdf.TextWriter(page.rect)
            writer.append((2, 10), "Label 0 1 2", font=font, fontsize=7)
            writer.write_text(page)
            page.insert_image(pymupdf.Rect(3, 12, 30, 33), stream=png.getvalue())
            source = document.tobytes()
        result = compose_pdf(42, 17, [(source, box), (source, {**box, "x": 21})])
        with pymupdf.open(stream=result) as document:
            page = document[0]
            self.assertAlmostEqual(page.rect.width / PT_PER_MM, 42, delta=.01)
            self.assertAlmostEqual(page.rect.height / PT_PER_MM, 17, delta=.01)
            self.assertEqual(page.get_text().count("Label 0 1 2"), 2)
            self.assertEqual(len(page.get_xobjects()), 2)
            self.assertTrue(all(entry[2] == 0 for entry in page.get_xobjects()))
            self.assertEqual([(item["width"], item["height"]) for item in page.get_image_info()],
                             [(37, 29), (37, 29)])
            self.assertTrue(all(document.extract_font(item[0])[3] for item in page.get_fonts()))

    def test_blank_panel_still_has_form(self):
        with pymupdf.open(stream=compose_pdf(20, 20, [(None, dict(x=1, y=1, w=18, h=18))])) as document:
            self.assertEqual(len(document[0].get_xobjects()), 1)

    def test_narrow_placement_preserves_stale_plot_and_panel_label(self):
        with pymupdf.open() as document:
            source = document.new_page(width=120, height=70)
            source.insert_text((3, 20), "Left axis label", fontsize=8)
            source.insert_text((85, 50), "Right title", fontsize=7)
            source = document.tobytes()
        rect = dict(x=0, y=0, w=18, h=40)
        panel = Panel(label="Long panel label", overrides={"panel_label_pt": 20})
        style = resolve(Project(), panel)["style"]
        box = content_box(rect, panel, style)
        with pymupdf.open(stream=compose_pdf(18, 40, [(source, box, panel.label, rect, style)])) as document:
            page = document[0]
            for label in ("Left axis label", "Right title", panel.label):
                self.assertIn(label, page.get_text())
            for kind, bounds in page.get_bboxlog():
                if kind == "fill-text":
                    self.assertTrue(page.rect.contains(pymupdf.Rect(bounds)), bounds)

    def test_raster_dimensions_and_metadata_at_each_dpi(self):
        width, height = 21.33, 16.29
        result = compose_pdf(width, height, [])
        for dpi in (300, 600, 1200):
            for format in ("png", "tiff"):
                with self.subTest(dpi=dpi, format=format):
                    data = rasterize(result, width, height, format, dpi)
                    with Image.open(BytesIO(data)) as image:
                        self.assertEqual(image.size, tuple(math.floor(mm/25.4*dpi+.5)
                                                           for mm in (width, height)))
                        self.assertEqual(image.mode, "RGB")
                        self.assertAlmostEqual(image.info["dpi"][0], dpi, delta=.05)
                        if format == "tiff":
                            self.assertEqual(image.info["compression"], "tiff_lzw")
