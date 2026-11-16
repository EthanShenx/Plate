from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from plate.checks import font_matches, panel_checks
from plate.model import Panel, Project
from plate.render import pdf_metadata
from plate.style import resolve


class Checks(unittest.TestCase):
    def test_pdf_detects_collisions_but_leaves_adjacent_labels_alone(self):
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "labels.pdf"
            with pymupdf.open() as document:
                page = document.new_page()
                page.insert_text((30, 30), "Point label", fontsize=8)
                page.insert_text((41, 31), "Legend title", fontsize=8)
                page.insert_text((30, 40), "Adjacent label", fontsize=8)
                page.insert_text((60, 80), "Other point", fontsize=8)
                page.insert_text((60, 80), "Other point", fontsize=8)
                document.save(path)
            result = panel_checks(Panel(), {"metadata": pdf_metadata(path)},
                                  resolve(Project(style={"font_family": "Helvetica"}))["style"])
        self.assertEqual([item["kind"] for item in result], ["text-overlap"])
        self.assertIn("Point label", result[0]["message"])
        self.assertIn("Legend title", result[0]["message"])
        self.assertEqual(len(result[0]["boxes"]), 2)
    def test_pdf_fixture_small_and_compliant_annotation(self):
        panel = Panel()
        style = resolve(Project(style={"font_family": "Helvetica"}))["style"]
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "text.pdf"
            for size in (4, 5.5):
                with pymupdf.open() as document:
                    page = document.new_page()
                    page.insert_text((30, 30), "Annotation", fontsize=size)
                    document.save(path)
                result = panel_checks(panel, {"metadata": pdf_metadata(path)}, style)
                self.assertEqual(len(result), int(size == 4))
                if result:
                    self.assertEqual(result[0]["kind"], "font-size")
                    self.assertAlmostEqual(result[0]["size"], 4)
                    self.assertEqual(len(result[0]["bbox"]), 4)

    def test_font_families_and_raster_warnings(self):
        self.assertTrue(font_matches("Arial", "ABCDEF+Arial-BoldMT"))
        self.assertFalse(font_matches("Arial", "DejaVuSans"))
        result = panel_checks(Panel(), {"metadata": {
            "text": [{"text": "Axis", "font": "DejaVuSans", "size": 7}],
            "effective_dpi": [299, 299.8, 300],
        }}, resolve(Project())["style"])
        self.assertEqual([item["kind"] for item in result], ["font-family", "raster-dpi"])
